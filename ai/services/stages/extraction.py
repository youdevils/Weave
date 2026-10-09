"""
Reconcile stage 1 -- Extraction: intent + evidence segments + the ontology
catalogue (as hints) -> IntentFrame + EvidenceGraph claims citing segments.

Scale (ai/README.md): small evidence is extracted in a single call; larger
evidence in bounded batches of whole segments (AI_EXTRACTION_BATCH_MAX_CHARS;
at most AI_RECONCILE_EXTRACTION_MAX_BATCHES), each new batch's ids re-keyed
into the shared namespace and merged deterministically afterwards.

Every batch is validated for structure and literal provenance (L1) and
grounding (L2) -- never ontology validity (I1). Valid claims are appended at
once and frozen. What isn't settled is corrected separately, in the
`extraction_correction` stage with its own budget, so one defective batch
never costs another batch its chance:

    invalid claims                re-asked once, then dropped (with a finding);
                                  an unanchored assertion no segment could
                                  anchor is dropped without the re-ask
                                  (`no_anchor`)
    uncovered relevant segments   re-asked once, then recorded `uncovered`
    dismissed segments that name  re-asked once, then the dismissal stands,
    a target                      flagged for Verification and the findings

Re-asks from every batch are packed together (bounded by size) into one
correction WAVE (AI_RECONCILE_EXTRACTION_MAX_CORRECTION_CALLS per wave).
A segment re-ask is first-time extraction of that segment, so invalid claims
it produces are new work with their own correction opportunity: they form the
next wave (a fresh scope of the same budget), which re-asks them once. A wave
of item re-asks only produces corrections, whose output is not corrected
again -- so there are at most two waves, every item and segment is re-asked
at most once, and a second wave starts only while the run can still afford a
full Verification pass.

Dismissals are coverage decisions, never claims: they never enter the
EvidenceGraph.
"""

from __future__ import annotations

from django.conf import settings

from ai.services.artifacts import Finding
from ai.services.evidence_graph import EvidenceGraph, item_id, validate_evidence_graph
from ai.services.grounding import grounding_issues, relationship_anchors
from ai.services.intent_frame import IntentFrame, repair_elisions, validate_intent_frame
from ai.services.reconcile.coverage import DISMISSED, UNCOVERED, compute_coverage
from ai.services.reconcile.ingress import ingest, log
from ai.services.reconcile.responses import ExtractionResult
from ai.services.reconcile.state import ReconcileState
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.catalogue import build_catalogue
from ai.services.semantic.index import SemanticModelIndex
from ai.services.sources import with_ancestors
from ai.services.stages import prompts
from ai.services.stages.reconcile_steps import affords_recovery, grant_workload_allowance, note_shortfall
from ai.services.tracing import trace_active, trace_anchors
from ai.services.workflow.engine import Finish, Goto, Stage

_INCLUDE_RELATED = "include_related"


def plan_batches(bundle, max_chars, only=None) -> list[list[str]]:
    """Whole segments, in document order, packed up to `max_chars` of text. A
    table row always carries its header labels, so rows may span batches.
    `only` (readings mode): the prose-eligible segments -- structured content
    is interpreted by Readings, never extracted (readings.prose_eligible)."""

    batches, current, used = [], [], 0
    for segment in bundle.segments():
        if only is not None and segment.segment_id not in only:
            continue
        # A batch's payload also carries the heading/table segments its
        # segments sit under (citable context) -- they count too.
        def cost(present):
            extra = [a for a in segment.ancestor_ids if a not in present]
            return len(segment.text) + 1 + sum(len(bundle.segment(a).text) + 1 for a in extra if bundle.segment(a))

        size = cost(set(current))
        if current and used + size > max_chars:
            batches.append(current)
            current, used = [], 0
            size = cost(set())
        current.append(segment.segment_id)
        used += size
    if current:
        batches.append(current)
    return batches


def _known_entities(graph: EvidenceGraph) -> list[dict]:
    return [{"eid": e.eid, "name": e.name, "type_label": e.type_label, "specificity": e.specificity} for e in graph.entities]


def _frame_elements(frame: IntentFrame) -> dict:
    elements = {t.target_id: t for t in frame.targets}
    elements.update({a.anchor_id: a for a in frame.anchors})
    return elements


def _expanded_entities(rs) -> list:
    """The Reading-expanded entities of the latest analysis that aren't
    claims of `rs.graph` (none in claims mode, or before any analysis)."""

    analysis = getattr(rs, "analysis", None)
    if analysis is None or getattr(analysis, "graph", None) is None:
        return []
    claimed = rs.graph.ids()
    return [e for e in analysis.graph.entities if e.origin == "reading" and e.eid not in claimed]


