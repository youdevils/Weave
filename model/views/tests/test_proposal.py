import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import (
    ProposalSubmissionResult,
    ProposalValidationError,
)
from model.services.proposal.proposal import ProposalService
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class ProposalViewTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="user@example.com",
            password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.workspace,
            user=cls.user,
            role=WorkspaceMember.Role.OWNER,
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
            revision=1,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _make_proposal(self, status=Proposal.Status.WORKING, with_change=True):
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=status,
        )

        if with_change:
            ProposalChange.objects.create(
                proposal=proposal,
                source=ProposalChange.Source.USER,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Model",
                target_id=self.model.id,
                before={"field": "description", "value": "Old"},
                after={"field": "description", "value": "New"},
            )

        return proposal

    def detail_url(self, proposal):
        return reverse("model:proposal", args=[self.model.id, proposal.id])

    def list_url(self):
        return reverse("model:proposal_list", args=[self.model.id])

    def create_url(self):
        return reverse("model:proposal_create", args=[self.model.id])


class ProposalListRedirectTests(ProposalViewTestCase):

    def test_no_proposals_redirects_to_overview(self):
        response = self.client.get(self.list_url())

        self.assertRedirects(
            response,
            reverse("model:overview", args=[self.model.id]),
        )

    def test_redirects_to_active_proposal_when_one_is_active(self):
        proposal = self._make_proposal()
        activate_proposal(self.client, self.model.id, proposal)

        response = self.client.get(self.list_url())

        self.assertRedirects(response, self.detail_url(proposal))

    def test_redirects_to_most_recent_live_proposal_when_none_active(self):
        self._make_proposal()
        newest = self._make_proposal()

        response = self.client.get(self.list_url())

        self.assertRedirects(response, self.detail_url(newest))


class ProposalCreateTests(ProposalViewTestCase):

    def test_create_makes_a_new_active_working_proposal(self):
        response = self.client.post(self.create_url())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        proposal = Proposal.objects.get(model=self.model, created_by=self.user)
        self.assertEqual(proposal.status, Proposal.Status.WORKING)
        self.assertEqual(proposal.title, "Proposal 1")
        self.assertEqual(data["redirect_url"], self.detail_url(proposal))

    def test_create_enforces_the_live_proposal_cap(self):
        for _ in range(5):
            self._make_proposal()

        response = self.client.post(self.create_url())

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertEqual(
            Proposal.objects.filter(model=self.model).count(),
            5,
        )

    def test_create_always_makes_a_new_proposal_even_if_one_is_active(self):
        first = self._make_proposal()
        activate_proposal(self.client, self.model.id, first)

        response = self.client.post(self.create_url())
        data = response.json()

        second_id = uuid.UUID(data["redirect_url"].rstrip("/").rsplit("/", 1)[-1])
        self.assertNotEqual(second_id, first.id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 2)


class ProposalSelectionTests(ProposalViewTestCase):

    def test_viewing_a_working_proposal_makes_it_active(self):
        proposal = self._make_proposal()

        self.client.get(self.detail_url(proposal))

        # A second request carrying the same session should now
        # redirect straight to it as the active proposal.
        second_response = self.client.get(self.list_url())
        self.assertRedirects(second_response, self.detail_url(proposal))

    def test_viewing_a_queued_proposal_does_not_make_it_active(self):
        working = self._make_proposal()
        activate_proposal(self.client, self.model.id, working)

        queued = self._make_proposal(status=Proposal.Status.QUEUED)

        response = self.client.get(self.detail_url(queued))
        self.assertEqual(response.status_code, 200)

        # The originally active WORKING proposal is still active.
        list_response = self.client.get(self.list_url())
        self.assertRedirects(list_response, self.detail_url(working))

    def test_viewing_a_completed_proposal_does_not_make_it_active(self):
        completed = self._make_proposal(status=Proposal.Status.COMPLETED)

        response = self.client.get(self.detail_url(completed))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["active_proposal"])

        # An unacknowledged COMPLETED proposal is still "live" (it
        # stays in the workspace until acknowledged), so with no
        # active editable proposal the list falls back to it -- but
        # it never became the *active* (editable) one.
        list_response = self.client.get(self.list_url())
        self.assertRedirects(list_response, self.detail_url(completed))


class ProposalRenameTests(ProposalViewTestCase):

    def test_rename_succeeds_regardless_of_status(self):
        for status in (
            Proposal.Status.WORKING,
            Proposal.Status.QUEUED,
            Proposal.Status.COMPLETED,
        ):
            proposal = self._make_proposal(status=status)

            response = self.client.post(
                self.detail_url(proposal),
                {"action": "rename", "title": f"Renamed {status}"},
            )

            self.assertTrue(response.json()["success"])
            proposal.refresh_from_db()
            self.assertEqual(proposal.title, f"Renamed {status}")


