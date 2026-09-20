from datetime import datetime, timezone
from importlib import import_module

from django.apps import apps
from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.proposal import Proposal
from model.models.proposal_submission_result import ProposalSubmissionResult
from workspace.models import Workspace

migration = import_module("model.migrations.0020_evidence_reference_completed_at")


class CompletedAtBackfillTests(TestCase):
    """The migration stamps completed_at on proposals committed before it existed."""

    @classmethod
    def setUpTestData(cls):
        workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        cls.model = Model.objects.create(workspace=workspace, name="Test Model", revision=1)

    def proposal(self, status):
        return Proposal.objects.create(model=self.model, created_by=self.user, status=status)

    def test_completed_proposals_are_stamped_from_their_submission_result(self):
        proposal = self.proposal(Proposal.Status.COMPLETED)
        result = ProposalSubmissionResult.objects.create(
            proposal=proposal, outcome=ProposalSubmissionResult.Outcome.SUCCESS, before_revision=1, after_revision=2
        )
        committed = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
        ProposalSubmissionResult.objects.filter(pk=result.pk).update(updated_at=committed)

        migration.backfill_completed_at(apps, None)

        proposal.refresh_from_db()
        self.assertEqual(proposal.completed_at, committed)

    def test_a_completed_proposal_without_a_result_falls_back_to_updated_at(self):
        proposal = self.proposal(Proposal.Status.COMPLETED)

        migration.backfill_completed_at(apps, None)

        proposal.refresh_from_db()
        self.assertEqual(proposal.completed_at, proposal.updated_at)

    def test_other_statuses_and_existing_values_are_left_alone(self):
        untouched = [
            self.proposal(status)
            for status in (Proposal.Status.WORKING, Proposal.Status.FAILED, Proposal.Status.QUEUED)
        ]
        stamped = self.proposal(Proposal.Status.COMPLETED)
        original = datetime(2026, 2, 1, tzinfo=timezone.utc)
        Proposal.objects.filter(pk=stamped.pk).update(completed_at=original)

        migration.backfill_completed_at(apps, None)

        for proposal in untouched:
            proposal.refresh_from_db()
            self.assertIsNone(proposal.completed_at)
        stamped.refresh_from_db()
        self.assertEqual(stamped.completed_at, original)