def _dependants_pending(graph_ids, items) -> set:
    """Ids in `items` that refer to an id that isn't (yet) in the graph."""

    present = set(graph_ids) | {item_id(i) for i in items}
    waiting = set()
    changed = True
    while changed:
        changed = False
        for item in items:
            identifier = item_id(item)
            if identifier in waiting:
                continue
            refs = []
            if hasattr(item, "aid"):
                refs = [item.subject_eid, item.object_eid]
            elif hasattr(item, "fid"):
                refs = [item.subject_id]
            if any(ref not in present or ref in waiting for ref in refs):
                waiting.add(identifier)
                changed = True
    return waiting


def absorb(run, patch: EvidenceGraph, *, origin: str, replace_ids=frozenset()) -> dict:
    """
    Ingress (ai.services.reconcile.ingress: provenance normalisation, global
    ids, duplicate handling), then validation against the current graph:
    every valid claim is appended (frozen from now on); every invalid one --
    and any claim waiting on it -- is kept in `pending_items` with its issues.
    Every fate is logged. Returns the response's local -> global id map.
    """

    rs = run.state.reconcile
    patch, mapping, ingress_issues = ingest(patch, rs=rs, bundle=run.bundle, origin=origin, replace_ids=replace_ids)
    # Readings mode: the entities the current Readings expand to are shown to
    # the AI as already extracted (`pack_claims`), so a claim may refer to
    # them -- as endpoints only: ingress never lets a response define an
    # `x/` id, and an expansion entity is never appended to `rs.graph` (it is
    # recomputed by every analysis; a claim whose endpoint stops existing is
    # unanchored there).
    expanded = _expanded_entities(rs)
    known_ids = rs.graph.ids() | {e.eid for e in expanded}
    known_graph = rs.graph.appended(EvidenceGraph(entities=expanded)) if expanded else rs.graph

    # Deterministic repair: a claim about something never extracted (in the
    # graph, pending, or this patch) cannot mean anything -- dropped, never
    # re-asked, and logged with what it referred to. A *missing* endpoint is
    # not a reference: it is a malformed claim, left to validation
    # (missing_endpoint) and so to its one correction.
    dangling = []
    while True:
        defined = known_ids | set(rs.pending_items) | {item_id(i) for i in patch.items()}

        def unknown(ref, defined=defined) -> bool:
            return bool((ref or "").strip()) and ref not in defined

        bad = {a.aid: [r for r in (a.subject_eid, a.object_eid) if unknown(r)] for a in patch.assertions
               if unknown(a.subject_eid) or unknown(a.object_eid)}
        bad.update({f.fid: [f.subject_id] for f in patch.facts if unknown(f.subject_id)})
        if not bad:
            break
        for identifier, refs in bad.items():
            dangling.append(identifier)
            log(rs, identifier, origin=origin, outcome="dropped_dependant", reason=f"refers to {', '.join(refs)}, which is not an accepted claim")
        patch = patch.without(bad)
    for identifier in dangling:
        message = f"Ignored evidence claim '{identifier}': it refers to something that was not extracted."
        rs.notes = [*rs.notes, Finding(severity="info", message=message)]
        rs.note_refs[message] = identifier
    issues = list(ingress_issues)
    issues += validate_evidence_graph(patch, bundle=run.bundle, intent_text=run.intent.text, known_ids=frozenset(known_ids))
    issues += grounding_issues(patch, bundle=run.bundle, known=known_graph)
    by_item: dict[str, list] = {}
    for found in issues:
        by_item.setdefault(found.item_id or "", []).append(found)

    candidates = [i for i in patch.items() if item_id(i) not in by_item]
    waiting = _dependants_pending(known_ids, candidates)
    for item in patch.items():
        identifier = item_id(item)
        if identifier in by_item or identifier in waiting:
            rs.pending_items[identifier] = (item, by_item.get(identifier, []))
            if identifier in by_item:
                log(rs, identifier, origin=origin, outcome="invalid", reason=by_item[identifier][0].message)
            else:
                log(rs, identifier, origin=origin, outcome="waiting", reason="refers to a claim that is not yet valid")
            continue
        rs.pending_items.pop(identifier, None)
        log(rs, identifier, origin=origin, outcome="accepted")
        rs.graph = rs.graph.appended(EvidenceGraph(**{
            "entities": [item] if hasattr(item, "eid") else [],
            "assertions": [item] if hasattr(item, "aid") else [],
            "facts": [item] if hasattr(item, "fid") else [],
        }))

    # A pending claim whose blocker is now in the graph is valid after all.
    released = True
    while released:
        released = False
        for identifier, (item, item_issues) in list(rs.pending_items.items()):
            if item_issues:
                continue
            refs = [item.subject_eid, item.object_eid] if hasattr(item, "aid") else ([item.subject_id] if hasattr(item, "fid") else [])
            if all(ref in rs.graph.ids() or ref in known_ids for ref in refs):
                known = rs.graph.appended(EvidenceGraph(entities=expanded)) if expanded else rs.graph
                again = grounding_issues(EvidenceGraph(**{"assertions" if hasattr(item, "aid") else "facts": [item]}), bundle=run.bundle, known=known)
                if not again:
                    del rs.pending_items[identifier]
                    rs.graph = rs.graph.appended(EvidenceGraph(**{"assertions" if hasattr(item, "aid") else "facts": [item]}))
                    log(rs, identifier, origin=origin, outcome="accepted", reason="the claim it waited on became valid")
                    released = True
    return mapping