class ProposalSubmitTests(ProposalViewTestCase):

    def test_submit_moves_working_proposal_to_queued(self):
        proposal = self._make_proposal()

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "submit"},
        )

        self.assertTrue(response.json()["success"])
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.QUEUED)
        self.assertIsNotNone(proposal.submitted_at)

    def test_submit_without_changes_is_rejected(self):
        proposal = self._make_proposal(with_change=False)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "submit"},
        )

        self.assertEqual(response.status_code, 400)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.WORKING)

    def test_submit_is_rejected_for_a_locked_proposal(self):
        proposal = self._make_proposal(status=Proposal.Status.QUEUED)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "submit"},
        )

        self.assertEqual(response.status_code, 400)


class ProposalAbandonTests(ProposalViewTestCase):

    def test_abandon_deletes_an_editable_proposal(self):
        proposal = self._make_proposal()
        activate_proposal(self.client, self.model.id, proposal)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "abandon"},
        )
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["redirect_url"], self.list_url())
        self.assertFalse(Proposal.objects.filter(id=proposal.id).exists())

    def test_abandoning_the_last_proposal_ends_on_model_overview(self):
        proposal = self._make_proposal()
        activate_proposal(self.client, self.model.id, proposal)

        data = self.client.post(
            self.detail_url(proposal),
            {"action": "abandon"},
        ).json()

        response = self.client.get(data["redirect_url"], follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0],
            reverse("model:overview", args=[self.model.id]),
        )

    def test_abandon_is_rejected_for_a_locked_proposal(self):
        proposal = self._make_proposal(status=Proposal.Status.COMPLETED)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "abandon"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Proposal.objects.filter(id=proposal.id).exists())


class ProposalAcknowledgeTests(ProposalViewTestCase):

    def test_acknowledge_marks_completed_proposal_and_drops_from_live_list(self):
        proposal = self._make_proposal(status=Proposal.Status.COMPLETED)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "acknowledge"},
        )
        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(
            data["redirect_url"],
            reverse("model:overview", args=[self.model.id]),
        )
        proposal.refresh_from_db()
        self.assertIsNotNone(proposal.acknowledged_at)

        from model.views.active_proposal import live_proposals_queryset
        self.assertNotIn(
            proposal.id,
            live_proposals_queryset(self.model, self.user).values_list("id", flat=True),
        )

    def test_completed_proposal_page_offers_acknowledge(self):
        proposal = self._make_proposal(status=Proposal.Status.COMPLETED)

        response = self.client.get(self.detail_url(proposal))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "model-proposal-acknowledge")
        self.assertContains(response, "Committed successfully")

    def test_acknowledge_is_rejected_for_a_non_completed_proposal(self):
        proposal = self._make_proposal(status=Proposal.Status.WORKING)

        response = self.client.post(
            self.detail_url(proposal),
            {"action": "acknowledge"},
        )

        self.assertEqual(response.status_code, 400)


class ProposalReadOnlyEnforcementTests(ProposalViewTestCase):

    def test_locked_statuses_reject_discard_review_and_bulk_actions(self):
        for status in (
            Proposal.Status.QUEUED,
            Proposal.Status.PROCESSING,
            Proposal.Status.COMPLETED,
        ):
            proposal = self._make_proposal(status=status)
            change = proposal.changes.first()

            for action, extra in (
                ("discard", {"change_id": str(change.id)}),
                ("review", {"change_id": str(change.id)}),
                ("unreview", {"change_id": str(change.id)}),
                ("review_all", {}),
                ("unreview_all", {}),
            ):
                response = self.client.post(
                    self.detail_url(proposal),
                    {"action": action, **extra},
                )
                self.assertEqual(
                    response.status_code, 400,
                    f"expected 400 for action={action} on status={status}",
                )


class ProposalFailedStateTests(ProposalViewTestCase):

    def test_validation_errors_are_attached_to_their_change_and_unlinked_ones_are_separate(self):
        proposal = self._make_proposal(status=Proposal.Status.FAILED)
        change = proposal.changes.first()

        result = ProposalSubmissionResult.objects.create(
            proposal=proposal,
            outcome=ProposalSubmissionResult.Outcome.VALIDATION_FAILED,
            before_revision=1,
        )

        linked_error = ProposalValidationError.objects.create(
            result=result,
            change=change,
            code="duplicate_key",
            message="This key is already in use.",
        )

        unlinked_error = ProposalValidationError.objects.create(
            result=result,
            change=None,
            code="invalid_change",
            message="Something about the whole proposal.",
        )

        response = self.client.get(self.detail_url(proposal))

        rendered_change = next(
            c for c in response.context["changes"] if c.id == change.id
        )
        self.assertEqual(
            [e.id for e in rendered_change.review_validation_errors],
            [linked_error.id],
        )
        self.assertEqual(
            [e.id for e in response.context["unlinked_validation_errors"]],
            [unlinked_error.id],
        )

    def test_system_error_message_is_surfaced_without_leaking_details(self):
        proposal = self._make_proposal(status=Proposal.Status.FAILED)

        ProposalSubmissionResult.objects.create(
            proposal=proposal,
            outcome=ProposalSubmissionResult.Outcome.SYSTEM_ERROR,
            message="An unexpected error occurred while processing this proposal.",
        )

        response = self.client.get(self.detail_url(proposal))

        self.assertContains(
            response,
            "An unexpected error occurred while processing this proposal.",
        )
