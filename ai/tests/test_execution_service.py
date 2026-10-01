from ai.models import AIExecution
from ai.services.context_schema import ContextPacket
from ai.services.execution import AIExecutionService
from ai.services.provider import ProviderResult
from ai.services.result_schema import AIStructuredResult, ExecutionStatus, Interpretation, OperationOutcome
from ai.tests.support import AIServiceTestCase


class AIExecutionServiceTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()

    def _execution(self):
        return AIExecutionService.create(operation="test_op", model=self.model, user=self.user)

    def test_create_sets_running_status(self):
        execution = self._execution()

        self.assertEqual(execution.execution_status, AIExecution.ExecutionStatus.RUNNING)
        self.assertIsNone(execution.outcome)
        self.assertIsNone(execution.proposal)

    def test_context_digest_overwritten_each_cycle_latest_wins(self):
        execution = self._execution()
        packet_a = ContextPacket(intent="a", model_id="1", model_name="M", model_revision=1, byte_size=0)
        packet_b = ContextPacket(intent="b", model_id="1", model_name="M", model_revision=1, byte_size=0)

        AIExecutionService.record_context_digest(execution, packet_a)
        digest_a = execution.context_digest
        AIExecutionService.record_context_digest(execution, packet_b)

        self.assertNotEqual(execution.context_digest, digest_a)

    def test_usage_accumulated_across_cycles(self):
        execution = self._execution()
        result = ProviderResult(parsed=None, raw_text="", usage={"total_tokens": 10}, provider="openai")

        AIExecutionService.accumulate_usage(execution, result)
        AIExecutionService.accumulate_usage(execution, result)

        self.assertEqual(execution.usage["total_tokens"], 20)

    def test_provider_model_recorded_once(self):
        execution = self._execution()
        first = ProviderResult(parsed=None, raw_text="", usage={}, provider="openai", provider_model="gpt-4.1")
        second = ProviderResult(parsed=None, raw_text="", usage={}, provider="openai", provider_model="gpt-5")

        AIExecutionService.accumulate_usage(execution, first)
        AIExecutionService.accumulate_usage(execution, second)

        self.assertEqual(execution.provider_model, "gpt-4.1")

    def test_increment_refinement_cycle(self):
        execution = self._execution()

        AIExecutionService.increment_refinement_cycle(execution)
        AIExecutionService.increment_refinement_cycle(execution)

        self.assertEqual(execution.refinement_cycles, 2)

    def test_increment_context_expansion(self):
        execution = self._execution()

        AIExecutionService.increment_context_expansion(execution)

        self.assertEqual(execution.context_expansions, 1)

    def test_result_digest_populated_when_structured_result_exists(self):
        execution = self._execution()
        result = AIStructuredResult(interpretation=Interpretation(restated_intent="x"))

        AIExecutionService.finish(
            execution,
            execution_status=ExecutionStatus.COMPLETED,
            outcome=OperationOutcome.NO_CHANGE_REQUIRED,
            result_payload=result,
        )

        self.assertNotEqual(execution.result_digest, "")

    def test_result_digest_blank_when_no_structured_result_exists(self):
        execution = self._execution()

        AIExecutionService.finish(
            execution,
            execution_status=ExecutionStatus.FAILED,
            outcome=OperationOutcome.FAILED,
            error="provider timed out",
        )

        self.assertEqual(execution.result_digest, "")

    def test_execution_never_left_running_after_finish(self):
        execution = self._execution()

        AIExecutionService.finish(
            execution,
            execution_status=ExecutionStatus.COMPLETED,
            outcome=OperationOutcome.NO_CHANGE_REQUIRED,
        )

        self.assertNotEqual(execution.execution_status, AIExecution.ExecutionStatus.RUNNING)
        self.assertIsNotNone(execution.ended_at)

    def test_proposal_set_on_finish_when_given(self):
        from model.services.proposal.proposal import ProposalService
        from model.models.proposal import Proposal

        execution = self._execution()
        proposal = ProposalService.create_working(self.model, self.user, source=Proposal.Source.AI)

        AIExecutionService.finish(
            execution,
            execution_status=ExecutionStatus.COMPLETED,
            outcome=OperationOutcome.READY_FOR_REVIEW,
            proposal=proposal,
        )

        self.assertEqual(execution.proposal_id, proposal.id)
