"""
Reconcile's deterministic stages (no provider calls):

    analysis  run the whole deterministic pipeline (ai.services.reconcile.analysis)
              on the current claims, derive the WorkQueue and route it. This
              is the convergence hub: every stage returns here, and any stage
              may create work for another (a probe's claims raise questions,
              an answer exposes an evidence gap, an objection does either),
              so a stage is revisited whenever new work of its class exists
              and its own budget allows:

                  1. clarification          -> finish (ask the user)
                  2. decision gaps (open     -> Adjudication  (answers change
                     questions)                 which requirements are truly
                                                unsatisfied, so they go first)
                  3. evidence gaps (unmet    -> Gap Probe
                     requirements with no
                     evidence at all)
                  4. otherwise              -> compile

              Adjudication and Gap Probe rounds are progress-driven, not
              counted. A class may take another round while (may_run_round):
                - the round still leaves a full Verification pass
                  (affords_recovery / verification_pass_cost). Every
                  recovery call -- a round, a correction of a round or of an
                  extraction wave -- is granted only on that condition, when
                  it is about to be made, so recovery never spends the calls
                  the next review needs (a round's correction is therefore
                  subject to the total budget only at its very edge);
                - it has not spent MAX_IDLE_ROUNDS consecutive rounds
                  without progress (a new claimed pin / a new accepted
                  claim). Genuinely new work for the class (an id never
                  routed to it before) starts a fresh streak.
              A gap the class may not take is deferred, never defaulted: no
              pin is written, its decision stays undecided (nothing resting
              on it compiles), and it is reported as unadjudicated /
              unprobed.

              Termination: every route needs NEW work (unasked question
              ids, unprobed requirement ids, unseen objections -- sets that
              only grow). The universe of question / requirement ids grows
              only through accepted claims or claimed pins, i.e. through
              productive rounds (or Verification, under its own bounds),
              each costing at least one call of the finite total budget;
              between them it is finite, so idle streaks are reset finitely
              often, and rounds over work already routed are capped by
              MAX_IDLE_ROUNDS. The run is bounded overall.

    compile   the blocked set and partial-outcome policy, compilation into a
              ChangeSet v3 + ChangeTrace, TracePolicy (I2), the mutation
              resolver, and speculative staging -> Verification. A residual
              resolver/staging failure is never sent to a provider as prose:
              the deterministic chain re-runs once on a fresh index, then the
              run ends UNRESOLVED.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings

from ai.services.artifacts import Finding
from ai.services.feedback import translate_validation_issues
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.ledger import ADJUDICATION
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.trace_policy import check_trace
from ai.services.resolution import resolve_change_set
from ai.services.result_schema import ExecutionStatus, OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.staging import ProjectedDelta, stage_and_validate
from ai.services.workflow.engine import DeterministicStage, Finish, Goto

logger = logging.getLogger("ai.workflow")

_PENDING_TEXT = {
    "open": "not adjudicated (the Adjudication budget was spent)",
    "undecidable": "judged undecidable from the evidence",
    "rejected_answer": "the answer given could not be verified against the evidence",
}


@dataclass
class WorkQueue:
    """What the current analysis leaves to do, by class of work. Derived on
    every analysis, never stored as truth."""

    clarification: str = ""
    decision_gaps: list = field(default_factory=list)  # Questions (grouped by pattern)
    evidence_gaps: list = field(default_factory=list)  # Requirements
    deferred_decisions: list = field(default_factory=list)
    deferred_evidence: list = field(default_factory=list)
    route: str = ""

    def payload(self) -> dict:
        return {
            "route": self.route,
            "clarification": bool(self.clarification),
            "decision_gaps": [question.question_id for question in self.decision_gaps],
            "evidence_gaps": [requirement.requirement_id for requirement in self.evidence_gaps],
            "deferred_decisions": [question.question_id for question in self.deferred_decisions],
            "deferred_evidence": [requirement.requirement_id for requirement in self.deferred_evidence],
        }


def work_queue(analysis) -> WorkQueue:
    return WorkQueue(clarification=analysis.clarification, decision_gaps=list(analysis.questions),
                     evidence_gaps=list(analysis.probe_requests))


# -- progress-driven rounds -------------------------------------------------------------


def _idle_limit(stage: str) -> int:
    return {
        "adjudication": settings.AI_RECONCILE_ADJUDICATION_MAX_IDLE_ROUNDS,
        "gap_probe": settings.AI_RECONCILE_GAP_PROBE_MAX_IDLE_ROUNDS,
    }[stage]


def progress(rs, stage: str) -> int:
    """A monotone count of what a round of the class can add: claimed pins
    for Adjudication (a refused answer is not progress), accepted claims for
    the Gap Probe (the graph only grows; retraction is an overlay)."""

    if stage == "adjudication":
        return sum(1 for pin in rs.pins.values() if pin.basis != "rejected_answer")
    return len(rs.graph.ids())


def verification_pass_cost(run) -> int:
    """The provider calls one complete Verification pass may need: the review,
    plus the re-ask of an unroutable objection while its correction budget
    lasts (commit makes no provider call; explain() is outside the budget).
    A send-back re-enters analysis, where every recovery round is checked
    against this again for the next review."""

    budgets = run.definition.stage_budgets
    correction = (budgets.get("verification_correction") or 0) - run.stage_calls.get("verification_correction", 0)
    return 1 + max(0, correction)


def affords_recovery(run) -> bool:
    """Whether one more recovery call (a round, or a correction of one) still
    leaves a full Verification pass. Checked when the call is about to be
    made, never reserved ahead."""

    return run.remaining_calls() >= 1 + verification_pass_cost(run)


def may_run_round(run, stage: str, work_ids) -> bool:
    """Whether the class may take one more round for this work (see the
    module docstring). Work never routed to the class starts a fresh idle
    streak."""

    rs = run.state.reconcile
    if set(work_ids) - rs.routed_work.get(stage, set()):
        rs.idle_rounds[stage] = 0
    return run.allows(stage) and affords_recovery(run) and rs.idle_rounds.get(stage, 0) < _idle_limit(stage)


def open_round(rs, stage: str, work_ids) -> None:
    rs.round_open = (stage, progress(rs, stage))
    rs.routed_work.setdefault(stage, set()).update(work_ids)


def close_round(rs) -> None:
    """At the analysis after a round (and its correction): progress resets the
    class's idle streak, none extends it."""

    if rs.round_open is None:
        return
    stage, marker = rs.round_open
    rs.idle_rounds[stage] = 0 if progress(rs, stage) > marker else rs.idle_rounds.get(stage, 0) + 1
    rs.round_open = None


