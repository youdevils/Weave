"""
AI-outcome -> AssistedTask mapping, as a per-operation policy rather than a
global switch. This is deliberately a one-class-per-operation registry: a
future ASSESS operation (no Proposal gate -- "operation happened, here's the
result" independent of whether a Proposal exists) plugs in as a new policy
class plus one _POLICIES entry, never a change to assisted.services.execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ai.services.result_schema import ExecutionStatus, OperationOutcome

from assisted.models import AssistedTask


@dataclass(frozen=True)
class OutcomeDecision:
    status: str  # AssistedTask.Status.READY_FOR_REVIEW, .COMPLETED, or .FAILED
    failure_reason_code: str = ""
    failure_reason: str = ""
    # Only meaningful when status == COMPLETED (a non-Proposal success, e.g.
    # Reconcile's NO_CHANGE_REQUIRED/UNRESOLVED/NEEDS_USER_CLARIFICATION):
    # written to AssistedTask.outcome_detail, never failure_reason, which is
    # semantically failure-only.
    outcome_detail: str = ""


class OutcomePolicy(Protocol):
    def decide(self, *, operation_result) -> OutcomeDecision: ...


class CreateOutcomePolicy:
    """
    Create has no reviewable artifact other than a Proposal: every outcome
    except READY_FOR_REVIEW is terminal FAILED, each with its own
    failure_reason_code.
    """

    def decide(self, *, operation_result) -> OutcomeDecision:
        if operation_result.execution_status == ExecutionStatus.FAILED:
            return OutcomeDecision(
                AssistedTask.Status.FAILED,
                AssistedTask.FailureReasonCode.EXECUTION_FAILED,
                "The assisted run failed unexpectedly. Try again, or start from scratch.",
            )

        outcome = operation_result.outcome

        if outcome == OperationOutcome.READY_FOR_REVIEW:
            return OutcomeDecision(AssistedTask.Status.READY_FOR_REVIEW)

        if outcome == OperationOutcome.UNRESOLVED:
            return OutcomeDecision(
                AssistedTask.Status.FAILED,
                AssistedTask.FailureReasonCode.UNRESOLVED,
                "The assisted run could not produce a valid proposal after several attempts.",
            )

        if outcome == OperationOutcome.NEEDS_USER_CLARIFICATION:
            return OutcomeDecision(
                AssistedTask.Status.FAILED,
                AssistedTask.FailureReasonCode.NEEDS_CLARIFICATION,
                operation_result.explanation or "The assisted run needed clarification it could not get.",
            )

        if outcome == OperationOutcome.NO_CHANGE_REQUIRED:
            return OutcomeDecision(
                AssistedTask.Status.FAILED,
                AssistedTask.FailureReasonCode.NO_CHANGE_PRODUCED,
                "The assisted run did not find anything to create.",
            )

        # Defensive catch-all for any future OperationOutcome value.
        return OutcomeDecision(
            AssistedTask.Status.FAILED,
            AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            "The assisted run ended in an unrecognised state.",
        )


class ReconcileOutcomePolicy:
    """
    Unlike Create, Reconcile's Model pre-exists and isn't a disposable
    bootstrap artifact: "no supported changes found" and "ran out of bounded
    cycles without enough evidence" are genuine successes here, not
    failures -- COMPLETED with no Proposal, exactly what
    assisted/templates/assisted/task_detail.html's existing non-Proposal,
    non-failed render branch already anticipates. NEEDS_USER_CLARIFICATION is
    deliberately collapsed into the same bucket as UNRESOLVED: there is no
    chat loop for the user to answer a mid-task clarification question, so
    both mean "ran cleanly to a terminal determination, nothing to review
    this time." Only a genuine execution failure (provider error, exception,
    or an outcome this policy doesn't recognise) is terminal FAILED.
    """

    def decide(self, *, operation_result) -> OutcomeDecision:
        if operation_result.execution_status == ExecutionStatus.FAILED:
            return OutcomeDecision(
                AssistedTask.Status.FAILED,
                AssistedTask.FailureReasonCode.EXECUTION_FAILED,
                "The assisted run failed unexpectedly. Try again, or start from scratch.",
            )

        outcome = operation_result.outcome

        if outcome == OperationOutcome.READY_FOR_REVIEW:
            return OutcomeDecision(AssistedTask.Status.READY_FOR_REVIEW)

        if outcome == OperationOutcome.NO_CHANGE_REQUIRED:
            return OutcomeDecision(
                AssistedTask.Status.COMPLETED,
                outcome_detail=operation_result.explanation
                or "No changes were needed -- the supplied evidence is already consistent with this model.",
            )

        if outcome in (OperationOutcome.UNRESOLVED, OperationOutcome.NEEDS_USER_CLARIFICATION):
            return OutcomeDecision(
                AssistedTask.Status.COMPLETED,
                outcome_detail=operation_result.explanation
                or "OnyxJar could not determine a confidently supported change from the supplied evidence.",
            )

        # Defensive catch-all for any future OperationOutcome value.
        return OutcomeDecision(
            AssistedTask.Status.FAILED,
            AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            "The assisted run ended in an unrecognised state.",
        )


_POLICIES = {
    AssistedTask.Operation.CREATE: CreateOutcomePolicy(),
    AssistedTask.Operation.RECONCILE: ReconcileOutcomePolicy(),
}


def get_outcome_policy(operation: str) -> OutcomePolicy:
    return _POLICIES[operation]
