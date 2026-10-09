"""
Verification v2 in readings mode: a bounded CAUSAL dossier (Phase 5 of
.Documentation/reconcile-architecture-plan.md, section 3.7) instead of the
whole historical ledger.

The reviewer answers two questions:

    Q1  are the decisions that CAUSED the proposed changes sound?
    Q2  are the decisions that PREVENTED other changes justified?

So the dossier carries, and only carries:

    causes_of_changes   per Reading slot the changes rest on: its choice, its
                        structural basis, how many changes it produced, a few
                        sample changes and every anomaly it left; plus the
                        prose claims and adjudicated answers changes rest on
    causes_of_blocks    per blocked item: its state, the requirements it
                        misses (each with its state), the upstream decisions
                        those rest on, and the structural / prose leads that
                        could challenge the block
    disputes            computed, never inferred by the model: a lead into a
                        `none` / undecided / unread element, a not_stated
                        verdict over a structural lead, a not_a_table on a
                        table that conforms well, repeated anomalies,
                        target-relevant prose left unread, and any
                        invariant violation
    ignored_structure / unread_structure / unread_prose
    open_decisions      questions the budget never reached
    segments            the evidence those entries cite -- nothing else

Its size grows with the decisions changes rest on, the blocked roots and the
disputes -- not with rows, and not with ledger families. Objections still
target decision ids (VerificationStage.route): `read:<slot id>` re-reads
every row that slot governs.
"""

from __future__ import annotations

from collections import Counter

from django.conf import settings

from ai.services.reconcile import readings as rd
from ai.services.reconcile import triage as tg
from ai.services.reconcile.coverage import UNCOVERED
from ai.services.reconcile.trace_policy import check_trace
from ai.services.sources import with_ancestors

SAMPLES_PER_SLOT = 3
ANOMALIES_PER_SLOT = 10


def _decision_payload(decision) -> dict:
    data = {"decision_id": decision.decision_id, "step": decision.step, "outcome": decision.outcome}
    if decision.excerpts:
        data["excerpts"] = list(decision.excerpts)[:3]
    if decision.options:
        data["options"] = [o["option_id"] for o in decision.options][:24]
    return data


def _chain(ledger, decision_ids) -> set:
    """Every decision a traced action transitively rests on."""

    seen, frontier = set(), list(decision_ids)
    while frontier:
        decision_id = frontier.pop()
        if decision_id in seen or ledger.get(decision_id) is None:
            continue
        seen.add(decision_id)
        frontier += list(ledger.get(decision_id).inputs)
    return seen


def _summary(action, names) -> str:
    data = action.model_dump(mode="json")
    if data.get("kind") == "create_object":
        return f"create {data['type']['key']} '{data.get('name')}'"
    if data.get("kind") == "create_relationship":
        return f"{names(data['subject'])} -{data['relationship_type']['key']}-> {names(data['object'])}"
    return data.get("kind", "")


def disputes(analysis, state, *, bundle, change_set=None, trace=None) -> list[dict]:
    """Deterministic disputes (module docstring)."""

    found = []
    for requirement_id, item in sorted(analysis.triage.items()):
        for lead in item.structural:
            if lead["route"] in (tg.QUESTION, tg.UNREAD):
                found.append({"kind": "lead_into_" + ("unread" if lead["route"] == tg.UNREAD else "undecided_or_none"),
                              "requirement_id": requirement_id, "segment_id": lead["segment_id"], "slot_id": lead["slot_id"],
                              "reason": lead["reason"]})
        if analysis.probe_outcomes.get(requirement_id) == "not_stated" and item.route in (tg.QUESTION, tg.UNREAD, tg.ANOMALY):
            found.append({"kind": "not_stated_over_structural_lead", "requirement_id": requirement_id,
                          "segment_ids": [lead["segment_id"] for lead in item.structural]})
    document = bundle.document()
    from ai.services.document.queries import structurally_conforms

    for reading in analysis.readings:
        if reading.status == rd.NOT_A_TABLE and reading.element_id in document.tables:
            table = document.tables[reading.element_id]
            conforming = sum(1 for r in table.rows if structurally_conforms(r, table.signature).conforms)
            if table.has_header and conforming >= 2:
                found.append({"kind": "not_a_table_on_a_conforming_table", "decision_id": f"read:{reading.reading_id}",
                              "reason": reading.not_a_table_reason, "conforming_rows": conforming})
    repeated = Counter((a.slot_id, a.reason) for a in analysis.anomalies if a.check == "reading_conforms")
    for (slot_id, reason), count in sorted(repeated.items()):
        if count >= 2:
            found.append({"kind": "repeated_anomaly", "slot_id": slot_id, "reason": reason, "rows": count})
    for segment_id, entry in sorted(analysis.coverage.items()):
        if entry.status == UNCOVERED and entry.named:
            found.append({"kind": "unread_target_prose", "segment_id": segment_id, "mentions": entry.named})
    if change_set is not None and trace is not None:
        for problem in check_trace(change_set, trace, analysis):
            found.append({"kind": "invariant_violation", "message": problem.message})
    return found