def record_dismissals(run, dismissals) -> None:
    rs = run.state.reconcile
    for dismissal in dismissals:
        if run.bundle.segment(dismissal.segment_id) is None:
            continue
        if rs.prose_scope is not None and dismissal.segment_id not in rs.prose_scope:
            continue  # readings mode: structure is covered by its Reading, never dismissed per segment
        entry = rs.dismissals.setdefault(dismissal.segment_id, {"reason": "", "count": 0})
        entry["reason"] = dismissal.reason
        entry["count"] += 1


def segment_payload(run, segment_ids) -> list[dict]:
    """The segments and the heading/table segments they sit under, all citable."""

    return [s.context() for s in with_ancestors(run.bundle, segment_ids)]


def unaccounted_reask(names) -> str:
    """Why a segment that names target entities no claim citing it involves is
    re-asked -- in the segment's own names only, never a domain example."""

    them = "it" if len(names) == 1 else "them"
    return (f"It names {', '.join(repr(n) for n in names)}, but no claim extracted from it involves {them}: extract what "
            f"this segment states about {them} -- with any other entity it names in relation to {them}, under the name it "
            "uses -- or dismiss it with a specific reason")


def cited_payload(run, item) -> dict:
    """An invalid item's citations as a correction sees them: exactly the
    segments it cites (`cited_segments`), and -- separately, citable but NOT
    cited -- the headings/tables they sit under (`context_segments`). Mixing
    the two once showed a correction an uncited title heading as already
    cited, contradicting the very issue it was asked to fix."""

    cited = {p.segment_id for p in item.provenance if p.segment_id}
    shown = segment_payload(run, sorted(cited))
    return {"cited_segments": [s for s in shown if s["segment_id"] in cited],
            "context_segments": [s for s in shown if s["segment_id"] not in cited]}


def _known_name(rs, eid) -> tuple[str, list[str]] | None:
    """-> (name, aliases) of a known entity, from the graph or a still-pending claim."""

    entity = rs.graph.entity(eid)
    if entity is None:
        pending = rs.pending_items.get(eid)
        entity = pending[0] if pending else None
    return (entity.name, entity.aliases) if entity is not None else None


def correction_anchors(run, item, issues, *, stage: str) -> dict | None:
    """For an assertion rejected as `unanchored_claim`: where its claimed
    subject and object could actually be related (ai.services.grounding.
    relationship_anchors) -- a locator for the correction, never a claim.
    None when the item isn't an unanchored assertion, or either endpoint's
    name isn't known. `stage` is the caller's own stage id, used only to
    correlate the opt-in trace event below with that call's trace file --
    it never affects the returned payload."""

    if not hasattr(item, "aid") or not any(i.code == "unanchored_claim" for i in issues):
        return None
    rs = run.state.reconcile
    subject, obj = _known_name(rs, item.subject_eid), _known_name(rs, item.object_eid)
    if subject is None or obj is None:
        return None
    subject_names, object_names = [subject[0], *subject[1]], [obj[0], *obj[1]]
    anchors = relationship_anchors(subject_names, object_names, run.bundle)
    if trace_active():
        trace_anchors(run.execution.id, run.current_sequence, stage, item_id(item),
                      subject=subject[0], object=obj[0], anchors=anchors)
    payload = {"direct": segment_payload(run, anchors["direct"]),
              "structural": [segment_payload(run, list(pair)) for pair in anchors["structural"]]}
    if "subject_only" in anchors:
        payload["subject_segments"] = segment_payload(run, anchors["subject_only"])
        payload["object_segments"] = segment_payload(run, anchors["object_only"])
    return payload


