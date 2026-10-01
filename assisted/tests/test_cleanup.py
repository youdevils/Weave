import uuid

from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal

from ai.services.result_schema import ExecutionStatus, OperationOutcome, OperationResult

from assisted.models import AssistedTask
from assisted.services.cleanup import fail_task
from assisted.tests.support import AssistedTestCase


def _result(**kwargs):
    kwargs.setdefault("execution_status", ExecutionStatus.COMPLETED)
    kwargs.setdefault("outcome", OperationOutcome.UNRESOLVED)
    kwargs.setdefault("execution_id", uuid.uuid4())
    kwargs.setdefault("proposal_id", None)
    kwargs.setdefault("explanation", "")
    kwargs.setdefault("refinement_cycles", 3)
    kwargs.setdefault("context_expansions", 1)
    return OperationResult(**kwargs)


class FailTaskTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("status", AssistedTask.Status.RUNNING)
        return AssistedTask.objects.create(**kwargs)

    def test_denormalizes_failure_fields(self):
        task = self.make_task()

        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.UNRESOLVED,
            failure_reason="could not resolve",
            result=_result(),
        )

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.UNRESOLVED)
        self.assertEqual(task.failure_reason, "could not resolve")
        self.assertEqual(task.ai_outcome, OperationOutcome.UNRESOLVED.value)
        self.assertEqual(task.refinement_cycles, 3)
        self.assertEqual(task.context_expansions, 1)
        self.assertIsNotNone(task.failed_at)

    def test_create_operation_deletes_its_bootstrap_model(self):
        task = self.make_task(operation=AssistedTask.Operation.CREATE)

        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="boom",
        )

        self.assertFalse(Model.objects.filter(id=self.model.id).exists())
        task.refresh_from_db()
        self.assertIsNone(task.model)

    def test_non_bootstrap_operation_leaves_the_model_untouched(self):
        # Fabricated: RECONCILE/CHANGE/ASSESS aren't implemented yet, but the
        # operation-gating in fail_task must already hold for them.
        task = self.make_task(operation=AssistedTask.Operation.CHANGE)

        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="boom",
        )

        self.assertTrue(Model.objects.filter(id=self.model.id).exists())
        task.refresh_from_db()
        self.assertEqual(task.model_id, self.model.id)

    def test_already_null_model_is_a_no_op_for_deletion(self):
        task = self.make_task(model=None)

        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.STALE_TIMED_OUT,
            failure_reason="timed out",
        )

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)

    def test_a_proposal_queued_for_processing_blocks_deletion_and_is_logged_not_raised(self):
        ObjectType.objects.create(model=self.model, name="Thing", key="thing")
        Proposal.objects.create(model=self.model, created_by=self.owner, status=Proposal.Status.QUEUED)
        task = self.make_task()

        # Must not raise even though delete_model() itself would.
        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="boom",
        )

        self.assertTrue(Model.objects.filter(id=self.model.id).exists())
        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