def review_dossier(run) -> dict:
    state = run.state
    rs = state.reconcile
    analysis = rs.analysis
    ledger = analysis.ledger
    change_set, trace = rs.compiled if rs.compiled else (state.change_set, None)
    actions = list(change_set.actions) if change_set else []
    tokens = {a.token: a.name for a in actions if getattr(a, "kind", "") == "create_object"}

    def names(ref):
        return f"'{tokens.get(ref.get('token'), ref.get('key') or ref.get('token'))}'"

    cited: list[str] = []

    def cite(segment_ids):
        cited.extend(s for s in segment_ids if s and s not in cited)

    # Q1 -- what caused each change, grouped by the decision that caused it.
    by_slot: dict[str, list] = {}
    prose_claims: dict[str, dict] = {}
    adjudicated: dict[str, dict] = {}
    for action in actions:
        entry = trace.entries.get(action.action_id) if trace else None
        chain = _chain(ledger, [*(entry.decision_ids if entry else []), *(entry.evidence_ids if entry else [])])
        summary = {"action_id": action.action_id, "change": _summary(action, names)}
        for decision_id in sorted(chain):
            decision = ledger.get(decision_id)
            if decision.step == rd.READING and decision.kind == "claim":
                by_slot.setdefault(decision_id, []).append(summary)
            elif decision.kind == "claim" and decision.step == "extraction":
                item = analysis.graph.item(decision_id)
                entry_ = prose_claims.setdefault(decision_id, {**_decision_payload(decision), "changes": []})
                entry_["changes"].append(action.action_id)
                if item is not None:
                    cite([p.segment_id for p in item.provenance])
            elif decision.kind == "claim" and decision.decision_id.startswith("adj:"):
                adjudicated.setdefault(decision_id, {**_decision_payload(decision), "changes": []})["changes"].append(action.action_id)
    readings_caused = []
    for decision_id, changes in sorted(by_slot.items()):
        decision = ledger.get(decision_id)
        slot_id = decision.subject_ids[0] if decision.subject_ids else ""
        anomalies = [{"row_id": a.row_id, "reason": a.reason} for a in analysis.anomalies if a.slot_id == slot_id]
        readings_caused.append({
            **_decision_payload(decision), "detail": decision.detail, "changes_resting_on_it": len(changes),
            "sample_changes": changes[:SAMPLES_PER_SLOT], "anomalies": anomalies[:ANOMALIES_PER_SLOT],
            "anomalies_total": len(anomalies),
        })
        cite(rd.subject_segments(slot_id, analysis.readings, run.bundle.document())[:2])

    # Q2 -- what prevented the rest.
    blocks = []
    for blocked in state.blocked_targets:
        root = blocked.get("cluster_id")
        upstream = []
        if root:
            requirement_ids = [r.requirement_id for r in analysis.scope.requirements.get(root, [])]
            for requirement_id in requirement_ids:
                item = analysis.triage.get(requirement_id)
                if item is not None:
                    cite([lead["segment_id"] for lead in item.structural][:3] + item.prose[:2])
            members = analysis.clusters.clusters[root].member_eids if root in analysis.clusters.clusters else []
            for decision_id in sorted(_chain(ledger, [f"type:{root}", f"ident:{root}", *members])):
                decision = ledger.get(decision_id)
                if decision.kind == "claim" and decision.step in (rd.READING, "adjudication"):
                    upstream.append(_decision_payload(decision))
        leads = []
        for requirement in analysis.scope.requirements.get(root, []) if root else []:
            item = analysis.triage.get(requirement.requirement_id)
            if item is not None and (item.structural or item.prose):
                leads.append({"requirement_id": requirement.requirement_id, "route": item.route,
                              "structural": item.structural[:5], "prose": item.prose[:5]})
        blocks.append({
            "target": blocked.get("target"), "state": blocked.get("state", ""), "reason": blocked.get("reason"),
            "missing_requirements": blocked.get("missing_requirements", []), "cascade": blocked.get("cascade"),
            "upstream_decisions": upstream[:12], "leads": leads,
        })

    coverage = analysis.structured_coverage
    found_disputes = disputes(analysis, rs, bundle=run.bundle, change_set=change_set, trace=trace)
    for dispute in found_disputes:
        cite([dispute.get("segment_id"), *dispute.get("segment_ids", [])])
    unread_prose = [{"segment_id": s, "mentions": e.named} for s, e in sorted(analysis.coverage.items()) if e.status == UNCOVERED]
    cite([u["segment_id"] for u in unread_prose])

    budget, segments = settings.AI_VERIFY_EVIDENCE_MAX_CHARS, []
    for segment in with_ancestors(run.bundle, cited):
        if len(segment.text) <= budget:
            segments.append(segment.context())
            budget -= len(segment.text)
    feedback = state.feedback.get("verification", [])
    previous = state.previous_output.get("verification") if feedback else None
    return {
        "stage": "verification",
        "intent": run.intent.text,
        "model": run.model_context(),
        "intent_frame": rs.frame.model_dump(mode="json"),
        "questions": {
            "Q1": "Are the decisions that caused the proposed changes sound?",
            "Q2": "Are the decisions that prevented other changes justified?",
        },
        "causes_of_changes": {
            "reading_decisions": readings_caused,
            "prose_claims": list(prose_claims.values())[:30],
            "adjudicated_answers": list(adjudicated.values())[:30],
            "changes_total": len(actions),
        },
        "causes_of_blocks": blocks,
        "disputes": found_disputes,
        "ignored_structure": [{"dem_id": d, "slot_id": e["slot_id"]} for d, e in sorted(coverage.items()) if e["status"] == rd.IGNORED],
        "unread_structure": [{"dem_id": d, "reading_id": e["reading_id"]} for d, e in sorted(coverage.items()) if e["status"] == rd.UNREAD],
        "unread_prose": unread_prose,
        "open_decisions": [{"question_id": x.question_id, "kind": x.kind, "prompt": x.prompt, "options": [o.option_id for o in x.options]}
                           for x in analysis.questions],
        "segments": segments,
        "feedback": [item.model_dump(mode="json", exclude_none=True) for item in feedback],
        "previous_output": previous.model_dump(mode="json") if previous is not None else None,
    }
