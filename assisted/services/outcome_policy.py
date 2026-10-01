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
    status: str  # AssistedTask.Status.READY_FOR_REVIEW or .FAILED
    failure_reason_code: str = ""
    failure_reason: str = ""


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


_POLICIES = {AssistedTask.Operation.CREATE: CreateOutcomePolicy()}


def get_outcome_policy(operation: str) -> OutcomePolicy:
    return _POLICIES[operation]