def no_anchor(run, item, issues) -> bool:
    """An assertion whose only defect is `unanchored_claim` while no segment
    relates its subject and object -- no direct anchor, no structural pair
    (ai.services.grounding.relationship_anchors). Its correction could only
    withdraw it (the correction contract says so), so it is not re-asked: it
    stays pending and is dropped like any unrecovered item, with its own
    issue as the reason. An anchored one, or one with any other defect, is
    re-asked as before."""

    if not hasattr(item, "aid") or not issues or any(i.code != "unanchored_claim" for i in issues):
        return False
    rs = run.state.reconcile
    subject, obj = _known_name(rs, item.subject_eid), _known_name(rs, item.object_eid)
    if subject is None or obj is None:
        return False
    anchors = relationship_anchors([subject[0], *subject[1]], [obj[0], *obj[1]], run.bundle)
    return not anchors["direct"] and not anchors["structural"]


def finish_extraction(run):
    """After the last batch: queue every defect for one bounded round of
    re-asks, or settle."""

    state = run.state
    rs = state.reconcile
    frame_issues = validate_intent_frame(rs.frame, run.intent.text)
    rs.pending_frame = {}
    for found in frame_issues:
        rs.pending_frame.setdefault(found.item_id, []).append(found)

    coverage = compute_coverage(run.bundle, rs.graph, rs.frame, state.index, rs.dismissals, scope=rs.prose_scope)
    queue = [("frame", i) for i in rs.pending_frame if i not in rs.reasked]
    queue += [("item", i) for i, (item, issues) in rs.pending_items.items()
              if issues and i not in rs.reasked and not no_anchor(run, item, issues)]
    for segment_id, entry in coverage.items():
        if segment_id in rs.reasked or segment_id in rs.unextracted:
            continue
        if entry.status == UNCOVERED or (entry.status == DISMISSED and entry.named_target):
            queue.append(("segment", segment_id))
    rs.correction_queue = queue
    if queue and run.allows("extraction_correction"):
        return Goto("extraction_correction")
    if queue and run.remaining_calls() <= 0:
        note_shortfall(rs, "extraction_uncorrected", [identifier for _, identifier in queue])
    return settle(run)


def repair_frame(rs, intent_text) -> None:
    rs.frame, repaired = repair_elisions(rs.frame, intent_text)
    rs.frame_repairs.update(repaired)


def unframe(rs, frame, pending: dict) -> IntentFrame:
    """Frame elements that still fail grounding leave the frame (they are not
    verified claims) but never disappear: each is kept as unframed requested
    work, reported as a block and recoverable by a Verification frame_error
    amendment."""

    frame = frame.model_copy(deep=True)
    for target in [t for t in frame.targets if t.target_id in pending]:
        rs.unframed[target.target_id] = {"kind": "target", "element": target.model_dump(mode="json"),
                                         "reason": pending[target.target_id][0].message}
    for anchor in [a for a in frame.anchors if a.anchor_id in pending]:
        rs.unframed[anchor.anchor_id] = {"kind": "anchor", "element": anchor.model_dump(mode="json"),
                                         "reason": pending[anchor.anchor_id][0].message}
    frame.targets = [t for t in frame.targets if t.target_id not in pending]
    frame.anchors = [a for a in frame.anchors if a.anchor_id not in pending]
    if _INCLUDE_RELATED in pending:
        rs.unframed[_INCLUDE_RELATED] = {"kind": "include_related", "element": {"excerpt": frame.include_related_excerpt},
                                         "reason": pending[_INCLUDE_RELATED][0].message}
        frame.include_related, frame.include_related_excerpt = False, None
    return frame


