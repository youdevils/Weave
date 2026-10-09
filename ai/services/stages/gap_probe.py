"""
Reconcile stage -- Gap Probe (C6, revised): targeted re-extraction of the
evidence OnyxJar retrieved for each unsatisfied structural requirement
(ai.services.reconcile.near_miss), returning the same evidence-claim
contract as Extraction plus a verdict per requirement.

The probe never maps onto the ontology: any relationship/entity hint it
sends is stripped (mapping is OnyxJar's, I2). Its claims go through the same
validation as Extraction's (structure, literal provenance, L2 grounding) and
are appended; the deterministic pipeline then recomputes -- because a probe
re-extracts whole rows, a recovered entity normally arrives with what it
needs itself (a match with its teams and stage).

Bounds: `gap_probe` calls are rounds; a round only covers requirements never
probed before, and rounds are progress-driven (ai.services.stages.
reconcile_steps). Each round's output gets its own correction opportunity:
`gap_probe_correction` re-asks the round's invalid claims (except an
unanchored one no segment could anchor -- ai.services.stages.extraction.
no_anchor -- which is dropped without the re-ask), missing verdicts
and contract-breaking verdicts once (AI_RECONCILE_GAP_PROBE_MAX_CORRECTION_CALLS
per round -- an earlier round's correction never spends a later round's), and
never consumes a round. The correction's own output is not corrected again.

A verdict is part of the response contract: every claim a `found` verdict
names must be emitted in `claims` (this round) or shown in
`already_extracted`. One naming claims that exist nowhere
(`verdict_claim_missing`) is neither a finding nor an absence -- it is
re-asked in the round's correction, and only if it is still broken after
that does it count as an unsupported `found`.
A `not_stated` verdict's coverage is the pack's (deterministic), not the
probe's own account -- unless the requirement's own pack holds labelled
evidence (ai.services.reconcile.near_miss: layout associating the entity with
the counterpart's kind), which contradicts it: such a verdict is
`not_stated_contested` (partial coverage) and earns ONE re-probe, told which
segments and which header/heading. A second `not_stated` stands. A `found` verdict stands only while one of the claims it
names counts toward that requirement (re-checked by every analysis); an
unsupported `found` makes the requirement eligible for ONE re-probe in a
later round, told why the earlier answer did not count.
"""

from __future__ import annotations

from ai.services.artifacts import Finding
from ai.services.evidence_graph import EvidenceGraph, item_id
from ai.services.feedback import AIIssue, issue
from ai.services.reconcile.ingress import log
from ai.services.reconcile.near_miss import pack_claims, probe_payload
from ai.services.reconcile.responses import ProbeResult
from ai.services.stages import prompts
from ai.services.stages.extraction import absorb, cited_payload, correction_anchors, no_anchor, segment_payload
from ai.services.stages.reconcile_steps import affords_recovery, note_shortfall
from ai.services.workflow.engine import Goto, Stage


def _public(requirement: dict) -> dict:
    return {k: v for k, v in requirement.items() if not k.startswith("_") and k != "coverage"}


def _pack_ids(already: dict) -> set:
    return {e["eid"] for e in already.get("entities", [])} | {a["aid"] for a in already.get("assertions", [])}


def strip_mapping(graph: EvidenceGraph) -> EvidenceGraph:
    copy = graph.model_copy(deep=True)
    for assertion in copy.assertions:
        assertion.relationship_type_hint = None
        assertion.hint_orientation = "as_stated"
    for entity in copy.entities:
        entity.type_hint = None
    return copy


