from django.db import IntegrityError, transaction

from assisted.models import AssistedTask
from assisted.tests.support import AssistedTestCase


class AssistedTaskModelTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        return AssistedTask.objects.create(**kwargs)

    def test_defaults(self):
        task = self.make_task()

        self.assertEqual(task.status, AssistedTask.Status.QUEUED)
        self.assertEqual(task.submitted_intent, "")
        self.assertEqual(task.failure_reason_code, "")
        self.assertEqual(task.refinement_cycles, 0)
        self.assertEqual(task.context_expansions, 0)
        self.assertIsNone(task.proposal)
        self.assertIsNone(task.ai_execution)

    def test_bootstrap_model_operations_is_create_only(self):
        self.assertEqual(AssistedTask.BOOTSTRAP_MODEL_OPERATIONS, (AssistedTask.Operation.CREATE,))

    def test_two_active_tasks_against_the_same_model_violate_the_partial_unique_constraint(self):
        """
        Defense-in-depth: bypassing assisted.services.lifecycle entirely and
        creating two active rows directly must still be rejected at the DB
        level.
        """

        self.make_task(status=AssistedTask.Status.QUEUED)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_task(status=AssistedTask.Status.RUNNING)

    def test_a_second_terminal_task_against_the_same_model_is_allowed(self):
        self.make_task(status=AssistedTask.Status.FAILED)

        # Does not raise: FAILED is outside the partial index's condition.
        self.make_task(status=AssistedTask.Status.FAILED)

        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 2)

    def test_a_new_active_task_is_allowed_once_the_old_one_is_terminal(self):
        self.make_task(status=AssistedTask.Status.COMPLETED)

        # Does not raise: COMPLETED is outside the partial index's condition.
        self.make_task(status=AssistedTask.Status.QUEUED)

        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 2)
