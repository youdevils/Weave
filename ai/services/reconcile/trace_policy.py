"""
TracePolicy (C9): the evidence-pipeline rules a compiled ChangeSet must meet
before it reaches the mutation resolver -- the backstop for I2.

    - every claim an action rests on passed L2 grounding (anchored, or
      structural with a structural citation)
    - every action has a trace, and every decision it cites rests
      (transitively) on a claim; the ledger as a whole has no structural
      decision that rests on nothing (trace closure)
    - a created Object rests on a `new` identity and a `mapped` type
    - a created relationship rests on a `mapped` assertion
    - a retirement rests on a removal claim with a confirmed
      removal_confirmation answer
    - no value comes from a set classified as a conflict
    - nothing blocked or blocked-dependent is compiled
    - (readings mode) nothing rests on a Reading slot that is not decided
      (undecidable / none / not_a_table), and every Reading-derived item
      carries basis_refs naming every Reading its ledgered inputs come from

For compiled actions these hold by construction; a violation is an OnyxJar
defect, reported as an issue and never sent to a provider.
"""

from __future__ import annotations

from ai.services.feedback import AIIssue, issue
from ai.services.reconcile.analysis import Analysis
from ai.services.reconcile.compiler import ChangeTrace


_UNDECIDED_READ = ("undecidable", "none", "not_a_table", "value")


def _reading_violations(ledger, decision_ids, graph) -> list[str]:
    """Reading slots a traced chain rests on that are not decided, and
    Reading-derived items whose basis_refs do not account for their inputs."""

    problems, seen, frontier = [], set(), list(decision_ids)
    while frontier:
        decision_id = frontier.pop()
        if decision_id in seen:
            continue
        seen.add(decision_id)
        decision = ledger.get(decision_id)
        if decision is None:
            continue
        if decision.step == "reading" and decision.kind == "claim" and decision.outcome in _UNDECIDED_READ:
            problems.append(f"'{decision_id}' is not a decided Reading slot ({decision.outcome}).")
        if decision.step == "reading" and decision.kind == "structural":
            item = graph.item(decision_id) if graph is not None else None
            refs = {r.split("@")[0] for r in (getattr(item, "basis_refs", None) or [])}
            readings = {(ledger.get(i).detail or {}).get("reading_id") for i in decision.inputs if ledger.get(i) is not None}
            if not refs or not decision.inputs or (readings - {None}) - refs:
                problems.append(f"'{decision_id}' does not name every Reading it rests on in basis_refs.")
        frontier += list(decision.inputs)
    return problems


def check_trace(change_set, trace: ChangeTrace, analysis: Analysis) -> list[AIIssue]:
    ledger = analysis.ledger
    issues: list[AIIssue] = []
    for decision_id in ledger.i2_violations():
        issues.append(issue("trace_violation", f"Decision '{decision_id}' rests on no claim.", item_id=decision_id))

    blocked = {c for c, o in analysis.scope.outcomes.items() if o in ("blocked", "blocked_dependent", "clarification")}
    for action in change_set.actions:
        entry = trace.entries.get(action.action_id)
        if entry is None or not entry.decision_ids:
            issues.append(issue("trace_violation", "This action has no trace to evidence claims.", action_id=action.action_id))
            continue
        for decision_id in entry.decision_ids:
            if ledger.get(decision_id) is None or not ledger.rests_on_claim(decision_id):
                issues.append(issue("trace_violation", f"Traced decision '{decision_id}' rests on no claim.", action_id=action.action_id))
        for problem in _reading_violations(ledger, [*entry.decision_ids, *entry.evidence_ids], analysis.graph):
            issues.append(issue("trace_violation", problem, action_id=action.action_id))
        outcomes = {decision_id: ledger.get(decision_id).outcome for decision_id in entry.decision_ids if ledger.get(decision_id)}
        for evidence_id in entry.evidence_ids:
            grounded = ledger.get(f"ground:{evidence_id}")
            if grounded is None or grounded.outcome not in ("anchored", "structural"):
                issues.append(issue("trace_violation", f"Evidence '{evidence_id}' is not grounded in its cited text.", action_id=action.action_id))
        if entry.subject in blocked:
            issues.append(issue("trace_violation", f"'{entry.subject}' is blocked and must not be compiled.", action_id=action.action_id))
        if action.kind == "create_object":
            if outcomes.get(f"ident:{entry.subject}") != "new" or outcomes.get(f"type:{entry.subject}") != "mapped":
                issues.append(issue("trace_violation", "A created Object must rest on a `new` identity and a mapped type.", action_id=action.action_id))
        if action.kind == "create_relationship" and outcomes.get(f"map:{entry.subject}") != "mapped":
            issues.append(issue("trace_violation", "A created relationship must rest on a mapped assertion.", action_id=action.action_id))
        if action.kind == "set_active" and not action.active:
            confirmations = [d for d in entry.decision_ids if d.startswith("adj:removal_confirmation:")]
            if not confirmations or any(outcomes.get(d) != "confirm" for d in confirmations):
                issues.append(issue("trace_violation", "A retirement must rest on a confirmed removal claim.", action_id=action.action_id))
        for decision_id in entry.decision_ids:
            if decision_id.startswith("value:"):
                for input_id in ledger.get(decision_id).inputs if ledger.get(decision_id) else ():
                    source = ledger.get(input_id)
                    if source is not None and input_id.startswith("obs:") and source.outcome == "conflict":
                        issues.append(issue("trace_violation", "A value may not come from conflicting evidence.", action_id=action.action_id))
    return issues
