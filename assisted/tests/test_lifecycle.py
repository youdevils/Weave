from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from ai.services.intent import InvalidIntent
from model.models.model import Model

from assisted.models import AssistedTask, AssistedTaskEvidence
from assisted.services.evidence import AssistedEvidenceInvalid
from assisted.services.lifecycle import AssistedTaskActive, BootstrapModelGone, start_assisted_create
from assisted.tests.support import AssistedTestCase


def _backdate(task, *, minutes):
    AssistedTask.objects.filter(pk=task.pk).update(updated_at=timezone.now() - timedelta(minutes=minutes))


class StartAssistedCreateTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def test_creates_a_queued_task_and_dispatches_on_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            task = start_assisted_create(
                workspace=self.workspace,
                model=self.model,
                user=self.owner,
                intent_text="Track widgets.",
                files=[],
            )

        self.assertEqual(task.status, AssistedTask.Status.QUEUED)
        self.assertEqual(task.model_id, self.model.id)
        self.assertEqual(task.submitted_intent, "Track widgets.")
        self.assertEqual(len(callbacks), 1)

    def test_invalid_intent_rolls_back_the_whole_creation(self):
        with self.assertRaises(InvalidIntent):
            start_assisted_create(
                workspace=self.workspace,
                model=self.model,
                user=self.owner,
                intent_text="   ",
                files=[],
            )

        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)

    @override_settings(ASSISTED_MAX_EVIDENCE_FILES=1)
    def test_invalid_evidence_rolls_back_the_whole_creation_including_the_task(self):
        files = [
            SimpleUploadedFile("a.txt", b"one"),
            SimpleUploadedFile("b.txt", b"two"),
        ]

        with self.assertRaises(AssistedEvidenceInvalid):
            start_assisted_create(
                workspace=self.workspace,
                model=self.model,
                user=self.owner,
                intent_text="Track widgets.",
                files=files,
            )

        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)
        self.assertEqual(AssistedTaskEvidence.objects.count(), 0)

    def test_evidence_is_stored_against_the_task(self):
        files = [SimpleUploadedFile("notes.txt", b"hello evidence")]

        task = start_assisted_create(
            workspace=self.workspace,
            model=self.model,
            user=self.owner,
            intent_text="Track widgets.",
            files=files,
        )

        evidence = task.evidence.get()
        self.assertEqual(evidence.original_filename, "notes.txt")
        self.assertEqual(bytes(evidence.content), b"hello evidence")

    def test_a_second_attempt_against_the_same_model_is_rejected(self):
        start_assisted_create(
            workspace=self.workspace, model=self.model, user=self.owner,
            intent_text="First.", files=[],
        )

        with self.assertRaises(AssistedTaskActive):
            start_assisted_create(
                workspace=self.workspace, model=self.model, user=self.editor,
                intent_text="Second.", files=[],
            )

        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 1)

    def test_a_stale_queued_create_task_is_reclaimed_and_its_model_deleted(self):
        """
        Reclaiming a stale CREATE task deletes its own bootstrap Model (full
        fail_task cleanup, not a bare status flip) -- which, here, is the
        very Model this second call was about to reuse. That must surface
        as a clear BootstrapModelGone, not an IntegrityError from trying to
        create a new AssistedTask against a Model that no longer exists.
        """

        stale = start_assisted_create(
            workspace=self.workspace, model=self.model, user=self.owner,
            intent_text="First.", files=[],
        )
        _backdate(stale, minutes=10)

        with self.assertRaises(BootstrapModelGone):
            start_assisted_create(
                workspace=self.workspace, model=self.model, user=self.owner,
                intent_text="Second.", files=[],
            )

        stale.refresh_from_db()
        self.assertEqual(stale.status, AssistedTask.Status.FAILED)
        self.assertEqual(stale.failure_reason_code, AssistedTask.FailureReasonCode.STALE_TIMED_OUT)
        self.assertIsNone(stale.model)
        self.assertFalse(Model.objects.filter(id=self.model.id).exists())

    def test_a_stale_running_task_is_reclaimed_the_same_way(self):
        stale = start_assisted_create(
            workspace=self.workspace, model=self.model, user=self.owner,
            intent_text="First.", files=[],
        )
        AssistedTask.objects.filter(pk=stale.pk).update(status=AssistedTask.Status.RUNNING)
        _backdate(stale, minutes=20)

        with self.assertRaises(BootstrapModelGone):
            start_assisted_create(
                workspace=self.workspace, model=self.model, user=self.owner,
                intent_text="Second.", files=[],
            )

        stale.refresh_from_db()
        self.assertEqual(stale.status, AssistedTask.Status.FAILED)
        self.assertEqual(stale.failure_reason_code, AssistedTask.FailureReasonCode.STALE_TIMED_OUT)

    def test_a_stale_task_against_a_different_model_does_not_block_this_one(self):
        other_model = self.make_model(name="Other")
        other_stale = start_assisted_create(
            workspace=self.workspace, model=other_model, user=self.owner,
            intent_text="Other.", files=[],
        )
        _backdate(other_stale, minutes=10)

        # Reclaim is scoped per-Model: a stale task against a different
        # Model is left untouched by starting a task against this one.
        start_assisted_create(
            workspace=self.workspace, model=self.model, user=self.owner,
            intent_text="This one.", files=[],
        )

        other_stale.refresh_from_db()
        self.assertEqual(other_stale.status, AssistedTask.Status.QUEUED)
        self.assertTrue(Model.objects.filter(id=other_model.id).exists())

    def test_a_recently_queued_task_is_not_reclaimed(self):
        recent = start_assisted_create(
            workspace=self.workspace, model=self.model, user=self.owner,
            intent_text="First.", files=[],
        )

        with self.assertRaises(AssistedTaskActive):
            start_assisted_create(
                workspace=self.workspace, model=self.model, user=self.editor,
                intent_text="Second.", files=[],
            )

        recent.refresh_from_db()
        self.assertEqual(recent.status, AssistedTask.Status.QUEUED)