def verdict_issue(verdict, emitted, shown, *, needs_assertion=False, is_assertion=lambda claim_id: False) -> AIIssue | None:
    """The response contract of a `found` verdict:

      - every claim it names is one this response emits or one it was shown;
      - it names at least one claim stating what was found -- for a
        requirement (a relationship to an entity) an assertion, for a target
        gap any claim. A "found" naming none is self-contradictory: it is
        never a result, and is re-asked in the round's correction.

    (Whether the claims it names really count is the analysis' question.)"""

    if verdict.status != "found":
        return None
    missing = [c for c in verdict.claim_ids if c not in emitted and c not in shown]
    if missing:
        message = (f"This verdict cites {', '.join(missing)}, which {'is' if len(missing) == 1 else 'are'} in neither `claims` nor "
                   "`already_extracted`. Emit those claims in `claims` with valid citations, cite an `already_extracted` claim "
                   "instead, or change the verdict.")
        return issue("verdict_claim_missing", message, item_id=verdict.requirement_id)
    stating = [c for c in verdict.claim_ids if is_assertion(c)] if needs_assertion else list(verdict.claim_ids)
    if stating:
        return None
    what = "an assertion stating that relationship" if needs_assertion else "a claim"
    if verdict.claim_ids:
        failure = f"names only {', '.join(verdict.claim_ids)}, none of which is {what}"
    else:
        failure = f"names no claim stating it ({what}): nothing was emitted for it"
    message = (f"This verdict says found, but {failure}. Emit the claim in `claims`, citing the segments that state it (or "
               "name an `already_extracted` assertion that does), and name it in `claim_ids` -- or, if the segments do not "
               "state it, answer not_stated.")
    return issue("verdict_without_claims", message, item_id=verdict.requirement_id)


def previous_answer(requirement: dict, named_claims, contested=None) -> str:
    """Why a re-probed requirement's earlier answer did not count -- told as
    it was: claims that don't state what is looked for, no claim at all, or
    (`contested`) a not_stated that its own labelled evidence contradicts."""

    wanted = requirement["looking_for"].get("kind") or requirement["looking_for"].get("relationship")
    if contested:
        return _contested_answer(requirement, wanted, contested)
    if not named_claims:
        what = f"relating '{requirement['entity']['name']}' to a {wanted}" if requirement.get("entity") else f"for a {wanted}"
        return (f"An earlier answer said this was found but emitted no claim stating it, so nothing {what} was recorded. "
                "If the segments state it, emit the claim in `claims` with citations to those segments and name it in "
                "`claim_ids`; if they do not, answer not_stated.")
    named = ", ".join(named_claims)
    if requirement.get("entity"):
        return (f"An earlier answer said this was found, citing {named}, but those claims do not relate "
                f"'{requirement['entity']['name']}' to any {wanted}. Report only what the segments state.")
    return f"An earlier answer said this was found, citing {named}, but none of those claims is a {wanted}. Report only what the segments state."


def _contested_answer(requirement: dict, wanted: str, contested) -> str:
    name = requirement["entity"]["name"]
    layout = []
    for entry in contested:
        if "column" in entry:
            layout.append(f"{entry['segment_id']} is a row under the header '{entry['header']}': in the same row as '{name}', "
                          f"its '{entry['column']}' cell reads '{entry['cell']}'")
        else:
            layout.append(f"{entry['segment_id']} is an item in the section '{entry['heading']}' under the heading '{entry['under']}'")
    return (f"An earlier answer said not_stated, but the layout of these segments associates '{name}' with a {wanted}: "
            + "; ".join(layout) + ". A cell in a column headed by a kind, or an item in a section headed by a kind, names an "
            "entity of that kind; a composite label naming several entities (e.g. 'Entity A v Entity B') is that entity's name, "
            "and the entities it names are named by the source too. If these segments state how '" + name + "' relates to it, "
            "emit that entity and the assertion relating '" + name + "' to it, citing these segments, and name the assertion in "
            "claim_ids; answer not_stated only if they do not state it.")


