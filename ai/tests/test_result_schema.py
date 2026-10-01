import uuid

from django.test import SimpleTestCase

from ai.services.result_schema import (
    AIStructuredResult,
    ExecutionStatus,
    Interpretation,
    OperationOutcome,
    OperationResult,
)


class AIStructuredResultTests(SimpleTestCase):

    def test_interpretation_defaults_when_omitted(self):
        result = AIStructuredResult()

        self.assertEqual(result.interpretation, Interpretation())

    def test_change_plan_is_optional(self):
        result = AIStructuredResult()

        self.assertIsNone(result.change_plan)

    def test_round_trips_through_dict(self):
        result = AIStructuredResult(interpretation=Interpretation(restated_intent="x"))

        rebuilt = AIStructuredResult.model_validate(result.model_dump(mode="json"))

        self.assertEqual(rebuilt, result)


class OperationResultTests(SimpleTestCase):

    def test_operation_result_is_plain_dataclass_not_pydantic(self):
        result = OperationResult(
            execution_status=ExecutionStatus.COMPLETED,
            outcome=OperationOutcome.NO_CHANGE_REQUIRED,
            execution_id=uuid.uuid4(),
            proposal_id=None,
            explanation="",
            refinement_cycles=0,
            context_expansions=0,
        )

        self.assertFalse(hasattr(result, "model_dump"))
        self.assertEqual(result.unresolved_issues, [])
        self.assertEqual(result.findings, [])
