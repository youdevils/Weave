"""
Planning: the AI authors a ChangeSet v3 directly -- used where the model
structure itself is the output (Create), rather than compiled from evidence
claims (Reconcile, ai.services.reconcile).

Every attempt: resolve deterministically (ai.services.resolution) against
the full semantic context; Create commits a clean ChangeSet directly --
commit_proposal performs the apply-and-validate itself -- and a validation
failure comes back as action-addressed feedback for the next attempt.
"""

from __future__ import annotations

from ai.services.change_set import PlanResult
from ai.services.resolution import resolve_change_set
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.semantic.selection import select_full_context
from ai.services.stages import prompts
from ai.services.stages.commit import commit, commit_decision
from ai.services.workflow.engine import Correct, Finish, Stage


class PlanningStage(Stage):
    stage_id = "planning"
    response_schema = PlanResult

    def __init__(self, *, prompt: str = prompts.CREATE_PLANNING):
        self.prompt = prompt

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + self.prompt

    def build_input(self, run) -> dict:
        state = run.state
        state.index = SemanticModelIndex.load(run.model)  # canonical as it stands now, every attempt
        state.context = select_full_context(state.index)
        feedback = state.feedback.get(self.stage_id, [])
        previous = state.previous_output.get(self.stage_id)
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "operation_policy": run.operation.policy.describe(),
            "context": state.context.model_dump(mode="json"),
            "evidence": [source.model_dump(mode="json", exclude={"segments"}) for source in run.bundle.sources],
            "feedback": [item.model_dump(mode="json", exclude_none=True) for item in feedback],
            "previous_change_set": previous.change_set.model_dump(mode="json") if (feedback and previous is not None) else None,
        }

    def evaluate(self, run, output: PlanResult):
        state = run.state
        if output.clarification.needed:
            return Finish(
                OperationOutcome.NEEDS_USER_CLARIFICATION,
                explanation=output.clarification.question or "The request needs clarification.",
            )
        if output.interpretation.restated_intent:
            state.interpretation = output.interpretation.restated_intent

        change_set = output.change_set
        resolution = resolve_change_set(
            change_set, model=run.model, index=state.index, policy=run.operation.policy, bundle=run.bundle, intent_text=run.intent.text
        )
        if resolution.issues:
            return Correct(resolution.issues)

        state.change_set = change_set
        state.resolution = resolution
        state.plan_findings = [f for f in output.findings if f.severity in ("info", "warning")]
        if not change_set.actions:
            return Finish(OperationOutcome.NO_CHANGE_REQUIRED, explanation=state.interpretation)
        return commit_decision(run, commit(run, resolution=resolution, index=state.index), on_issues=Correct)
