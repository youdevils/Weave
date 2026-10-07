"""
The generic staged-workflow engine every Assisted operation runs on.

A WorkflowDefinition is a set of Stages plus per-stage call budgets. A Stage
builds one self-contained provider payload from explicit WorkflowState (no
conversation memory: a correction attempt gets the stage's inputs, its own
previous output and OnyxJar's explicit feedback -- nothing else), names its
response schema, and evaluates the parsed output into a Decision:

    Correct(issues)        -- retry this stage with OnyxJar's feedback
    Goto(stage, ...)       -- continue at another stage (forward, or a
                              review-driven send-back with correction=True)
    Finish(outcome, ...)   -- terminal

A DeterministicStage is OnyxJar work between provider calls (Reconcile's
analysis and compilation): it makes no provider call, consumes no provider
budget, and returns Goto/Finish directly. It is still recorded as a step
(provider_call=False) and bounded by AI_WORKFLOW_MAX_DETERMINISTIC_STEPS.

The engine owns everything stages must not: the loop, the budgets, the single
provider choke point (call_provider -- usage accumulation, step recording,
progress heartbeat), the UNRESOLVED terminal on budget exhaustion and its
optional explanation call. Nothing here branches on operation id.

Budgets (all logical provider calls, never transport retries), one per
class of work so a stage may be revisited without one class starving another:
    stage_budgets[stage]  -- the stage's rounds for the whole run
    stage_budgets["<stage>_correction"]
                          -- when declared, a Correct re-ask of that stage is
                             charged here instead of to its rounds (a
                             correction never consumes a round)
    total_budget          -- hard backstop on all workflow-stage calls
    explanation_budget    -- the terminal explain() call, OUTSIDE total_budget
so the absolute per-run ceiling is total_budget + explanation_budget, and
every edge of every stage graph consumes from a finite budget.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel

from ai.services.artifacts import Finding
from ai.services.change_set import ChangeSet
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.execution import AIExecutionService
from ai.services.feedback import AIIssue, bounded_issues
from ai.services.provider import ProviderConfig, ProviderError, ProviderSchemaError
from ai.services.result_schema import ExecutionStatus, OperationOutcome
from ai.services.tracing import reconcile_snapshot, trace_active, write_step

logger = logging.getLogger("ai.workflow")


# -- decisions ----------------------------------------------------------------


@dataclass
class Correct:
    issues: list[AIIssue]


@dataclass
class Goto:
    stage_id: str
    # True for a send-back (e.g. Verification -> Planning): counted as a
    # correction of the run, not a forward step.
    correction: bool = False


@dataclass
class Finish:
    outcome: OperationOutcome
    explanation: str = ""
    proposal: Any = None
    unresolved_issues: list[AIIssue] = field(default_factory=list)
    execution_status: ExecutionStatus = ExecutionStatus.COMPLETED
    error: str = ""
    # complete | partial (a Proposal holding only the targets that could be
    # reconciled independently of blocked ones -- see OperationPolicy.partial_outcome).
    completeness: str = ""
    blocked_targets: list[dict] = field(default_factory=list)


Decision = Correct | Goto | Finish


# -- state / definition ----------------------------------------------------------


@dataclass
class WorkflowState:
    """Explicit state passed between stages. Every artifact a later call needs
    is here -- the provider never 'remembers' anything."""

    index: Any = None  # SemanticModelIndex (canonical, refreshed by stages)
    catalogue: Any = None  # OntologyCatalogue (full)
    context: Any = None  # SemanticContext (Create's planning context)
    change_set: Optional[ChangeSet] = None
    resolution: Any = None  # ai.services.resolution.Resolution
    delta: Any = None  # ai.services.staging.ProjectedDelta
    # Reconcile's claims, pins and latest deterministic results
    # (ai.services.reconcile.state.ReconcileState).
    reconcile: Any = None
    # Intent targets left out of a partial result (ai.services.reconcile).
    blocked_targets: list = field(default_factory=list)
    feedback: dict[str, list[AIIssue]] = field(default_factory=dict)
    previous_output: dict[str, BaseModel] = field(default_factory=dict)
    interpretation: str = ""
    last_issues: list[AIIssue] = field(default_factory=list)
    # User-facing findings, by origin.
    plan_findings: list[Finding] = field(default_factory=list)
    review_notes: list[Finding] = field(default_factory=list)
    unresolved_findings: list[Finding] = field(default_factory=list)
    last_output: Optional[BaseModel] = None


class Stage(ABC):
    stage_id: str
    response_schema: type[BaseModel]
    deterministic = False

    @abstractmethod
    def system_prompt(self, run: "WorkflowRun") -> str: ...

    @abstractmethod
    def build_input(self, run: "WorkflowRun") -> dict: ...

    @abstractmethod
    def evaluate(self, run: "WorkflowRun", output: BaseModel) -> Decision: ...


class DeterministicStage(ABC):
    """OnyxJar-only work between provider calls -- never calls a provider."""

    stage_id: str
    deterministic = True

    @abstractmethod
    def run(self, run: "WorkflowRun") -> "Goto | Finish": ...


@dataclass
class WorkflowDefinition:
    stages: dict[str, Stage]
    first_stage: str
    stage_budgets: dict[str, int]
    total_budget: int
    explanation_budget: int


class BudgetExhausted(Exception):
    pass


@dataclass
class WorkflowRun:
    """One execution of a WorkflowDefinition: inputs, injected collaborators,
    budgets and counters. Stages receive it as their only context."""

    operation: Any
    model: Any
    user: Any
    intent: Any  # ai.services.intent.Intent
    bundle: EvidenceBundle
    provider: Any
    config: ProviderConfig
    execution: Any  # ai.models.AIExecution
    definition: WorkflowDefinition
    on_progress: Optional[Callable[[str], None]] = None
    should_commit: Optional[Callable[[], bool]] = None
    state: WorkflowState = field(default_factory=WorkflowState)
    stage_calls: dict[str, int] = field(default_factory=dict)
    stage_corrections: dict[str, int] = field(default_factory=dict)
    workflow_calls: int = 0
    explanation_calls: int = 0
    deterministic_steps: int = 0
    step_sequence: int = 0
    corrections: int = 0
    # The sequence number reserved for the call currently being built (set
    # before build_input() runs, so a stage can correlate a trace event --
    # e.g. ai.services.stages.extraction.correction_anchors -- with its own
    # eventual <seq>-<stage>.json before the provider has even been called).
    current_sequence: int = 0

    # -- budgets -------------------------------------------------------------

    def next_sequence(self) -> int:
        self.step_sequence += 1
        return self.step_sequence

    def budget_key(self, stage_id: str, correction: bool = False) -> str:
        """The counter a call is charged to: a correction of a stage that
        declares a `<stage>_correction` budget is charged there."""

        key = f"{stage_id}_correction"
        return key if correction and key in self.definition.stage_budgets else stage_id

    def allows(self, stage_id: str, correction: bool = False) -> bool:
        key = self.budget_key(stage_id, correction)
        return (
            self.stage_calls.get(key, 0) < self.definition.stage_budgets.get(key, 0)
            and self.workflow_calls < self.definition.total_budget
        )

    @property
    def provider_calls(self) -> int:
        return self.workflow_calls + self.explanation_calls

    def stage_summary(self) -> dict:
        stages = set(self.stage_calls) | set(self.stage_corrections)
        summary = {
            stage: {"calls": self.stage_calls.get(stage, 0), "corrections": self.stage_corrections.get(stage, 0)}
            for stage in sorted(stages)
        }
        if self.explanation_calls:
            summary["explain"] = {"calls": self.explanation_calls, "corrections": 0}
        return summary

    def model_context(self) -> dict:
        return {
            "name": self.model.name,
            "purpose": self.model.purpose,
            "scope": self.model.scope,
            "exclusions": self.model.exclusions,
        }

    def user_findings(self) -> list[Finding]:
        state = self.state
        findings = [*state.unresolved_findings, *state.review_notes, *state.plan_findings]
        seen, unique = set(), []
        for finding in findings:
            marker = (finding.severity, finding.message)
            if marker not in seen:
                seen.add(marker)
                unique.append(finding)
        return unique[: settings.AI_MAX_TASK_FINDINGS]

    # -- the provider choke point ------------------------------------------------

    def call_provider(self, *, stage_id, system_prompt, payload, response_schema, correction=False):
        if not self.allows(stage_id, correction):
            raise BudgetExhausted(stage_id)
        if self.on_progress is not None:
            self.on_progress(stage_id)

        key = self.budget_key(stage_id, correction)
        self.stage_calls[key] = self.stage_calls.get(key, 0) + 1
        self.workflow_calls += 1
        AIExecutionService.record_context_digest(self.execution, payload)

        result = self.provider.generate_structured(
            system_prompt=system_prompt,
            user_payload=payload,
            response_schema=response_schema,
            config=self.config,
        )
        AIExecutionService.accumulate_usage(self.execution, result)
        if result.parsed is None:
            raise ProviderSchemaError("Provider returned no structured result.")
        return result

    def explain(self, issues) -> str:
        if not settings.AI_FINAL_EXPLANATION_ENABLED or self.explanation_calls >= self.definition.explanation_budget:
            return ""
        if self.on_progress is not None:
            self.on_progress("explain")
        self.explanation_calls += 1
        sequence = self.current_sequence = self.next_sequence()
        started = timezone.now()
        context = {"intent": self.intent.text, "interpretation": self.state.interpretation}
        try:
            result = self.provider.explain(context=context, issues=list(issues), config=self.config)
        except ProviderError:
            AIExecutionService.record_step(
                self.execution, call_index=self.provider_calls, stage="explain", stage_attempt=1,
                decision="provider_error", started_at=started, ended_at=timezone.now(), sequence=sequence,
            )
            return ""  # best-effort only; never escalate UNRESOLVED into FAILED
        ended = timezone.now()
        AIExecutionService.accumulate_usage(self.execution, result)
        AIExecutionService.record_step(
            self.execution, call_index=self.provider_calls, stage="explain", stage_attempt=1,
            decision="explain", started_at=started, ended_at=ended, usage=result.usage, sequence=sequence,
        )
        write_step(self.execution.id, sequence, "explain", {
            "kind": "explain", "run_id": str(self.execution.id), "sequence": sequence, "stage": "explain",
            "output": result.raw_text or "", "provider": result.provider, "provider_model": getattr(result, "provider_model", None),
            "usage": result.usage, "started_at": started, "ended_at": ended,
        })
        if trace_active():
            logger.info("RECONCILE_TRACE run=%s seq=%s stage=explain", self.execution.id, sequence)
        return result.raw_text or ""


def _issue_codes(issues) -> dict:
    codes: dict[str, int] = {}
    for item in issues:
        codes[item.code] = codes.get(item.code, 0) + 1
    return codes


def run_workflow(run: WorkflowRun) -> Finish:
    definition = run.definition
    state = run.state
    current = definition.first_stage

    while True:
        stage = definition.stages[current]
        if stage.deterministic:
            if run.deterministic_steps >= settings.AI_WORKFLOW_MAX_DETERMINISTIC_STEPS:
                return _unresolved(run, current)
            run.deterministic_steps += 1
            started = timezone.now()
            decision = stage.run(run)
            if isinstance(decision, Goto) and decision.correction:
                run.corrections += 1
                run.stage_corrections[decision.stage_id] = run.stage_corrections.get(decision.stage_id, 0) + 1
                AIExecutionService.increment_refinement_cycle(run.execution)
            if isinstance(decision, Finish):
                label = "finish"
            else:
                label = "send_back" if decision.correction else "advance"
            sequence = run.next_sequence()
            AIExecutionService.record_step(
                run.execution, call_index=run.provider_calls, stage=current, stage_attempt=run.deterministic_steps,
                decision=label, started_at=started, sequence=sequence, provider_call=False,
                issue_codes=_issue_codes(decision.unresolved_issues) if isinstance(decision, Finish) else {},
            )
            write_step(run.execution.id, sequence, current, {
                "kind": "deterministic", "run_id": str(run.execution.id), "sequence": sequence, "stage": current,
                "decision": label, "next": getattr(decision, "stage_id", None), "snapshot": reconcile_snapshot(run.state),
            })
            logger.info("ai.workflow execution=%s stage=%s deterministic decision=%s", run.execution.id, current, label)
            if trace_active():
                logger.info("RECONCILE_TRACE run=%s seq=%s stage=%s", run.execution.id, sequence, current)
            if isinstance(decision, Finish):
                return decision
            current = decision.stage_id
            continue

        # A call made after this stage's Correct is a correction (charged to
        # its correction budget when one is declared).
        correcting = bool(state.feedback.get(current))
        if not run.allows(current, correcting):
            return _unresolved(run, current)

        correction_key = run.budget_key(current, True)
        attempt = run.stage_calls.get(current, 0) + (run.stage_calls.get(correction_key, 0) if correction_key != current else 0) + 1
        # Reserved before build_input() runs, so a stage can correlate a
        # trace event it writes mid-build (e.g. correction_anchors) with
        # this same call's eventual <seq>-<stage>.json.
        sequence = run.current_sequence = run.next_sequence()
        payload = stage.build_input(run)
        started = timezone.now()
        try:
            result = run.call_provider(
                stage_id=current,
                system_prompt=stage.system_prompt(run),
                payload=payload,
                response_schema=stage.response_schema,
                correction=correcting,
            )
        except ProviderError:
            AIExecutionService.record_step(
                run.execution, call_index=run.provider_calls, stage=current, stage_attempt=attempt,
                decision="provider_error", started_at=started, ended_at=timezone.now(), input_payload=payload, sequence=sequence,
            )
            raise
        ended = timezone.now()

        output = result.parsed
        state.last_output = output
        decision = stage.evaluate(run, output)

        if isinstance(decision, Correct):
            issues = bounded_issues(decision.issues)
            state.feedback[current] = issues
            state.previous_output[current] = output
            state.last_issues = issues
            run.corrections += 1
            run.stage_corrections[current] = run.stage_corrections.get(current, 0) + 1
            AIExecutionService.increment_refinement_cycle(run.execution)
            label, codes = "correct", _issue_codes(issues)
        elif isinstance(decision, Goto):
            state.feedback.pop(current, None)
            state.previous_output[current] = output
            if decision.correction:
                run.corrections += 1
                run.stage_corrections[current] = run.stage_corrections.get(current, 0) + 1
                AIExecutionService.increment_refinement_cycle(run.execution)
            label = "send_back" if decision.correction else "advance"
            codes = _issue_codes(state.last_issues) if decision.correction else {}
        else:
            label, codes = "finish", _issue_codes(decision.unresolved_issues)

        AIExecutionService.record_step(
            run.execution,
            call_index=run.provider_calls,
            stage=current,
            stage_attempt=attempt,
            decision=label,
            started_at=started,
            ended_at=ended,
            issue_codes=codes,
            verdict=getattr(output, "verdict", "") or "",
            usage=result.usage,
            input_payload=payload,
            output_payload=output.model_dump(mode="json"),
            sequence=sequence,
        )
        write_step(run.execution.id, sequence, current, {
            "kind": "provider", "run_id": str(run.execution.id), "sequence": sequence, "stage": current, "attempt": attempt,
            "decision": label, "schema": stage.response_schema.__name__, "payload": payload, "output": output.model_dump(mode="json"),
            "issues": [i.model_dump(mode="json") for i in (decision.issues if isinstance(decision, Correct) else [])],
            "provider": result.provider, "provider_model": getattr(result, "provider_model", None), "usage": result.usage,
            "started_at": started, "ended_at": ended,
        })
        if trace_active():
            logger.info("RECONCILE_TRACE run=%s seq=%s stage=%s", run.execution.id, sequence, current)
        logger.info(
            "ai.workflow execution=%s stage=%s attempt=%s decision=%s issues=%s tokens=%s",
            run.execution.id, current, attempt, label, codes, (result.usage or {}).get("total_tokens"),
        )

        if isinstance(decision, Finish):
            return decision
        if isinstance(decision, Goto):
            current = decision.stage_id


def _unresolved(run: WorkflowRun, stage_id: str) -> Finish:
    issues = run.state.last_issues or [
        AIIssue(code="budget_exhausted", message=f"The {stage_id} stage used its whole bounded budget.")
    ]
    explanation = run.explain(issues)
    return Finish(OperationOutcome.UNRESOLVED, explanation=explanation, unresolved_issues=list(issues))