def incorporate(run, output: ProbeResult, *, replace_ids=frozenset()) -> None:
    rs = run.state.reconcile
    emitted = {item_id(i) for i in output.claims.items()}
    emitted_assertions = {a.aid for a in output.claims.assertions}
    patch = strip_mapping(output.claims.with_origin("probe"))
    for identifier in replace_ids:
        rs.pending_items.pop(identifier, None)
    mapping = absorb(run, patch, origin="probe", replace_ids=replace_ids)

    for verdict in output.verdicts:
        payload = rs.probe_payloads.get(verdict.requirement_id)
        if payload is None or verdict.requirement_id in rs.probed:
            continue
        broken = verdict_issue(
            verdict, emitted, rs.probe_shown_ids, needs_assertion=not payload.get("_target"),
            is_assertion=lambda c: c in emitted_assertions or rs.graph.assertion(c) is not None
            or hasattr((rs.pending_items.get(c) or (None,))[0], "aid"),
        )
        if broken is not None:
            # Not a verdict yet: left unprobed, so the round's correction re-asks it.
            rs.verdict_issues[verdict.requirement_id] = (verdict, [broken])
            continue
        rs.verdict_issues.pop(verdict.requirement_id, None)
        rs.probed.add(verdict.requirement_id)
        if verdict.status == "not_stated" and payload.get("_labelled") and verdict.requirement_id not in rs.reprobed:
            # Its own pack's layout says otherwise: not a confirmed absence yet.
            rs.probe_outcomes[verdict.requirement_id] = "not_stated_contested"
            rs.probe_contested[verdict.requirement_id] = list(payload["_labelled"])
            rs.missing_evidence[verdict.requirement_id] = "partial"
        elif verdict.status == "not_stated":
            rs.probe_outcomes[verdict.requirement_id] = "not_stated"
            rs.missing_evidence[verdict.requirement_id] = payload["coverage"]
        elif verdict.status == "ambiguous":
            rs.probe_outcomes[verdict.requirement_id] = "ambiguous"
        elif _supports(rs, payload, claim_ids := [mapping.get(c, c) for c in verdict.claim_ids]):
            rs.probe_outcomes[verdict.requirement_id] = "found"
            rs.probe_claims[verdict.requirement_id] = claim_ids
            rs.missing_evidence.pop(verdict.requirement_id, None)
        else:
            # A "found" that no accepted claim about this entity backs is
            # neither found nor a confirmed absence. What it named is kept for
            # the re-probe's account of why it did not count.
            rs.probe_outcomes[verdict.requirement_id] = "found_unsupported"
            rs.probe_claims[verdict.requirement_id] = claim_ids
            rs.missing_evidence[verdict.requirement_id] = "partial"
    # What this round emitted stays citable by the round's correction verdicts.
    rs.probe_shown_ids |= emitted | set(mapping.values())


def _supports(rs, payload, claim_ids) -> bool:
    if payload.get("_target"):
        # A target gap: any accepted claim, provisionally; whether it is an
        # item of the requested kind is re-checked by every analysis.
        return any(rs.graph.entity(c) or rs.graph.assertion(c) for c in claim_ids)
    entity_ids = set(payload.get("_entity_ids") or [])
    for claim_id in claim_ids:
        assertion = rs.graph.assertion(claim_id)
        if assertion is not None and {assertion.subject_eid, assertion.object_eid} & entity_ids:
            return True
    return False


def settle_probe(run):
    rs = run.state.reconcile
    notes = []
    for requirement_id, (verdict, issues) in sorted(rs.verdict_issues.items()):
        # Still naming no claim, or claims that were never given, after the
        # round's correction: neither found nor a confirmed absence. What it
        # named (nothing, for an empty "found") tells the re-probe why.
        rs.probed.add(requirement_id)
        rs.probe_outcomes[requirement_id] = "found_unsupported"
        rs.probe_claims[requirement_id] = list(verdict.claim_ids)
        rs.missing_evidence[requirement_id] = "partial"
        notes.append(Finding(severity="info", message=f"Ignored probe verdict for '{requirement_id}': {issues[0].message}"))
    rs.verdict_issues = {}
    for requirement_id in rs.probe_payloads:
        if requirement_id not in rs.probed:
            rs.probed.add(requirement_id)
            rs.missing_evidence.setdefault(requirement_id, "partial")
    for identifier, (_, issues) in sorted(rs.pending_items.items()):
        detail = issues[0].message if issues else "it refers to a claim that could not be verified"
        notes.append(Finding(severity="info", message=f"Ignored probe claim '{identifier}': {detail}"))
        log(rs, identifier, origin="probe", outcome="dropped" if issues else "dropped_dependant", reason=detail)
    rs.pending_items = {}
    rs.notes = [*rs.notes, *notes]
    rs.reask_requirements = []
    return Goto("analysis")


def _reasked_claims(run) -> list[str]:
    """The round's invalid claims its correction re-asks."""

    return [i for i, (item, issues) in run.state.reconcile.pending_items.items() if issues and not no_anchor(run, item, issues)]


