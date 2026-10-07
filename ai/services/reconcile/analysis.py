"""
The deterministic Reconcile pipeline, run end to end from the current claims
(EvidenceGraph + IntentFrame + pinned answers) every time anything changes:

    claims -> grounding -> normalise -> map -> identify -> target/anchor
           -> ESC -> attribute values -> removals -> coverage
           -> questions (decision gaps) / probe requests (evidence gaps)
           -> intent target status (every target is requested work)

Every explicit intent target ends in a reported status (`target_status`):
evidenced (its items go through ESC like any other), folded (a request for
relationships in general == include_related), retire, or a target-level
block -- unframed (its framing claim could not be grounded in the intent),
unmapped (no catalogue kind), undecided (which kind is unresolved),
not_evidenced (nothing of that kind evidenced). A mapped target with nothing
evidenced, or with relevant segments left uncovered, is a *target gap*: an
evidence gap for the Gap Probe ("what do these segments say about
<kind>s?"). Failing to find evidence creates recoverable work; it never
erases the request.

Re-running the whole chain after a new claim (an Adjudication answer, a Gap
Probe result, a Verification objection) is how "invalidate a decision and
its dependants" is realised: every decision is a pure function of the claims
it rests on, decision ids are stable, and nothing is cached across runs. It
never calls a provider and never creates a semantic claim (I2); where it
needs one it emits a typed Question instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.artifacts import Finding
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph, cited_segments, resolve_graph_segments
from ai.services.grounding import ANCHORED, STRUCTURAL, ground_graph, units
from ai.services.reconcile import questions as q
from ai.services.reconcile.coverage import CLAIMED, DISMISSED, UNCOVERED, compute_coverage, labelled_by
from ai.services.reconcile.identity import resolve_identities
from ai.services.reconcile.ledger import ADJUDICATION, COVERAGE, EXTRACTION, FRAMING, GROUNDING, Ledger
from ai.services.reconcile.mapping import _label_matches, map_assertions, map_entity_types, map_facts, typed_value
from ai.services.reconcile.normalise import build_clusters, current_observation, label_observation_sets
from ai.services.reconcile.questions import Question, QuestionOption, standard_options
from ai.services.reconcile.scope import (
    GENERAL_RELATIONSHIPS,
    TARGET_VERBS,
    evidence_selective_closure,
    removals,
    resolve_anchors,
    resolve_targets,
)
from ai.services.sources import mentions
from ai.services.reconcile.state import ReconcileState
from ai.services.semantic.index import SemanticModelIndex

_REASON_TEXT = {
    "intermediate_unidentified": "the source refers to the {via} involved only in general terms, without identifying it",
    "no_direct_representation": "the model can only express this through a {via}, which the source does not describe",
    "indirect_unclassified": "the model can only express this through a {via}",
}


# Target statuses that are blocks: requested work that was not done.
TARGET_BLOCKS = ("unframed", "unmapped", "undecided", "not_evidenced")
_SEARCHED = ("text_block", "list_item", "table_row")


@dataclass
class TargetGap:
    """An intent target the evidence has not yet yielded (enough) items for:
    an evidence gap at the level of the requested kind."""

    requirement_id: str  # "target:<target_id>"
    target_id: str
    kind: str  # object_type | relationship_type
    type_id: str
    type_label: str
    verb: str
    reason: str  # none_evidenced | uncovered
    segment_ids: list = field(default_factory=list)


def target_gap_id(target_id) -> str:
    return f"target:{target_id}"


@dataclass
class PlannedValue:
    owner: str  # cluster id or aid
    owner_kind: str  # object | relationship
    attribute_key: str
    value: object
    fid: str
    mode: str  # set | update
    decision_id: str


@dataclass
class Analysis:
    ledger: Ledger
    graph: EvidenceGraph
    clusters: object
    types: dict
    assertions: dict
    facts: dict
    attribute_sets: dict
    targets: dict
    anchors: dict
    scope: object
    removals: list
    identities: dict = field(default_factory=dict)
    label_sets: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    grounding: dict = field(default_factory=dict)
    values: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    probe_requests: list = field(default_factory=list)
    clarification: str = ""
    findings: list = field(default_factory=list)
    # aid -> open | undecidable | rejected_answer: why an undecided
    # assertion's mapping is undecided (honest blocking).
    decision_status: dict = field(default_factory=dict)
    # Gap Probe verdicts as OnyxJar accepts them now: a "found" whose claims
    # do not count toward the requirement is found_unsupported.
    probe_outcomes: dict = field(default_factory=dict)
    # Every intent target's status (see module docstring), in frame order.
    target_status: list = field(default_factory=list)

    def cluster_name(self, cid) -> str:
        cluster = self.clusters.clusters.get(cid)
        return cluster.name if cluster else cid

    @staticmethod
    def evidenced(requirement) -> int:
        """Claims the evidence makes for a requirement, whatever their fate."""

        return requirement.evidenced

    def pending_detail(self, requirement) -> dict:
        """Undecided evidence for a requirement, by why it is undecided."""

        counts: dict[str, int] = {}
        for aid in requirement.pending_decision:
            status = self.decision_status.get(aid, "open")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def coverage_of(self, requirement, missing_evidence) -> str:
        coverage = missing_evidence.get(requirement.requirement_id, "")
        if not coverage and self.probe_outcomes.get(requirement.requirement_id) == "found_unsupported":
            coverage = "partial"
        return coverage

    def cascade(self, cid, index) -> dict | None:
        """Why a blocked item can't be added, down to the cause: the chain from
        it through non-viable counterparts to the first item whose own
        requirement the evidence does not meet (or None when its own is)."""

        scope = self.scope
        frontier, seen = [(cid, [cid])], {cid}
        while frontier:
            node, path = frontier.pop(0)
            for requirement in scope.requirements.get(node, []):
                if self.evidenced(requirement) < requirement.minimum:
                    return {
                        "chain": [self.cluster_name(c) for c in path],
                        "cause": {
                            "entity": self.cluster_name(node),
                            "relationship_type_key": index.relationship_types[requirement.relationship_type_id].key,
                            "counterpart_type_key": index.object_types[requirement.counterpart_type_id].key,
                            "minimum": requirement.minimum,
                            "evidenced": self.evidenced(requirement),
                        },
                    }
            for requirement in scope.requirements.get(node, []):
                for aid in requirement.candidates:
                    mapping = self.assertions[aid]
                    other = mapping.object_cid if mapping.subject_cid == node else mapping.subject_cid
                    if other not in scope.viable and other not in seen:
                        seen.add(other)
                        frontier.append((other, [*path, other]))
        return None

    def blocked_targets(self, index, missing_evidence) -> list[dict]:
        """Per blocked target: each unmet requirement with BOTH what the
        evidence states (`evidenced`) and how much of it can be added
        (`viable`), and the cascade down to the root cause -- then every
        intent target that is itself a block (requested work not done)."""

        result = []
        for status in self.target_status:
            if status["status"] not in TARGET_BLOCKS:
                continue
            result.append({
                "target": status["type_label"] or status["excerpt"],
                "target_id": status["target_id"],
                "cluster_id": None,
                "type_key": status.get("type_key") or "",
                "reason": status["status"],
                "verb": status.get("verb", ""),
                "excerpt": status.get("excerpt", ""),
                "coverage": status.get("coverage", ""),
                "missing_requirements": [],
                "dependants": [],
                "cascade": None,
            })
        for root, dependants in sorted(self.scope.blocked_roots.items()):
            missing = []
            for requirement in self.scope.requirements.get(root, []):
                if requirement.viable_count >= requirement.minimum:
                    continue
                missing.append({
                    "relationship_type_key": index.relationship_types[requirement.relationship_type_id].key,
                    "counterpart_type_key": index.object_types[requirement.counterpart_type_id].key,
                    "minimum": requirement.minimum,
                    "evidenced": self.evidenced(requirement),
                    "viable": requirement.viable_count,
                    "found": self.evidenced(requirement),
                    "coverage": self.coverage_of(requirement, missing_evidence),
                    "unresolved_ambiguity": bool(requirement.ambiguous),
                    "constraint_conflict": len(requirement.conflicted),
                    "pending_decision": self.pending_detail(requirement),
                })
            for dependant in dependants:
                for requirement in self.scope.requirements.get(dependant, []):
                    if requirement.distinct(requirement.candidates) + requirement.canonical < requirement.minimum:
                        missing.append({
                            "entity": self.cluster_name(dependant),
                            "relationship_type_key": index.relationship_types[requirement.relationship_type_id].key,
                            "counterpart_type_key": index.object_types[requirement.counterpart_type_id].key,
                            "minimum": requirement.minimum,
                            "evidenced": self.evidenced(requirement),
                            "viable": requirement.viable_count,
                            "found": requirement.distinct(requirement.candidates) + requirement.canonical,
                            "coverage": self.coverage_of(requirement, missing_evidence),
                            "unresolved_ambiguity": bool(requirement.ambiguous),
                            "constraint_conflict": len(requirement.conflicted),
                            "pending_decision": self.pending_detail(requirement),
                        })
            result.append({
                "target": self.cluster_name(root),
                "cluster_id": root,
                "type_key": index.object_types[self.types[root].type_id].key,
                "reason": self.scope.outcomes.get(root, "blocked"),
                "missing_requirements": missing,
                "dependants": [self.cluster_name(d) for d in dependants],
                "cascade": self.cascade(root, index),
            })
        return result


def _register_claims(ledger: Ledger, state: ReconcileState, graph: EvidenceGraph) -> None:
    for item in graph.entities:
        ledger.claim(item.eid, step=EXTRACTION, basis=item.origin, subject_ids=[item.eid], excerpts=[p.excerpt for p in item.provenance])
    for item in graph.assertions:
        ledger.claim(item.aid, step=EXTRACTION, basis=item.origin, subject_ids=[item.aid], excerpts=[p.excerpt for p in item.provenance])
    for item in graph.facts:
        ledger.claim(item.fid, step=EXTRACTION, basis=item.origin, subject_ids=[item.fid], excerpts=[p.excerpt for p in item.provenance])
    for target in state.frame.targets:
        repaired = state.frame_repairs.get(target.target_id)
        ledger.claim(f"frame:{target.target_id}", step=FRAMING, basis="framing", subject_ids=[target.target_id], excerpts=[target.excerpt],
                     detail={"repaired_from": repaired} if repaired else {})
    for identifier, entry in state.unframed.items():
        # Not a claim: requested work whose framing could not be grounded.
        ledger.coverage(f"frame:{identifier}", step=FRAMING, basis="framing", subject_ids=[identifier], outcome="unframed",
                        detail={"reason": entry.get("reason", ""), "element": entry.get("element")})
    for anchor in state.frame.anchors:
        ledger.claim(f"frame:{anchor.anchor_id}", step=FRAMING, basis="framing", subject_ids=[anchor.anchor_id], excerpts=[anchor.excerpt])
    # Workflow records -- never claims: each claim's latest ingress fate, and
    # each Gap Probe verdict.
    latest = {}
    for entry in state.ingress_log:
        latest[entry["id"]] = entry
    for identifier, entry in latest.items():
        ledger.coverage(f"ingest:{identifier}", step=EXTRACTION, basis=entry["origin"], subject_ids=[identifier],
                        outcome=entry["outcome"], detail={"reason": entry.get("reason", ""), "local": entry.get("local")})
    for requirement_id, outcome in state.probe_outcomes.items():
        ledger.coverage(f"probe:{requirement_id}", step=EXTRACTION, basis="probe", subject_ids=[requirement_id], outcome=outcome,
                        detail={"coverage": state.missing_evidence.get(requirement_id, "")})
    for key, pin in state.pins.items():
        if not q.is_claim(pin):
            # Not a claim: an answer refused twice -- recorded, never relied on.
            ledger.coverage(f"open:{key}", step=ADJUDICATION, basis=pin.basis, subject_ids=[key], outcome=pin.basis,
                            detail={"reason": pin.reason} if pin.reason else {})
            continue
        ledger.claim(
            q.pin_decision_id(key), step=ADJUDICATION, basis=pin.basis, subject_ids=[key], outcome=pin.option_id,
            excerpts=[pin.excerpt] if pin.excerpt else [], detail={"note": pin.note} if pin.note else {},
        )


def _kind_of(index):
    def kind(entity):
        hinted = index.object_type_by_key(entity.type_hint) if entity.type_hint else None
        if hinted is not None:
            return hinted.id
        matches = _label_matches(index, entity.type_label)
        return matches[0].id if len(matches) == 1 else None

    return kind


def run_analysis(state: ReconcileState, *, index: SemanticModelIndex, bundle: EvidenceBundle | None = None) -> Analysis:
    bundle = bundle if bundle is not None else EvidenceBundle()
    # The same literal segment resolution every evidence stage applies
    # (idempotent): citations point at their segment wherever unambiguous.
    graph = resolve_graph_segments(state.graph.without(state.retracted), bundle)
    # Claimed answers only: a rejected answer is never a basis for anything.
    pins = q.claim_pins(state.pins)
    ledger = Ledger()
    _register_claims(ledger, state, graph)

    # L2 grounding (defence in depth: Extraction, Gap Probe and Verification
    # already refuse unanchored claims) -- anything unanchored takes no part.
    grounding = ground_graph(graph, bundle=bundle)
    for identifier, outcome in grounding.items():
        ledger.structural(
            f"ground:{identifier}", step=GROUNDING, basis="lexical", subject_ids=[identifier], inputs=[identifier], outcome=outcome,
            flags=["structural_support"] if outcome == STRUCTURAL else [],
        )
    unanchored = {i for i, outcome in grounding.items() if outcome not in (ANCHORED, STRUCTURAL)}
    if unanchored:
        graph = graph.without(unanchored)

    clusters = build_clusters(graph, pins=pins, ledger=ledger, kind_of=_kind_of(index))
    label_sets = label_observation_sets(graph, clusters, pins=pins, ledger=ledger)
    types = map_entity_types(clusters, index=index, pins=pins, ledger=ledger)
    assertions = map_assertions(
        graph, clusters, types, index=index, pins=pins, ledger=ledger,
        evidence_texts=lambda a: [u.text for u in units(a.provenance, bundle)],
    )
    identities = resolve_identities(clusters, types, index=index, pins=pins, ledger=ledger)
    facts, attribute_sets = map_facts(graph, clusters, types, assertions, index=index, pins=pins, ledger=ledger)
    targets = resolve_targets(state.frame, index=index, pins=pins, ledger=ledger)
    anchors = resolve_anchors(state.frame, index=index, ledger=ledger)
    scope = evidence_selective_closure(
        graph, clusters, types, identities, assertions, index=index, frame=state.frame, targets=targets, anchors=anchors,
        pins=pins, ledger=ledger, excluded=state.excluded, probe_outcomes=state.probe_outcomes, unframed=state.unframed,
    )
    found_removals = removals(graph, clusters, types, identities, assertions, scope, index=index, pins=pins)

    analysis = Analysis(
        ledger=ledger, graph=graph, clusters=clusters, types=types, assertions=assertions, facts=facts,
        attribute_sets=attribute_sets, targets=targets, anchors=anchors, scope=scope, removals=found_removals,
        identities=identities, label_sets=label_sets, grounding=grounding,
    )
    analysis.decision_status = _decision_status(assertions, state.pins)
    _coverage(analysis, state, bundle=bundle, index=index)
    _plan_values(analysis, index=index, pins=pins)
    _questions(analysis, state, index=index)
    _probe_verdicts(analysis, state, index=index)
    target_gaps = _target_work(analysis, state, bundle=bundle, index=index)
    _probe_requests(analysis, state, target_gaps)
    _findings(analysis, index=index)
    ambiguous_anchors = [a for a in anchors.values() if a.outcome == "ambiguous"]
    if ambiguous_anchors:
        names = ", ".join(f"'{a.name}' ({' or '.join(a.options)})" for a in ambiguous_anchors)
        analysis.clarification = f"The request names {names}, which matches more than one existing entity. Which one is meant?"
    return analysis


# -- coverage -----------------------------------------------------------------------


def _coverage(analysis: Analysis, state: ReconcileState, *, bundle: EvidenceBundle, index: SemanticModelIndex) -> None:
    """Coverage decisions -- never claims. Claimed rests on the claims that
    cite the segment; dismissed and uncovered are `coverage` decisions."""

    coverage = compute_coverage(bundle, analysis.graph, state.frame, index, state.dismissals)
    analysis.coverage = coverage
    ledger = analysis.ledger
    for segment_id, entry in coverage.items():
        detail = {"mentions": entry.named, "text": (bundle.segment(segment_id).text if bundle.segment(segment_id) else "")[:300]}
        if entry.status == CLAIMED:
            ledger.structural(f"cover:{segment_id}", step=COVERAGE, basis="deterministic", subject_ids=[segment_id],
                              inputs=entry.cited_by, outcome=CLAIMED, detail=detail)
        elif entry.status == DISMISSED:
            ledger.coverage(f"cover:{segment_id}", step=COVERAGE, basis="extraction", subject_ids=[segment_id], outcome=DISMISSED,
                            detail={**detail, "reason": entry.reason}, flags=["dismissed_target_evidence"] if entry.flagged else [])
            if entry.flagged:
                analysis.findings.append(Finding(
                    severity="warning",
                    message=f"Evidence mentioning {', '.join(repr(n) for n in entry.named)} was set aside as not relevant "
                            f"({entry.reason or 'no reason given'}): \"{detail['text'][:160]}\"",
                ))
        else:
            flags = ["not_extracted"] if segment_id in state.unextracted else []
            ledger.coverage(f"cover:{segment_id}", step=COVERAGE, basis="deterministic", subject_ids=[segment_id], outcome=UNCOVERED,
                            detail=detail, flags=flags)
            if entry.named:
                analysis.findings.append(Finding(
                    severity="warning",
                    message=f"Evidence mentioning {', '.join(repr(n) for n in entry.named)} was not accounted for: \"{detail['text'][:160]}\"",
                ))


# -- attribute values -----------------------------------------------------------


def _plan_values(analysis: Analysis, *, index: SemanticModelIndex, pins: dict) -> None:
    scope = analysis.scope
    for (owner, attribute_key), obs_set in sorted(analysis.attribute_sets.items()):
        if owner in analysis.clusters.clusters:
            if owner not in scope.needed:
                continue
            owner_kind = "object"
            type_id = analysis.types[owner].type_id
        else:
            if owner not in scope.selected_assertions:
                continue
            owner_kind = "relationship"
            type_id = analysis.assertions[owner].relationship_type_id
        attribute = index.attribute(type_id, attribute_key)
        status, chosen = current_observation(obs_set, pins=pins)
        set_decision = f"obs:attribute:{obs_set.set_key}"
        decision_id = f"value:{owner}:{attribute_key}"
        inputs = [set_decision, *(analysis.facts[f].decision_id for f in obs_set.fids if f in analysis.facts)]
        inputs += q.pin_inputs(q.key("value_selection", obs_set.set_key), pins)
        if status != "set":
            analysis.ledger.structural(decision_id, step="scope", subject_ids=[owner], inputs=inputs, outcome=status, detail={"attribute_key": attribute_key})
            continue
        value = typed_value(chosen.value, attribute) if attribute else None
        if value is None:
            analysis.ledger.structural(decision_id, step="scope", subject_ids=[owner], inputs=inputs, outcome="not_representable", detail={"attribute_key": attribute_key, "value": chosen.value})
            continue
        mode, outcome = "set", "set"
        identity = analysis.identities.get(owner) if owner_kind == "object" else None
        if identity is not None and identity.outcome in ("existing", "reactivate"):
            canonical = index.objects[identity.object_id].attributes.get(attribute_key)
            change_key = q.key("value_change", owner, attribute_key)
            if canonical == value:
                mode, outcome = None, "already_consistent"
            elif canonical in (None, ""):
                mode, outcome = "update", "update"
            else:
                pin = pins.get(change_key)
                inputs += q.pin_inputs(change_key, pins)
                if pin is not None and pin.option_id == "update":
                    mode, outcome = "update", "update"
                elif pin is not None:
                    mode, outcome = None, "kept"
                else:
                    mode, outcome = None, "question"
                    analysis.questions.append(Question(
                        question_id=change_key, kind="value_change", subject_ids=[owner, chosen.fid],
                        prompt=(
                            f"The model records {attribute_key} = {canonical!r} for '{analysis.cluster_name(owner)}'; the evidence "
                            f"says {chosen.value!r}. Is this a change to the current value?"
                        ),
                        options=[QuestionOption(option_id="update", label="Yes: the value has changed"),
                                 QuestionOption(option_id="keep", label="No: keep the recorded value"),
                                 QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
                        excerpts=[p.excerpt for p in chosen.provenance],
                    ))
        analysis.ledger.structural(
            decision_id, step="scope", subject_ids=[owner], inputs=[*inputs, chosen.fid], outcome=outcome,
            detail={"attribute_key": attribute_key, "value": value},
        )
        if mode:
            analysis.values.append(PlannedValue(owner, owner_kind, attribute_key, value, chosen.fid, mode, decision_id))


# -- questions --------------------------------------------------------------------


def _excerpts(provenance) -> list[str]:
    return [p.excerpt for p in provenance][:3]


def _questions(analysis: Analysis, state: ReconcileState, *, index: SemanticModelIndex) -> None:
    scope = analysis.scope
    graph = analysis.graph
    clusters = analysis.clusters
    in_scope = scope.tentative | scope.anchor_clusters
    target_types = {t.type_id for t in analysis.targets.values() if t.outcome == "mapped"}
    neighbours = set()
    for mapping in analysis.assertions.values():
        ends = {mapping.subject_cid, mapping.object_cid}
        if ends & in_scope:
            neighbours |= ends
    material = in_scope | neighbours
    questions = analysis.questions

    def ask(question: Question):
        if question.question_id not in state.pins:
            questions.append(question)

    for target in analysis.targets.values():
        if target.outcome == "ambiguous":
            frame_target = next(t for t in state.frame.targets if t.target_id == target.target_id)
            ask(Question(
                question_id=q.key("target_type", target.target_id), kind="target_type", subject_ids=[target.target_id],
                prompt=f"The request asks to {target.verb} '{frame_target.type_label}'. Which kind of model entity is meant?",
                options=standard_options([QuestionOption(option_id=o, label=o) for o in target.options]),
                excerpts=[frame_target.excerpt],
            ))

    for a, b in clusters.possible_same_as:
        cid_a, cid_b = clusters.by_eid[a], clusters.by_eid[b]
        if not ({cid_a, cid_b} & material):
            continue
        entity_a, entity_b = graph.entity(a), graph.entity(b)
        ask(Question(
            question_id=q.key("coreference", a, b), kind="coreference", subject_ids=[a, b],
            prompt=f"Are '{entity_a.name}' ({entity_a.type_label}) and '{entity_b.name}' ({entity_b.type_label}) the same real-world entity?",
            options=[QuestionOption(option_id="same", label="Same entity"), QuestionOption(option_id="distinct", label="Different entities"),
                     QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
            excerpts=[*_excerpts(entity_a.provenance), *_excerpts(entity_b.provenance)],
        ))

    for cid, mapping in analysis.types.items():
        if mapping.outcome != "ambiguous":
            continue
        if cid not in material and not (set(mapping.options) & {index.object_types[t].key for t in target_types if t in index.object_types}):
            continue
        cluster = clusters.clusters[cid]
        ask(Question(
            question_id=q.key("entity_type", cid), kind="entity_type", subject_ids=[cid],
            prompt=f"Which kind of model entity is '{cluster.name}' (described as {', '.join(cluster.type_labels)})?",
            options=standard_options([QuestionOption(option_id=o, label=o, detail=index.object_type_by_key(o).description if index.object_type_by_key(o) else "") for o in mapping.options]),
            excerpts=_excerpts(cluster.provenance),
        ))

    patterns: dict[str, list] = {}
    for aid, mapping in analysis.assertions.items():
        if mapping.outcome == "ambiguous" and ({mapping.subject_cid, mapping.object_cid} & in_scope):
            patterns.setdefault(mapping.pattern_key or q.key("assertion_mapping", aid), []).append(aid)
    for pattern_key, aids in patterns.items():
        first = analysis.assertions[aids[0]]
        subject_kind = index.object_types[analysis.types[first.subject_cid].type_id].key
        object_kind = index.object_types[analysis.types[first.object_cid].type_id].key
        predicate = graph.assertion(aids[0]).predicate
        examples = "; ".join(
            f"'{analysis.cluster_name(analysis.assertions[a].subject_cid)}' {predicate} '{analysis.cluster_name(analysis.assertions[a].object_cid)}'"
            for a in aids[:3]
        )
        options = []
        for option in first.options:
            key, _, orientation = option.partition(":")
            relationship_type = index.relationship_type_by_key(key)
            reading = (f"<{subject_kind}> {key} <{object_kind}>" if orientation == "as_stated"
                       else f"<{object_kind}> {key} <{subject_kind}> (the converse of the stated wording)")
            options.append(QuestionOption(option_id=option, label=reading, detail=relationship_type.description if relationship_type else ""))
        ask(Question(
            question_id=pattern_key, kind="assertion_mapping", subject_ids=aids,
            prompt=(
                f"The evidence says a {subject_kind} '{predicate}' a {object_kind} ({len(aids)} statement(s), e.g. {examples}). "
                "Which model relationship (if any) does that wording mean?"
            ),
            options=standard_options(options),
            excerpts=[e for a in aids[:3] for e in _excerpts(graph.assertion(a).provenance)],
        ))

    for aid, mapping in analysis.assertions.items():
        assertion = graph.assertion(aid)
        if not ({mapping.subject_cid, mapping.object_cid} & in_scope):
            continue
        subject, obj = analysis.cluster_name(mapping.subject_cid), analysis.cluster_name(mapping.object_cid)
        if mapping.outcome == "indirect" and mapping.reason == "indirect_unclassified" and "unresolved_ambiguity" not in mapping.flags:
            via = ", ".join(sorted({p["via_type"] for p in mapping.paths}))
            ask(Question(
                question_id=q.key("indirect_classification", aid), kind="indirect_classification", subject_ids=[aid],
                prompt=(
                    f"The evidence says '{subject}' {assertion.predicate} '{obj}'. The model can only connect these through a {via}. "
                    f"Does the source's wording refer to a {via} (without identifying it), or does it state a direct relationship?"
                ),
                options=[QuestionOption(option_id="refers_to_intermediate", label=f"It refers to an unidentified {via}"),
                         QuestionOption(option_id="direct_statement", label="It states a direct relationship"),
                         QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
                excerpts=_excerpts(assertion.provenance),
            ))

    for cid, identity in analysis.identities.items():
        if identity.outcome != "ambiguous" or not (cid in in_scope or analysis.types[cid].type_id in target_types):
            continue
        cluster = clusters.clusters[cid]
        type_key = index.object_types[analysis.types[cid].type_id].key
        options = []
        for option in identity.options:
            if option == q.NEW:
                options.append(QuestionOption(option_id=q.NEW, label="A new entity not yet in the model"))
            else:
                obj = index.object_by_key(analysis.types[cid].type_id, option)
                options.append(QuestionOption(option_id=option, label=f"Existing {type_key} '{obj.name}'" + ("" if obj.is_active else " (retired)"), detail=f"{type_key}:{option}"))
        options.append(QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence"))
        ask(Question(
            question_id=q.key("identity", cid), kind="identity", subject_ids=[cid],
            prompt=f"Is the evidence's '{cluster.name}' one of these existing {type_key} entities, or a new one?",
            options=options, excerpts=_excerpts(cluster.provenance),
        ))

    for fid, mapping in analysis.facts.items():
        if mapping.outcome != "ambiguous":
            continue
        if mapping.owner not in scope.needed and mapping.owner not in scope.selected_assertions:
            continue
        fact = graph.fact(fid)
        ask(Question(
            question_id=q.key("fact_attribute", fid), kind="fact_attribute", subject_ids=[fid],
            prompt=f"The evidence records {fact.label} = {fact.value!r} for '{analysis.cluster_name(mapping.owner)}'. Which attribute (if any) does that value belong to?",
            options=standard_options([QuestionOption(option_id=o, label=o) for o in mapping.options]),
            excerpts=_excerpts(fact.provenance),
        ))

    for (owner, attribute_key), obs_set in analysis.attribute_sets.items():
        if owner not in scope.needed and owner not in scope.selected_assertions:
            continue
        status, kind = current_observation(obs_set, pins=q.claim_pins(state.pins))
        if status != "question":
            continue
        observations = obs_set.remaining()
        listing = "; ".join(f"{o.value!r} ({graph.fact(o.fid).qualifiers.model_dump(exclude_none=True) or 'unqualified'}, {o.modality})" for o in observations)
        if kind == "conflict_classification":
            ask(Question(
                question_id=q.key("conflict_classification", obs_set.set_key), kind=kind, subject_ids=obs_set.fids,
                prompt=(
                    f"The evidence gives different values for {attribute_key} of '{analysis.cluster_name(owner)}': {listing}. "
                    "Do these contradict each other, or are they distinct observations (different time, context or condition)? "
                    "Do not choose which value is right."
                ),
                options=[QuestionOption(option_id="contradictory", label="They contradict each other"),
                         QuestionOption(option_id="distinct", label="They are distinct observations (cite what separates them)"),
                         QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
                excerpts=[e for o in observations for e in _excerpts(o.provenance)],
            ))
        else:
            ask(Question(
                question_id=q.key("value_selection", obs_set.set_key), kind=kind, subject_ids=obs_set.fids,
                prompt=f"The evidence gives several observations of {attribute_key} for '{analysis.cluster_name(owner)}': {listing}. Which one is the current value?",
                options=[*(QuestionOption(option_id=o.fid, label=repr(o.value)) for o in observations),
                         QuestionOption(option_id=q.NONE, label="Do not set this attribute"),
                         QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
                excerpts=[e for o in observations for e in _excerpts(o.provenance)],
            ))

    for removal in analysis.removals:
        if removal.confirmed or removal.question_key in state.pins:
            continue
        subject = analysis.cluster_name(removal.subject) if removal.kind == "object" else removal.subject
        item = graph.assertion(removal.subject) if removal.kind == "relationship" else None
        provenance = item.provenance if item else clusters.clusters[removal.subject].provenance
        ask(Question(
            question_id=removal.question_key, kind="removal_confirmation", subject_ids=[removal.subject],
            prompt=f"Does the evidence explicitly state that '{subject}' has ended, been removed or no longer applies? (Absence is never removal.)",
            options=[QuestionOption(option_id="confirm", label="Yes, the evidence explicitly states the removal"),
                     QuestionOption(option_id="reject", label="No"),
                     QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
            excerpts=_excerpts(provenance),
        ))

    for cid, requirement, aids in scope.over_asserted:
        relationship_type = index.relationship_types[requirement.relationship_type_id].key
        ask(Question(
            question_id=q.key("current_satisfier", cid, requirement.rule_id, requirement.side), kind="current_satisfier", subject_ids=list(aids),
            prompt=(
                f"'{analysis.cluster_name(cid)}' may have at most {requirement.maximum} '{relationship_type}' relationship(s), "
                "but the evidence asserts more. Which one is current?"
            ),
            options=[*(QuestionOption(option_id=aid, label=graph.assertion(aid).predicate + " " + analysis.cluster_name(
                analysis.assertions[aid].object_cid if analysis.assertions[aid].subject_cid == cid else analysis.assertions[aid].subject_cid)) for aid in aids),
                     QuestionOption(option_id=q.NONE, label="None of them"),
                     QuestionOption(option_id=q.UNDECIDABLE, label="Cannot be decided from the evidence")],
            excerpts=[e for aid in aids for e in _excerpts(graph.assertion(aid).provenance)],
        ))

    # Type-level answers change which other options exist at all, so they go
    # in a round of their own; never re-ask a question already answered.
    pending = [question for question in questions if question.question_id not in state.asked]
    phase_one = [question for question in pending if question.kind in q.PHASE_1]
    analysis.questions = phase_one or pending
    # Open decisions are coverage records, never claims: the workflow either
    # asks them (Adjudication) or reports them unadjudicated.
    for question in analysis.questions:
        analysis.ledger.coverage(f"open:{question.question_id}", step=ADJUDICATION, basis="deterministic",
                                 subject_ids=question.subject_ids, outcome="open", detail={"kind": question.kind})


def _decision_status(assertions: dict, pins: dict) -> dict:
    """Why each undecided assertion mapping is undecided: judged undecidable
    (a claim), an answer refused twice (rejected_answer), or never answered
    (open -- asked next, or unadjudicated if the budget is spent)."""

    status = {}
    for aid, mapping in assertions.items():
        if mapping.outcome == "unresolved_ambiguity":
            status[aid] = "undecidable"
        elif mapping.outcome == "ambiguous":
            keys = [q.key("assertion_mapping", aid), mapping.pattern_key]
            rejected = any(key and key in pins and pins[key].basis == "rejected_answer" for key in keys)
            status[aid] = "rejected_answer" if rejected else "open"
    return status


# -- probe requests / findings ---------------------------------------------------


def _probe_verdicts(analysis: Analysis, state: ReconcileState, *, index: SemanticModelIndex) -> None:
    """A "found" verdict stands only if one of its claims now counts toward
    that requirement (whatever its fate) -- a claim that merely involves the
    entity (a venue named beside a stage) does not fill the slot."""

    analysis.probe_outcomes = dict(state.probe_outcomes)
    requirements = {r.requirement_id: r for reqs in analysis.scope.requirements.values() for r in reqs}
    for requirement_id, outcome in state.probe_outcomes.items():
        requirement = requirements.get(requirement_id)
        if outcome == "found" and requirement_id.startswith("target:"):
            target = analysis.targets.get(requirement_id[len("target:"):])
            if target is not None and not _fills_target(analysis, target, state.probe_claims.get(requirement_id, []), index):
                analysis.probe_outcomes[requirement_id] = "found_unsupported"
                analysis.ledger.coverage(
                    f"probe:{requirement_id}", step=EXTRACTION, basis="probe", subject_ids=[requirement_id], outcome="found_unsupported",
                    detail={"reason": "none of its claims is an item of the requested kind",
                            "claim_ids": list(state.probe_claims.get(requirement_id, []))},
                )
            continue
        if outcome != "found" or requirement is None:
            continue
        counted = {*requirement.candidates, *requirement.ambiguous, *requirement.conflicted, *requirement.pending_decision}
        if counted & set(state.probe_claims.get(requirement_id, [])):
            continue
        analysis.probe_outcomes[requirement_id] = "found_unsupported"
        analysis.ledger.coverage(
            f"probe:{requirement_id}", step=EXTRACTION, basis="probe", subject_ids=[requirement_id], outcome="found_unsupported",
            detail={"reason": f"its claims do not relate it to any {index.object_types[requirement.counterpart_type_id].key}",
                    "claim_ids": list(state.probe_claims.get(requirement_id, []))},
        )


def _probe_requests(analysis: Analysis, state: ReconcileState, target_gaps=()) -> None:
    """Evidence gaps only: target gaps and unsatisfied requirements never
    probed, or probed once with an unsupported "found" (re-probed once,
    never more)."""

    analysis.probe_requests = [
        r for r in [*analysis.scope.unsatisfied, *target_gaps]
        if r.requirement_id not in state.probed
        or (analysis.probe_outcomes.get(r.requirement_id) == "found_unsupported" and r.requirement_id not in state.reprobed)
    ]


# -- intent targets ------------------------------------------------------------------


def _target_items(analysis: Analysis, target, index: SemanticModelIndex) -> tuple[list, list]:
    """-> (evidenced items of the target's kind, those selected to compile)."""

    if target.kind == "relationship_type":
        evidenced = [
            aid for aid, m in analysis.assertions.items()
            if (m.outcome == "mapped" and m.relationship_type_id == target.type_id)
            or (m.outcome in ("ambiguous", "unresolved_ambiguity") and target.type_id in _option_types(index, m))
        ]
        return evidenced, [aid for aid in evidenced if aid in analysis.scope.selected_assertions]
    evidenced = [
        cid for cid, m in analysis.types.items()
        if m.outcome == "mapped" and m.type_id == target.type_id and analysis.clusters.clusters[cid].specificity == "specific"
    ]
    return evidenced, [cid for cid in evidenced if cid in analysis.scope.needed]


def _option_types(index: SemanticModelIndex, mapping) -> set:
    """The relationship types an undecided assertion's options name."""

    found = (index.relationship_type_by_key(str(option).partition(":")[0]) for option in mapping.options)
    return {item.id for item in found if item is not None}


def _fills_target(analysis: Analysis, target, claim_ids, index: SemanticModelIndex) -> bool:
    """Whether a probe's "found" names an item of the requested kind."""

    for claim_id in claim_ids:
        if target.kind == "relationship_type":
            mapping = analysis.assertions.get(claim_id)
            if mapping is not None and ((mapping.outcome == "mapped" and mapping.relationship_type_id == target.type_id)
                                        or target.type_id in _option_types(index, mapping)):
                return True
            continue
        ends = [claim_id]
        assertion = analysis.graph.assertion(claim_id)
        if assertion is not None:
            ends = [assertion.subject_eid, assertion.object_eid]
        for eid in ends:
            cid = analysis.clusters.by_eid.get(eid)
            mapping = analysis.types.get(cid) if cid else None
            if mapping is not None and mapping.outcome == "mapped" and mapping.type_id == target.type_id:
                return True
    return False


def _labelled_segments(bundle: EvidenceBundle, labels) -> list[str]:
    """Where evidence of a kind would be: structured segments labelled by it
    (in their text or table header), any segment naming it, and everything
    under a heading naming it. Nothing labelled: the whole document (the
    pack bounds it, and its coverage then says how much was read)."""

    headings = {s.segment_id for s in bundle.segments() if s.kind == "heading" and mentions(s.text, labels)}
    found = [
        s.segment_id for s in bundle.segments()
        if s.kind in _SEARCHED and (labelled_by(s, labels) or mentions(s.text, labels) or headings & set(s.ancestor_ids))
    ]
    return found or [s.segment_id for s in bundle.segments() if s.kind in _SEARCHED]


def _target_work(analysis: Analysis, state: ReconcileState, *, bundle: EvidenceBundle, index: SemanticModelIndex) -> list:
    """Every intent target's status, ledgered; -> the target gaps."""

    gaps, statuses = [], []
    # Segments a reviewer judged (it retracted a claim citing them): read, so
    # never re-probed as "uncovered" -- a probe must not re-assert a retraction.
    reviewed = {
        sid for item in resolve_graph_segments(state.graph, bundle).items()
        if (getattr(item, "eid", None) or getattr(item, "aid", None) or getattr(item, "fid", None)) in state.retracted
        for sid in cited_segments(item)
    }
    for frame_target in state.frame.targets:
        target = analysis.targets.get(frame_target.target_id)
        status = {"target_id": frame_target.target_id, "type_label": frame_target.type_label, "verb": frame_target.verb,
                  "excerpt": frame_target.excerpt, "outcome": target.outcome if target else "unmapped", "evidenced": 0, "selected": 0}
        gap_id = target_gap_id(frame_target.target_id)
        if target is None or target.outcome == "unmapped":
            status["status"] = "unmapped"
        elif target.outcome == GENERAL_RELATIONSHIPS:
            status["status"] = "folded"
        elif target.outcome != "mapped":
            status["status"] = "undecided"
        elif target.verb not in TARGET_VERBS:
            status["status"] = "retire"
        else:
            item = index.type_by_id(target.type_id)
            status["type_key"] = item.key if item else ""
            evidenced, selected = _target_items(analysis, target, index)
            status.update(evidenced=len(evidenced), selected=len(selected))
            status["status"] = "evidenced" if evidenced else "not_evidenced"
            if not evidenced:
                status["coverage"] = state.missing_evidence.get(gap_id) or (
                    "partial" if analysis.probe_outcomes.get(gap_id) != "not_stated" else "complete")
            labels = [frame_target.type_label, item.name if item else ""]
            uncovered = [
                sid for sid, entry in analysis.coverage.items()
                if entry.status == UNCOVERED and target.kind == "object_type" and target.type_id in entry.type_ids and sid not in reviewed
            ]
            reason = "none_evidenced" if not evidenced else ("uncovered" if uncovered else "")
            segments = []
            if reason == "none_evidenced":
                segments = [sid for sid in _labelled_segments(bundle, [l for l in labels if l]) if sid not in reviewed]
            elif reason == "uncovered":
                segments = uncovered
            if segments:
                gaps.append(TargetGap(gap_id, frame_target.target_id, target.kind, target.type_id, frame_target.type_label,
                                      frame_target.verb, reason, segments))
        statuses.append(status)
        analysis.ledger.coverage(
            f"intent:{frame_target.target_id}", step=FRAMING, basis="deterministic", subject_ids=[frame_target.target_id],
            inputs=[f"frame:{frame_target.target_id}"], outcome=status["status"],
            detail={k: v for k, v in status.items() if k in ("evidenced", "selected", "coverage", "type_key")},
        )
    for identifier, entry in sorted(state.unframed.items()):
        element = entry.get("element") or {}
        statuses.append({
            "target_id": identifier, "type_label": element.get("type_label") or element.get("name") or "related relationships",
            "verb": element.get("verb", "add"), "excerpt": element.get("excerpt") or "", "outcome": "unframed",
            "status": "unframed", "reason": entry.get("reason", ""), "evidenced": 0, "selected": 0,
        })
    analysis.target_status = statuses
    return gaps


def _findings(analysis: Analysis, *, index: SemanticModelIndex) -> None:
    findings = analysis.findings
    scope = analysis.scope
    in_scope = scope.needed | scope.anchor_clusters | scope.tentative
    graph = analysis.graph

    for aid, mapping in analysis.assertions.items():
        if not ({mapping.subject_cid, mapping.object_cid} & in_scope):
            continue
        assertion = graph.assertion(aid)
        statement = f"'{analysis.cluster_name(mapping.subject_cid)}' {assertion.predicate} '{analysis.cluster_name(mapping.object_cid)}'"
        if mapping.outcome == "indirect":
            via = ", ".join(sorted({p["via_type"] for p in mapping.paths})) or "an entity the evidence does not identify"
            reason = _REASON_TEXT.get(mapping.reason, "it is not directly representable").format(via=via)
            findings.append(Finding(severity="info", message=f"Not changed: the evidence says {statement}, but {reason}."))
        elif mapping.outcome in ("unmapped", "unresolved_ambiguity") and mapping.reason != "endpoint_unmapped":
            findings.append(Finding(severity="info", message=f"Not changed: the evidence says {statement}, which the model has no relationship for."))
        elif mapping.outcome == "ambiguous":
            findings.append(Finding(severity="warning", message=f"Not changed: the evidence says {statement}, but which model relationship it means is unresolved."))

    for fid, mapping in analysis.facts.items():
        if mapping.owner not in scope.needed and mapping.owner not in scope.selected_assertions:
            continue
        fact = graph.fact(fid)
        owner = analysis.cluster_name(mapping.owner)
        if mapping.outcome in ("unmapped", "unresolved_ambiguity", "ambiguous"):
            findings.append(Finding(severity="info", message=f"Not represented in the model: {fact.label} = {fact.value} ({owner})"))

    for obs_set in analysis.attribute_sets.values():
        if obs_set.classification in ("conflict", "candidate_conflict") and (obs_set.subject in scope.needed or obs_set.subject in scope.selected_assertions):
            values = ", ".join(repr(o.value) for o in obs_set.remaining())
            findings.append(Finding(severity="warning", message=f"Conflicting evidence for {obs_set.prop} of '{analysis.cluster_name(obs_set.subject)}' ({values}); not changed."))

    for cid, outcome in scope.outcomes.items():
        if outcome == "omitted":
            findings.append(Finding(severity="info", message=f"Not changed: '{analysis.cluster_name(cid)}' is not needed by, or cannot be added for, the requested outcome."))

    for cid, requirement, aids, allowed in scope.constraint_conflicts:
        relationship = index.relationship_types[requirement.relationship_type_id].name
        counterpart = index.object_types[requirement.counterpart_type_id].name
        names = ", ".join(
            f"'{analysis.cluster_name(analysis.assertions[a].object_cid if analysis.assertions[a].subject_cid == cid else analysis.assertions[a].subject_cid)}'"
            for a in aids[:5]
        )
        findings.append(Finding(
            severity="material",
            message=(
                f"Not changed: the evidence relates {len(aids)} {counterpart}(s) ({names}) to '{analysis.cluster_name(cid)}' by "
                f"'{relationship}', but the model allows at most {requirement.maximum}. None was added -- consider changing the model."
            ),
        ))

    for aid, reason in scope.excluded_assertions.items():
        assertion = graph.assertion(aid)
        if reason == "historical":
            findings.append(Finding(severity="info", message=f"Recorded as historical, not current: {assertion.predicate} ({', '.join(p.excerpt for p in assertion.provenance[:1])})."))

    for cid, identity in analysis.identities.items():
        if identity.outcome in ("ambiguous", "unresolved_ambiguity") and cid in in_scope:
            findings.append(Finding(severity="warning", message=f"Not changed: whether '{analysis.cluster_name(cid)}' is an existing entity could not be resolved."))

    for anchor in analysis.anchors.values():
        if anchor.outcome == "unresolved":
            findings.append(Finding(severity="info", message=f"'{anchor.name}', named in the request, was not found in the model."))