def settle(run):
    """Drop whatever evidence is still invalid (it has no verified, grounded
    support) and hand over to the deterministic pipeline. Frame elements that
    still fail are kept as unframed requested work, never dropped. Uncovered
    and flagged segments are reported by the analysis' coverage decisions,
    which update as later stages add evidence."""

    state = run.state
    rs = state.reconcile
    notes = []
    for identifier, (item, issues) in sorted(rs.pending_items.items()):
        detail = issues[0].message if issues else "it refers to a claim that could not be verified"
        notes.append(Finding(severity="info", message=f"Ignored evidence claim '{identifier}': {detail}"))
        rs.note_refs[notes[-1].message] = identifier
        log(rs, identifier, origin="extraction", outcome="dropped" if issues else "dropped_dependant", reason=detail)
    rs.pending_items = {}
    if rs.pending_frame:
        rs.frame = unframe(rs, rs.frame, rs.pending_frame)
        rs.pending_frame = {}
    rs.correction_queue, rs.current_pack = [], []
    rs.notes = [*rs.notes, *notes]
    state.interpretation = rs.frame.restated_intent or state.interpretation
    return Goto("analysis")


class ExtractionStage(Stage):
    """One first-pass batch per call."""

    stage_id = "extraction"
    response_schema = ExtractionResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.EXTRACTION

    def build_input(self, run) -> dict:
        state = run.state
        if state.reconcile is None:
            state.reconcile = ReconcileState()
        rs = state.reconcile
        rs.intent_text = run.intent.text
        state.index = SemanticModelIndex.load(run.model)
        state.catalogue = build_catalogue(state.index)
        if not rs.batches:
            rs.batches = plan_batches(run.bundle, settings.AI_EXTRACTION_BATCH_MAX_CHARS, only=rs.prose_scope) or [[]]
            grant_workload_allowance(run)
        batch = rs.batches[rs.batch_index]
        payload = {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "catalogue": state.catalogue.model_dump(mode="json"),
            "frame_intent": rs.batch_index == 0,
            "batch": {"number": rs.batch_index + 1, "of": len(rs.batches)},
            "segments": segment_payload(run, batch),
        }
        if rs.batch_index > 0:
            payload["known_entities"] = _known_entities(rs.graph)
        return payload

    def evaluate(self, run, output: ExtractionResult):
        rs = run.state.reconcile
        first = rs.batch_index == 0
        if first:
            if output.clarification.needed:
                return Finish(
                    OperationOutcome.NEEDS_USER_CLARIFICATION,
                    explanation=output.clarification.question or "The request needs clarification.",
                )
            rs.frame = output.intent_frame.model_copy(deep=True)
            repair_frame(rs, run.intent.text)
            rs.notes = [f for f in output.findings if f.severity in ("info", "warning")]
        absorb(run, output.evidence.with_origin("extraction"), origin="extraction")
        record_dismissals(run, output.dismissed_segments)

        rs.batch_index += 1
        if rs.batch_index < len(rs.batches):
            if run.allows(self.stage_id):
                return Goto(self.stage_id)
            for batch in rs.batches[rs.batch_index:]:
                rs.unextracted |= set(batch)
            note_shortfall(rs, "extraction_unextracted", rs.unextracted)
        return finish_extraction(run)


