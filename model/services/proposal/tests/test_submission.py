import uuid
from unittest.mock import patch

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


def _drain(model_id):
    """
    Simulate what the Celery task chain does, without touching Celery:
    repeatedly claim and process the next queued proposal for a Model
    until nothing is left to claim.
    """

    while True:
        proposal = submission.claim_next(model_id)

        if proposal is None:
            return

        submission.process(proposal.id)


class SubmissionTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="submitter@example.com",
            password="test-password",
        )

    def _new_model(self, name="Test Model", revision=1):
        return Model.objects.create(
            workspace=self.workspace,
            name=name,
            revision=revision,
        )

    def _submit_object_type_create(self, model, key, user=None):
        """
        Build a working proposal containing a single ObjectType CREATE
        change and submit it. Returns (proposal, object_type_id).
        """

        proposal = ProposalService.get_or_create_working(model, user or self.user)

        object_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": key.title(),
                "key": key,
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        ProposalService.submit(proposal)

        return proposal, object_type_id


class QueueOrderingTests(SubmissionTestCase):

    def test_serial_processing_for_one_model(self):
        model = self._new_model(revision=1)

        proposal_1, object_type_1 = self._submit_object_type_create(model, "alpha")
        proposal_2, object_type_2 = self._submit_object_type_create(
            model,
            "beta",
            user=CustomUser.objects.create_user(
                email="second@example.com", password="test-password"
            ),
        )
        proposal_3, object_type_3 = self._submit_object_type_create(
            model,
            "gamma",
            user=CustomUser.objects.create_user(
                email="third@example.com", password="test-password"
            ),
        )

        _drain(model.id)

        for proposal in (proposal_1, proposal_2, proposal_3):
            proposal.refresh_from_db()
            self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        model.refresh_from_db()
        self.assertEqual(model.revision, 4)

        self.assertTrue(ObjectType.objects.filter(id=object_type_1, key="alpha").exists())
        self.assertTrue(ObjectType.objects.filter(id=object_type_2, key="beta").exists())
        self.assertTrue(ObjectType.objects.filter(id=object_type_3, key="gamma").exists())

    def test_independent_models_process_independently(self):
        model_a = self._new_model(name="Model A", revision=1)
        model_b = self._new_model(name="Model B", revision=1)

        proposal_a, object_type_a = self._submit_object_type_create(model_a, "alpha")
        proposal_b, object_type_b = self._submit_object_type_create(model_b, "beta")

        claimed_a = submission.claim_next(model_a.id)
        self.assertEqual(claimed_a.id, proposal_a.id)

        # Model B's queue is unaffected by Model A's in-flight PROCESSING proposal.
        claimed_b = submission.claim_next(model_b.id)
        self.assertEqual(claimed_b.id, proposal_b.id)

        submission.process(claimed_a.id)
        submission.process(claimed_b.id)

        proposal_a.refresh_from_db()
        proposal_b.refresh_from_db()
        model_a.refresh_from_db()
        model_b.refresh_from_db()

        self.assertEqual(proposal_a.status, Proposal.Status.COMPLETED)
        self.assertEqual(proposal_b.status, Proposal.Status.COMPLETED)
        self.assertEqual(model_a.revision, 2)
        self.assertEqual(model_b.revision, 2)


