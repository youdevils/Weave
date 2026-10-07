from ai.models import AIExecution
from django.utils import timezone

from ai.models import AIExecutionStep
from ai.services.reconcile.responses import ExtractionResult
from ai.services.execution import AIExecutionService
from ai.services.provider import ProviderResult
from ai.services.result_schema import ExecutionStatus, OperationOutcome
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
        packet_a = {"stage": "extraction", "intent": "a"}
        packet_b = {"stage": "extraction", "intent": "b"}

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

    def test_record_step_keeps_digests_and_codes_never_payloads(self):
        execution = self._execution()

        step = AIExecutionService.record_step(
            execution,
            call_index=1,
            stage="extraction",
            stage_attempt=1,
            decision="correct",
            started_at=timezone.now(),
            issue_codes={"excerpt_not_found": 2},
            usage={"total_tokens": 7},
            input_payload={"intent": "secret intent text"},
            output_payload={"x": 1},
        )

        step.refresh_from_db()
        self.assertEqual(step.issue_codes, {"excerpt_not_found": 2})
        self.assertEqual(len(step.input_digest), 64)
        self.assertEqual(len(step.output_digest), 64)
        self.assertNotIn("secret", str(AIExecutionStep.objects.filter(pk=step.pk).values().first()))

    def test_finish_records_provider_calls_and_stage_summary(self):
        execution = self._execution()

        AIExecutionService.finish(
            execution,
            execution_status=ExecutionStatus.COMPLETED,
            outcome=OperationOutcome.NO_CHANGE_REQUIRED,
            provider_calls=2,
            stage_summary={"extraction": {"calls": 1, "corrections": 0}},
        )

        execution.refresh_from_db()
        self.assertEqual(execution.provider_calls, 2)
        self.assertEqual(execution.stage_summary["extraction"]["calls"], 1)

    def test_result_digest_populated_when_structured_result_exists(self):
        execution = self._execution()
        result = ExtractionResult()

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