def _question_ids(queue: WorkQueue) -> list[str]:
    return [question.question_id for question in queue.decision_gaps]


def _requirement_ids(queue: WorkQueue) -> list[str]:
    return [requirement.requirement_id for requirement in queue.evidence_gaps]


def route(queue: WorkQueue, run) -> str:
    """The convergence policy (see the module docstring): the next stage for
    this queue, deferring any gap whose class may not take another round."""

    if queue.clarification:
        queue.route = "clarification"
    elif queue.decision_gaps and may_run_round(run, "adjudication", _question_ids(queue)):
        queue.route = "adjudication"
    else:
        queue.deferred_decisions = list(queue.decision_gaps)
        if queue.evidence_gaps and may_run_round(run, "gap_probe", _requirement_ids(queue)):
            queue.route = "gap_probe"
        else:
            queue.deferred_evidence = list(queue.evidence_gaps)
            queue.route = "compile"
    return queue.route


def _pending_reason(pending: dict) -> str:
    parts = [f"{count} claim(s): {_PENDING_TEXT.get(status, status)}" for status, count in sorted(pending.items())]
    return "; ".join(parts)


_COVERAGE_TEXT = {"complete": "", "partial": " (not all of the evidence could be reviewed)", "": ""}


def _target_block_message(blocked) -> str:
    """Requested work that was not done -- never a silent no-op."""

    asked = f"the request asks to {blocked.get('verb') or 'add'} '{blocked['target']}'"
    reason = blocked["reason"]
    if reason == "unframed":
        return (f"Not done: part of the request (\"{blocked.get('excerpt') or blocked['target']}\") could not be grounded in the "
                "request's own words, so OnyxJar could not act on it.")
    if reason == "unmapped":
        return f"Not done: {asked}, but the model has no kind of entity or relationship for '{blocked['target']}'."
    if reason == "undecided":
        return f"Not done: {asked}, but which kind of model entity that means could not be decided."
    return f"Not done: {asked}, but the evidence names none{_COVERAGE_TEXT.get(blocked.get('coverage', ''), '')}."