class ProcessingAgainstCurrentStateTests(SubmissionTestCase):

    def test_revision_advancing_alone_does_not_reject(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # Simulate an unrelated intervening commit: nothing conflicts,
        # only the revision moves.
        model.revision = 5
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(model.revision, 6)
        self.assertTrue(ObjectType.objects.filter(id=object_type_id).exists())

    def test_proposal_still_valid_after_intervening_commit_succeeds(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # An unrelated ObjectType lands canonically before this
        # proposal is processed -- no conflict with "alpha".
        ObjectType.objects.create(model=model, name="Beta", key="beta")
        model.revision = 2
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertTrue(ObjectType.objects.filter(id=object_type_id, key="alpha").exists())

    def test_proposal_invalidated_by_intervening_commit_fails(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # A conflicting ObjectType with the same key lands canonically
        # (as if a different proposal committed first) before this
        # one is processed -- validates against CURRENT state, not
        # the state at submit time.
        ObjectType.objects.create(model=model, name="Alpha (existing)", key="alpha")
        model.revision = 2
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.FAILED)

        result = proposal.submission_result
        self.assertEqual(result.outcome, result.Outcome.VALIDATION_FAILED)

        error = result.errors.get()
        self.assertEqual(error.code, "duplicate_key")
        self.assertEqual(error.change.target_type, "ObjectType")
        self.assertEqual(error.change.target_id, object_type_id)

        # Nothing from this proposal was committed.
        self.assertFalse(
            ObjectType.objects.filter(id=object_type_id).exists()
        )


class ErrorAttributionTests(SubmissionTestCase):

    def test_errors_attributed_to_correct_proposal_change(self):
        model = self._new_model(revision=1)

        ObjectType.objects.create(model=model, name="Existing", key="existing")

        proposal = ProposalService.get_or_create_working(model, self.user)

        duplicate_object_type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=duplicate_object_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": "Existing (duplicate)",
                "key": "existing",
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            field="not_a_real_field",
            before={"field": "not_a_real_field", "value": "x"},
            after={"field": "not_a_real_field", "value": "y"},
        )

        ProposalService.submit(proposal)
        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.FAILED)

        errors = list(proposal.submission_result.errors.all())
        self.assertEqual(len(errors), 2)

        errors_by_code = {error.code: error for error in errors}

        self.assertEqual(
            errors_by_code["duplicate_key"].change.target_id,
            duplicate_object_type_id,
        )
        self.assertEqual(
            errors_by_code["invalid_change"].change.target_type,
            "Model",
        )
        self.assertNotEqual(
            errors_by_code["duplicate_key"].change_id,
            errors_by_code["invalid_change"].change_id,
        )


class CommitAtomicityTests(SubmissionTestCase):

    def test_failed_validation_leaves_no_canonical_changes(self):
        model = self._new_model(revision=1)

        ObjectType.objects.create(model=model, name="Existing", key="existing")

        proposal = ProposalService.get_or_create_working(model, self.user)

        conflicting_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=conflicting_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": "Existing (duplicate)",
                "key": "existing",
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        ProposalService.submit(proposal)

        object_type_count_before = ObjectType.objects.count()
        revision_before = model.revision

        submission.process(submission.claim_next(model.id).id)

        model.refresh_from_db()

        self.assertEqual(ObjectType.objects.count(), object_type_count_before)
        self.assertEqual(model.revision, revision_before)
        self.assertFalse(ObjectType.objects.filter(id=conflicting_id).exists())

    def test_successful_commit_is_atomic_and_revision_increments_once(self):
        model = self._new_model(revision=1)

        proposal = ProposalService.get_or_create_working(model, self.user)

        object_type_ids = [uuid.uuid4() for _ in range(3)]

        for index, object_type_id in enumerate(object_type_ids):
            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.CREATE,
                target_type="ObjectType",
                target_id=object_type_id,
                parent_type="Model",
                parent_id=model.id,
                before=None,
                after={
                    "name": f"Type {index}",
                    "key": f"type-{index}",
                    "description": "",
                    "sort_order": 0,
                    "is_active": True,
                },
            )

        ProposalService.submit(proposal)
        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(model.revision, 2)

        for object_type_id in object_type_ids:
            self.assertTrue(ObjectType.objects.filter(id=object_type_id).exists())

    def test_successful_proposal_remains_complete_historical_record(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")
        change_id = proposal.changes.get().id

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertTrue(Proposal.objects.filter(id=proposal.id).exists())
        self.assertTrue(ProposalChange.objects.filter(id=change_id).exists())
        self.assertEqual(proposal.changes.count(), 1)

    def test_unexpected_exception_during_commit_rolls_back_and_records_system_error(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        revision_before = model.revision
        object_type_count_before = ObjectType.objects.count()

        with patch(
            "model.services.proposal.submission.validate_model",
            side_effect=RuntimeError("super-secret-internal-detail"),
        ):
            submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(model.revision, revision_before)
        self.assertEqual(ObjectType.objects.count(), object_type_count_before)
        self.assertFalse(ObjectType.objects.filter(id=object_type_id).exists())

        result = proposal.submission_result
        self.assertEqual(result.outcome, result.Outcome.SYSTEM_ERROR)
        self.assertNotIn("super-secret-internal-detail", result.message)


class QueueDrainDispatchTests(SubmissionTestCase):

    def test_queue_drain_dispatch_only_follows_durable_commit(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")
        claimed = submission.claim_next(model.id)

        with patch(
            "model.tasks.proposal_tasks.process_next_for_model.delay"
        ) as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                submission.process(claimed.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        # Dispatched exactly once, and only after the proposal's
        # final COMPLETED state is what a fresh query would see --
        # i.e. execute=True only ran callbacks from transactions that
        # actually committed within the captured block.
        mock_delay.assert_called_once_with(str(model.id))
