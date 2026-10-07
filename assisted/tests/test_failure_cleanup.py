"""
End-to-end: every outcome that fails an Assisted Create task leaves the same
shape behind -- bootstrap Model gone, AssistedTask.model/proposal/ai_execution
all NULL, and the denormalized failure/outcome fields intact even though
the Model (and therefore the AIExecution row, which CASCADEs with it) no
longer exists to read them back from.
"""

from django.test import override_settings

from model.models.model import Model

from ai.services.provider import ProviderError

from assisted.models import AssistedTask
from assisted.services import execution
from assisted.tests.support import (
    AssistedTestCase,
    RaisingProvider,
    ScriptedProvider,
    clarification_result,
    no_change_result,
    unresolved_result,
)


class FailureCleanupTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def make_task(self):
        return AssistedTask.objects.create(
            workspace=self.workspace,
            creator=self.owner,
            operation=AssistedTask.Operation.CREATE,
            model=self.model,
            status=AssistedTask.Status.QUEUED,
            submitted_intent="Track widgets.",
        )

    def assert_cleaned_up(self, task, *, failure_reason_code):
        self.assertFalse(Model.objects.filter(id=self.model.id).exists())

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, failure_reason_code)
        self.assertNotEqual(task.failure_reason, "")
        self.assertIsNotNone(task.failed_at)
        self.assertIsNone(task.model)
        self.assertIsNone(task.proposal)
        self.assertIsNone(task.ai_execution)

    def test_provider_error(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=RaisingProvider(ProviderError("boom")))

        self.assert_cleaned_up(task, failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED)

    def test_needs_clarification(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([clarification_result()]))

        self.assert_cleaned_up(task, failure_reason_code=AssistedTask.FailureReasonCode.NEEDS_CLARIFICATION)

    def test_no_change_required(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        self.assert_cleaned_up(task, failure_reason_code=AssistedTask.FailureReasonCode.NO_CHANGE_PRODUCED)

    def test_unresolved(self):
        task = self.make_task()

        with override_settings(AI_CREATE_PLANNING_MAX_CALLS=1):
            execution.run_and_finish(task.id, provider=ScriptedProvider([unresolved_result()] * 2))

        self.assert_cleaned_up(task, failure_reason_code=AssistedTask.FailureReasonCode.UNRESOLVED)