def _next(run):
    rs = run.state.reconcile
    missing = [rid for rid in rs.probe_payloads if rid not in rs.probed]
    invalid = _reasked_claims(run)
    if (missing or invalid) and run.allows("gap_probe_correction") and affords_recovery(run):
        rs.reask_requirements = missing
        return Goto("gap_probe_correction")
    if (missing or invalid) and not affords_recovery(run):
        note_shortfall(rs, "probe_uncorrected", [*rs.budget_shortfall.get("probe_uncorrected", []), *missing, *invalid])
    return settle_probe(run)


class GapProbeStage(Stage):
    stage_id = "gap_probe"
    response_schema = ProbeResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.GAP_PROBE

    def build_input(self, run) -> dict:
        state = run.state
        rs = state.reconcile
        analysis = rs.analysis
        requirements, segments, coverage = probe_payload(analysis.probe_requests, analysis, index=state.index, bundle=run.bundle, scope=rs.prose_scope)
        for requirement in requirements:
            requirement_id = requirement["requirement_id"]
            if requirement_id in rs.probed:
                # The one re-probe after an unsupported "found" or a contested absence.
                contested = rs.probe_contested.get(requirement_id) if rs.probe_outcomes.get(requirement_id) == "not_stated_contested" else None
                rs.probed.discard(requirement_id)
                rs.reprobed.add(requirement_id)
                rs.probe_outcomes.pop(requirement_id, None)
                rs.missing_evidence.pop(requirement_id, None)
                requirement["previous_answer"] = previous_answer(requirement, rs.probe_claims.get(requirement_id, []), contested)
        rs.probe_payloads = {r["requirement_id"]: {**r, "coverage": coverage[r["requirement_id"]]} for r in requirements}
        rs.verdict_issues = {}
        already = pack_claims(rs.analysis, [s["segment_id"] for s in segments])
        rs.probe_shown_ids = _pack_ids(already)
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "requirements": [_public(r) for r in requirements],
            "segments": segments,
            "already_extracted": already,
        }

    def evaluate(self, run, output: ProbeResult):
        incorporate(run, output)
        return _next(run)


class GapProbeCorrectionStage(Stage):
    stage_id = "gap_probe_correction"
    response_schema = ProbeResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.GAP_PROBE + "\n\n" + prompts.GAP_PROBE_CORRECTION

    def build_input(self, run) -> dict:
        rs = run.state.reconcile
        invalid = []
        for identifier in _reasked_claims(run):
            item, issues = rs.pending_items[identifier]
            entry = {
                "id": identifier, "item": item.model_dump(mode="json"),
                "issues": [i.model_dump(mode="json", exclude_none=True) for i in issues],
                **cited_payload(run, item),
            }
            anchors = correction_anchors(run, item, issues, stage=self.stage_id)
            if anchors is not None:
                entry["relationship_anchors"] = anchors
            invalid.append(entry)
        reask = [rs.probe_payloads[rid] for rid in rs.reask_requirements if rid in rs.probe_payloads]
        missing = [r for r in reask if r["requirement_id"] not in rs.verdict_issues]
        invalid_verdicts = []
        for requirement in reask:
            if requirement["requirement_id"] not in rs.verdict_issues:
                continue
            verdict, issues = rs.verdict_issues[requirement["requirement_id"]]
            invalid_verdicts.append({
                "requirement": _public(requirement), "previous_verdict": verdict.model_dump(mode="json"),
                "issues": [i.model_dump(mode="json", exclude_none=True) for i in issues],
            })
        segment_ids = sorted({sid for r in reask for sid in r["segment_ids"]})
        already = pack_claims(rs.analysis, segment_ids)
        rs.probe_shown_ids |= _pack_ids(already)
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "invalid_claims": invalid,
            "missing_verdicts": [_public(r) for r in missing],
            "invalid_verdicts": invalid_verdicts,
            "segments": segment_payload(run, segment_ids),
            "already_extracted": already,
        }

    def evaluate(self, run, output: ProbeResult):
        rs = run.state.reconcile
        incorporate(run, output, replace_ids=set(_reasked_claims(run)))
        return settle_probe(run)
