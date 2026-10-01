import uuid

from django.test import SimpleTestCase

from ai.services.result_schema import ExecutionStatus, OperationOutcome, OperationResult

from assisted.models import AssistedTask
from assisted.services.outcome_policy import CreateOutcomePolicy, get_outcome_policy


def _result(execution_status, outcome, **kwargs):
    kwargs.setdefault("explanation", "")
    kwargs.setdefault("refinement_cycles", 0)
    kwargs.setdefault("context_expansions", 0)
    return OperationResult(
        execution_status=execution_status,
        outcome=outcome,
        execution_id=uuid.uuid4(),
        proposal_id=kwargs.pop("proposal_id", None),
        **kwargs,
    )


class GetOutcomePolicyTests(SimpleTestCase):

    def test_create_resolves_to_the_create_policy(self):
        self.assertIsInstance(get_outcome_policy(AssistedTask.Operation.CREATE), CreateOutcomePolicy)

    def test_an_unregistered_operation_raises(self):
        with self.assertRaises(KeyError):
            get_outcome_policy(AssistedTask.Operation.ASSESS)


class CreateOutcomePolicyTests(SimpleTestCase):

    def setUp(self):
        self.policy = CreateOutcomePolicy()

    def test_ready_for_review(self):
        result = _result(ExecutionStatus.COMPLETED, OperationOutcome.READY_FOR_REVIEW, proposal_id=uuid.uuid4())

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.READY_FOR_REVIEW)
        self.assertEqual(decision.failure_reason_code, "")

    def test_execution_failed(self):
        result = _result(ExecutionStatus.FAILED, OperationOutcome.FAILED)

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.FAILED)
        self.assertEqual(decision.failure_reason_code, AssistedTask.FailureReasonCode.EXECUTION_FAILED)

    def test_unresolved(self):
        result = _result(ExecutionStatus.COMPLETED, OperationOutcome.UNRESOLVED)

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.FAILED)
        self.assertEqual(decision.failure_reason_code, AssistedTask.FailureReasonCode.UNRESOLVED)

    def test_needs_user_clarification_uses_the_explanation_as_the_failure_reason(self):
        result = _result(
            ExecutionStatus.COMPLETED,
            OperationOutcome.NEEDS_USER_CLARIFICATION,
            explanation="Which widget do you mean?",
        )

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.FAILED)
        self.assertEqual(decision.failure_reason_code, AssistedTask.FailureReasonCode.NEEDS_CLARIFICATION)
        self.assertEqual(decision.failure_reason, "Which widget do you mean?")

    def test_no_change_required(self):
        result = _result(ExecutionStatus.COMPLETED, OperationOutcome.NO_CHANGE_REQUIRED)

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.FAILED)
        self.assertEqual(decision.failure_reason_code, AssistedTask.FailureReasonCode.NO_CHANGE_PRODUCED)

    def test_unrecognised_outcome_falls_back_to_execution_failed(self):
        result = _result(ExecutionStatus.COMPLETED, "some_future_outcome")

        decision = self.policy.decide(operation_result=result)

        self.assertEqual(decision.status, AssistedTask.Status.FAILED)
        self.assertEqual(decision.failure_reason_code, AssistedTask.FailureReasonCode.EXECUTION_FAILED)