class ExtractionCorrectionStage(Stage):
    """Item- and segment-level re-asks, packed across batches."""

    stage_id = "extraction_correction"
    response_schema = ExtractionResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.EXTRACTION + "\n\n" + prompts.EXTRACTION_CORRECTION

    def build_input(self, run) -> dict:
        state = run.state
        rs = state.reconcile
        budget, pack = settings.AI_EXTRACTION_BATCH_MAX_CHARS, []
        coverage = compute_coverage(run.bundle, rs.graph, rs.frame, state.index, rs.dismissals, scope=rs.prose_scope)
        invalid_items, frame_items, segments = [], [], []
        while rs.correction_queue:
            kind, identifier = rs.correction_queue[0]
            if kind == "item" and identifier in rs.pending_items:
                item, issues = rs.pending_items[identifier]
                entry = {
                    "id": identifier, "item": item.model_dump(mode="json"),
                    "issues": [i.model_dump(mode="json", exclude_none=True) for i in issues],
                    **cited_payload(run, item),
                }
                anchors = correction_anchors(run, item, issues, stage=self.stage_id)
                if anchors is not None:
                    entry["relationship_anchors"] = anchors
                size = len(str(entry))
            elif kind == "frame" and identifier in rs.pending_frame:
                element = _frame_elements(rs.frame).get(identifier)
                entry = {
                    "id": identifier,
                    "item": element.model_dump(mode="json") if element is not None else {"include_related": rs.frame.include_related},
                    "issues": [i.model_dump(mode="json", exclude_none=True) for i in rs.pending_frame[identifier]],
                }
                size = len(str(entry))
            elif kind == "segment" and run.bundle.segment(identifier) is not None:
                segment = run.bundle.segment(identifier)
                state_entry = coverage.get(identifier)
                if state_entry and state_entry.unaccounted:
                    why = unaccounted_reask(state_entry.unaccounted)
                else:
                    why = (
                        f"It mentions {', '.join(repr(n) for n in state_entry.named)}" if state_entry and state_entry.named
                        else "It mentions a kind of thing the request asks for"
                    )
                if state_entry and state_entry.status == DISMISSED:
                    why += f"; it was dismissed as: {state_entry.reason!r}. Extract what it says, or dismiss it again with a specific reason"
                entry = {"segment": segment.context(), "context_segments": segment_payload(run, segment.ancestor_ids), "why": why}
                size = len(segment.text) + len(why)
            else:
                rs.correction_queue.pop(0)
                continue
            if pack and size > budget:
                break
            budget -= size
            rs.correction_queue.pop(0)
            pack.append((kind, identifier))
            rs.reasked.add(identifier)
            (invalid_items if kind == "item" else frame_items if kind == "frame" else segments).append(entry)
        rs.current_pack = pack
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "catalogue": state.catalogue.model_dump(mode="json") if state.catalogue else None,
            "invalid_items": invalid_items,
            "invalid_frame_items": frame_items,
            "uncovered_segments": segments,
            "known_entities": _known_entities(rs.graph),
        }

    def evaluate(self, run, output: ExtractionResult):
        rs = run.state.reconcile
        replaced = {identifier for kind, identifier in rs.current_pack if kind == "item"}
        frame_ids = {identifier for kind, identifier in rs.current_pack if kind == "frame"}
        discovery = any(kind == "segment" for kind, _ in rs.current_pack)

        if frame_ids:
            frame = rs.frame.model_copy(deep=True)
            targets = {t.target_id: t for t in output.intent_frame.targets}
            anchors = {a.anchor_id: a for a in output.intent_frame.anchors}
            frame.targets = [targets.get(t.target_id, t) for t in frame.targets if t.target_id not in frame_ids or t.target_id in targets]
            frame.anchors = [anchors.get(a.anchor_id, a) for a in frame.anchors if a.anchor_id not in frame_ids or a.anchor_id in anchors]
            if _INCLUDE_RELATED in frame_ids:
                frame.include_related = output.intent_frame.include_related
                frame.include_related_excerpt = output.intent_frame.include_related_excerpt
            rs.frame = frame
            repair_frame(rs, run.intent.text)
            rs.pending_frame = {k: v for k, v in rs.pending_frame.items() if k not in frame_ids}
            for found in validate_intent_frame(rs.frame, run.intent.text):
                rs.pending_frame.setdefault(found.item_id, []).append(found)

        # Replacements keep their ids; anything new gets a globally unused id
        # at ingress, so it can never collide with (or overwrite) a frozen claim.
        for identifier in replaced:
            rs.pending_items.pop(identifier, None)
        absorb(run, output.evidence.with_origin("extraction"), origin="extraction_correction", replace_ids=replaced)
        record_dismissals(run, output.dismissed_segments)
        rs.current_pack = []
        if discovery:
            # Invalid claims a segment re-ask produced for the first time.
            queued = {identifier for _, identifier in (*rs.correction_queue, *rs.next_wave)}
            rs.next_wave += [("item", i) for i, (item, issues) in rs.pending_items.items()
                             if issues and i not in replaced and i not in rs.reasked and i not in queued
                             and not no_anchor(run, item, issues)]

        if rs.correction_queue and run.allows(self.stage_id):
            return Goto(self.stage_id)
        # Left undone for want of calls -- not by a wave's own bound: reported.
        cut = [i for _, i in rs.correction_queue] if rs.correction_queue and run.remaining_calls() <= 0 else []
        if rs.next_wave and affords_recovery(run):
            # Whatever is left of this wave keeps its fate (dropped / uncovered).
            rs.correction_queue, rs.next_wave = rs.next_wave, []
            run.open_scope(self.stage_id)
            if run.allows(self.stage_id):
                note_shortfall(rs, "extraction_uncorrected", [*rs.budget_shortfall.get("extraction_uncorrected", []), *cut])
                return Goto(self.stage_id)
            cut += [i for _, i in rs.correction_queue]
        cut += [i for _, i in rs.next_wave]  # a wave the run could not afford
        note_shortfall(rs, "extraction_uncorrected", [*rs.budget_shortfall.get("extraction_uncorrected", []), *cut])
        return settle(run)