def blocked_findings(blocked_targets) -> list[Finding]:
    findings = []
    for blocked in blocked_targets:
        if blocked.get("target_id"):
            findings.append(Finding(severity="material", message=_target_block_message(blocked)))
            continue
        reasons = []
        for missing in blocked["missing_requirements"]:
            who = f"'{missing['entity']}' " if missing.get("entity") else ""
            coverage = " (not all of the evidence could be reviewed)" if missing.get("coverage") == "partial" else ""
            if missing.get("constraint_conflict"):
                reasons.append(
                    f"{who}is related by the evidence to {missing['constraint_conflict']} {missing['counterpart_type_key']}(s) by "
                    f"'{missing['relationship_type_key']}', more than the model allows"
                )
                continue
            pending = missing.get("pending_decision") or {}
            if pending and missing.get("viable", 0) < missing["minimum"]:
                reasons.append(
                    f"{who}needs a '{missing['relationship_type_key']}' -> {missing['counterpart_type_key']}; the evidence relates it to "
                    f"{missing['evidenced']} {missing['counterpart_type_key']}(s), but which model relationship its wording means is undecided "
                    f"({_pending_reason(pending)})"
                )
                continue
            if missing.get("unresolved_ambiguity"):
                reasons.append(
                    f"{who}needs a '{missing['relationship_type_key']}' -> {missing['counterpart_type_key']}, and which "
                    f"{missing['counterpart_type_key']} the evidence means could not be resolved"
                )
                continue
            evidenced = missing.get("evidenced", missing["found"])
            viable = missing.get("viable", evidenced)
            if evidenced >= missing["minimum"] and viable < missing["minimum"]:
                reasons.append(
                    f"{who}is related by the evidence to {evidenced} {missing['counterpart_type_key']}(s) by "
                    f"'{missing['relationship_type_key']}', but they cannot be added themselves"
                )
                continue
            reasons.append(
                f"{who}needs at least {missing['minimum']} '{missing['relationship_type_key']}' -> "
                f"{missing['counterpart_type_key']}, but the evidence identifies {evidenced}{coverage}"
            )
        cascade = blocked.get("cascade")
        if cascade and len(cascade["chain"]) > 1:
            cause = cascade["cause"]
            needs = (f"'{cause['entity']}' needs at least {cause['minimum']} '{cause['relationship_type_key']}' -> "
                     f"{cause['counterpart_type_key']}")
            if cause.get("pending_decision"):
                why = (f"the evidence relates it to {cause['evidenced']}, but which model relationship that wording means is "
                       f"undecided ({_pending_reason(cause['pending_decision'])})")
            elif cause.get("unresolved_ambiguity"):
                why = f"which {cause['counterpart_type_key']} the evidence means could not be resolved"
            elif cause.get("constraint_conflict"):
                why = f"the evidence relates it to more {cause['counterpart_type_key']}s than the model allows"
            else:
                why = f"the evidence identifies {cause['evidenced']}"
            reasons.append(f"because {' <- '.join(repr(n) for n in cascade['chain'])}: {needs}, and {why}")
        if blocked["reason"] == "clarification":
            reasons.append("the evidence allows more than one candidate")
        detail = "; ".join(reasons) or "a required related entity is not identified by the evidence"
        dependants = f" (also left out: {', '.join(blocked['dependants'])})" if blocked["dependants"] else ""
        findings.append(Finding(severity="material", message=f"Not included: {blocked['type_key']} '{blocked['target']}' -- {detail}.{dependants}"))
    return findings


