import uuid

from django.test import override_settings

from model.models.model import Model
from model.models.proposal import Proposal

from ai.services.provider import ProviderError

from assisted.models import AssistedTask
from assisted.services import execution
from assisted.tests.support import (
    AssistedTestCase,
    RaisingProvider,
    ScriptedProvider,
    clarification_result,
    create_object_plan,
    no_change_result,
    unresolved_result,
)


class AssistedExecutionTestCase(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("status", AssistedTask.Status.QUEUED)
        kwargs.setdefault("submitted_intent", "Track widgets.")
        return AssistedTask.objects.create(**kwargs)


class ClaimTests(AssistedExecutionTestCase):

    def test_claims_a_queued_task(self):
        task = self.make_task()

        claimed = execution.claim(task.id)

        self.assertIsNotNone(claimed)
        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.RUNNING)

    def test_a_non_queued_task_is_a_no_op(self):
        task = self.make_task(status=AssistedTask.Status.RUNNING)

        self.assertIsNone(execution.claim(task.id))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.RUNNING)

    def test_an_unknown_task_is_a_no_op(self):
        self.assertIsNone(execution.claim(uuid.uuid4()))


class RunAndFinishTests(AssistedExecutionTestCase):

    def test_ready_for_review_sets_the_proposal_and_execution(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.id)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)
        self.assertIsNotNone(task.proposal)
        self.assertIsNotNone(task.ai_execution)
        self.assertIsNotNone(task.ready_for_review_at)
        self.assertEqual(task.proposal.status, Proposal.Status.WORKING)
        self.assertEqual(task.proposal.source, Proposal.Source.AI)

    def test_needs_clarification_fails_the_task_without_deleting_a_pending_proposal(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([clarification_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.NEEDS_CLARIFICATION)

    def test_no_change_required_fails_the_task(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.NO_CHANGE_PRODUCED)

    def test_unresolved_fails_the_task(self):
        task = self.make_task()

        with override_settings(AI_MAX_REFINEMENT_CYCLES=1):
            execution.run_and_finish(task.id, provider=ScriptedProvider([unresolved_result()] * 2))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.UNRESOLVED)

    def test_a_provider_error_fails_the_task_and_deletes_the_bootstrap_model(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=RaisingProvider(ProviderError("boom")))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.EXECUTION_FAILED)
        self.assertIsNone(task.model)
        self.assertFalse(Model.objects.filter(id=self.model.id).exists())

    def test_a_non_queued_task_is_a_safe_no_op(self):
        task = self.make_task(status=AssistedTask.Status.READY_FOR_REVIEW)

        # Must not raise, and must not touch an already-finished task.
        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.id)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)
