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

Bounds: `gap_probe` calls are rounds (AI_RECONCILE_GAP_PROBE_MAX_ROUNDS; a
round only covers requirements never probed before), `gap_probe_correction`
calls re-ask invalid claims / missing verdicts once
(AI_RECONCILE_GAP_PROBE_MAX_CORRECTION_CALLS) and never consume a round.
A `not_stated` verdict's coverage is the pack's (deterministic), not the
probe's own account. A `found` verdict stands only while one of the claims it
names counts toward that requirement (re-checked by every analysis); an
unsupported `found` makes the requirement eligible for ONE re-probe in a
later round, told why the earlier answer did not count.
"""

from __future__ import annotations

from ai.services.artifacts import Finding
from ai.services.evidence_graph import EvidenceGraph
from ai.services.reconcile.ingress import log
from ai.services.reconcile.near_miss import pack_claims, probe_payload
from ai.services.reconcile.responses import ProbeResult
from ai.services.stages import prompts
from ai.services.stages.extraction import absorb, correction_anchors, segment_payload
from ai.services.workflow.engine import Goto, Stage


def _public(requirement: dict) -> dict:
    return {k: v for k, v in requirement.items() if not k.startswith("_") and k != "coverage"}


def strip_mapping(graph: EvidenceGraph) -> EvidenceGraph:
    copy = graph.model_copy(deep=True)
    for assertion in copy.assertions:
        assertion.relationship_type_hint = None
        assertion.hint_orientation = "as_stated"
    for entity in copy.entities:
        entity.type_hint = None
    return copy


def incorporate(run, output: ProbeResult, *, replace_ids=frozenset()) -> None:
    rs = run.state.reconcile
    patch = strip_mapping(output.claims.with_origin("probe"))
    for identifier in replace_ids:
        rs.pending_items.pop(identifier, None)
    mapping = absorb(run, patch, origin="probe", replace_ids=replace_ids)

    for verdict in output.verdicts:
        payload = rs.probe_payloads.get(verdict.requirement_id)
        if payload is None or verdict.requirement_id in rs.probed:
            continue
        rs.probed.add(verdict.requirement_id)
        if verdict.status == "not_stated":
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
            # neither found nor a confirmed absence.
            rs.probe_outcomes[verdict.requirement_id] = "found_unsupported"
            rs.missing_evidence[verdict.requirement_id] = "partial"


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
    for requirement_id in rs.probe_payloads:
        if requirement_id not in rs.probed:
            rs.probed.add(requirement_id)
            rs.missing_evidence.setdefault(requirement_id, "partial")
    notes = []
    for identifier, (_, issues) in sorted(rs.pending_items.items()):
        detail = issues[0].message if issues else "it refers to a claim that could not be verified"
        notes.append(Finding(severity="info", message=f"Ignored probe claim '{identifier}': {detail}"))
        log(rs, identifier, origin="probe", outcome="dropped" if issues else "dropped_dependant", reason=detail)
    rs.pending_items = {}
    rs.notes = [*rs.notes, *notes]
    rs.reask_requirements = []
    return Goto("analysis")


def _next(run):
    rs = run.state.reconcile
    missing = [rid for rid in rs.probe_payloads if rid not in rs.probed]
    invalid = [i for i, (_, issues) in rs.pending_items.items() if issues]
    if (missing or invalid) and run.allows("gap_probe_correction"):
        rs.reask_requirements = missing
        return Goto("gap_probe_correction")
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
        requirements, segments, coverage = probe_payload(analysis.probe_requests, analysis, index=state.index, bundle=run.bundle)
        for requirement in requirements:
            requirement_id = requirement["requirement_id"]
            if requirement_id in rs.probed:
                # The one re-probe after an unsupported "found".
                rs.probed.discard(requirement_id)
                rs.reprobed.add(requirement_id)
                rs.probe_outcomes.pop(requirement_id, None)
                rs.missing_evidence.pop(requirement_id, None)
                named = ", ".join(rs.probe_claims.get(requirement_id, [])) or "no claim"
                if requirement.get("entity"):
                    requirement["previous_answer"] = (
                        f"An earlier answer said this was found, citing {named}, but those claims do not relate "
                        f"'{requirement['entity']['name']}' to any {requirement['looking_for']['kind']}. Report only what the segments state."
                    )
                else:
                    wanted = requirement["looking_for"].get("kind") or requirement["looking_for"].get("relationship")
                    requirement["previous_answer"] = (
                        f"An earlier answer said this was found, citing {named}, but none of those claims is a {wanted}. "
                        "Report only what the segments state."
                    )
        rs.probe_payloads = {r["requirement_id"]: {**r, "coverage": coverage[r["requirement_id"]]} for r in requirements}
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "requirements": [_public(r) for r in requirements],
            "segments": segments,
            "already_extracted": pack_claims(rs.analysis, [s["segment_id"] for s in segments]),
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
        for identifier, (item, issues) in rs.pending_items.items():
            if not issues:
                continue
            entry = {
                "id": identifier, "item": item.model_dump(mode="json"),
                "issues": [i.model_dump(mode="json", exclude_none=True) for i in issues],
                "cited_segments": segment_payload(run, sorted({p.segment_id for p in item.provenance if p.segment_id})),
            }
            anchors = correction_anchors(run, item, issues, stage=self.stage_id)
            if anchors is not None:
                entry["relationship_anchors"] = anchors
            invalid.append(entry)
        missing = [rs.probe_payloads[rid] for rid in rs.reask_requirements if rid in rs.probe_payloads]
        segment_ids = sorted({sid for r in missing for sid in r["segment_ids"]})
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "invalid_claims": invalid,
            "missing_verdicts": [_public(r) for r in missing],
            "segments": segment_payload(run, segment_ids),
            "already_extracted": pack_claims(rs.analysis, segment_ids),
        }

    def evaluate(self, run, output: ProbeResult):
        rs = run.state.reconcile
        incorporate(run, output, replace_ids={i for i, (_, issues) in rs.pending_items.items() if issues})
        return settle_probe(run)