class AnalysisStage(DeterministicStage):
    stage_id = "analysis"

    def run(self, run):
        state = run.state
        rs = state.reconcile
        state.index = SemanticModelIndex.load(run.model)
        close_round(rs)

        analysis = run_analysis(rs, index=state.index, bundle=run.bundle)
        rs.analysis = analysis
        queue = work_queue(analysis)
        next_stage = route(queue, run)
        rs.work_queue = queue
        if next_stage == "clarification":
            return Finish(OperationOutcome.NEEDS_USER_CLARIFICATION, explanation=analysis.clarification)
        if next_stage == "adjudication":
            open_round(rs, next_stage, _question_ids(queue))
        elif next_stage == "gap_probe":
            open_round(rs, next_stage, _requirement_ids(queue))
        for question in queue.deferred_decisions:
            # Not a pin and not a claim: the decision stays undecided.
            analysis.ledger.coverage(f"open:{question.question_id}", step=ADJUDICATION, basis="budget",
                                     subject_ids=question.subject_ids, outcome="unadjudicated", detail={"kind": question.kind})
        for requirement in queue.deferred_evidence:
            # Never probed: the evidence was not fully reviewed for it.
            rs.missing_evidence.setdefault(requirement.requirement_id, "partial")
        return Goto(next_stage)


class CompileStage(DeterministicStage):
    stage_id = "compile"

    def run(self, run):
        state = run.state
        rs = state.reconcile
        analysis = rs.analysis
        index = state.index
        policy = run.operation.policy

        state.blocked_targets = analysis.blocked_targets(index, rs.missing_evidence)
        blocked_notes = blocked_findings(state.blocked_targets)
        state.plan_findings = _dedupe(rs.notes, analysis.findings)
        state.unresolved_findings = blocked_notes

        if state.blocked_targets and policy.partial_outcome == "forbidden":
            return Finish(OperationOutcome.UNRESOLVED, explanation="Some requested items could not be reconciled from the evidence.",
                          blocked_targets=state.blocked_targets)

        change_set, trace = compile_change_set(analysis, index=index)
        violations = check_trace(change_set, trace, analysis)
        if violations:
            logger.error("Reconcile trace violations (an OnyxJar defect): %s", [v.message for v in violations])
            return Finish(
                OperationOutcome.FAILED, execution_status=ExecutionStatus.FAILED,
                error="OnyxJar could not trace a compiled change to its evidence.", unresolved_issues=violations,
            )
        # Nothing compilable (everything blocked) still goes to Verification,
        # with full objection routing: a missed_evidence objection there
        # re-enters the pipeline and can unblock targets. Only an approval (or
        # unroutable / repeated objections, or a spent budget) ends UNRESOLVED.

        resolution = resolve_change_set(
            change_set, model=run.model, index=index, policy=policy, bundle=run.bundle, intent_text=run.intent.text
        )
        issues = resolution.issues
        delta = ProjectedDelta()
        if not issues and change_set.actions:
            staged = stage_and_validate(model=run.model, user=run.user, operation=run.operation, resolution=resolution, index=index)
            issues = translate_validation_issues(staged.issues, ref_map=resolution.ref_map, index=index) if staged.issues else []
            delta = staged.delta or ProjectedDelta()
        if issues:
            state.last_issues = issues
            if rs.compile_retries < 1:
                rs.compile_retries += 1
                return Goto("analysis")
            return Finish(
                OperationOutcome.UNRESOLVED,
                explanation="The compiled changes could not be validated against the current model.",
                unresolved_issues=issues, blocked_targets=state.blocked_targets,
            )

        rs.compiled = (change_set, trace)
        state.change_set = change_set
        state.resolution = resolution
        state.delta = delta
        return Goto("verification")


def _dedupe(*groups) -> list[Finding]:
    seen, result = set(), []
    for group in groups:
        for finding in group:
            marker = (finding.severity, finding.message)
            if marker not in seen:
                seen.add(marker)
                result.append(finding)
    return result
