import uuid

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from account.models import CustomUser
from model.models.model import Model
from model.models.proposal import Proposal
from model.views.active_proposal import (
    get_or_create_active_proposal,
    live_proposals_queryset,
    resolve_active_proposal,
    set_active_proposal_id,
)
from workspace.models import Workspace, WorkspaceMember


def _request_with_session():
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


class ActiveProposalHelperTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="user@example.com",
            password="test-password",
        )

        cls.other_user = CustomUser.objects.create_user(
            email="other@example.com",
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

    def test_resolve_returns_none_with_no_session_pointer(self):
        request = _request_with_session()

        self.assertIsNone(resolve_active_proposal(request, self.model, self.user))

    def test_resolve_returns_none_for_stale_pointer(self):
        request = _request_with_session()

        set_active_proposal_id(request, self.model.id, uuid.uuid4())

        self.assertIsNone(resolve_active_proposal(request, self.model, self.user))

    def test_resolve_ignores_pointer_to_a_proposal_owned_by_another_user(self):
        request = _request_with_session()

        other_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.other_user,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, other_proposal.id)

        self.assertIsNone(resolve_active_proposal(request, self.model, self.user))

    def test_resolve_ignores_pointer_to_a_locked_proposal(self):
        request = _request_with_session()

        queued = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.QUEUED,
        )

        set_active_proposal_id(request, self.model.id, queued.id)

        self.assertIsNone(resolve_active_proposal(request, self.model, self.user))

    def test_resolve_returns_working_proposal_pointed_to_by_session(self):
        request = _request_with_session()

        working = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, working.id)

        self.assertEqual(
            resolve_active_proposal(request, self.model, self.user).id,
            working.id,
        )

    def test_resolve_returns_failed_proposal_pointed_to_by_session(self):
        request = _request_with_session()

        failed = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.FAILED,
        )

        set_active_proposal_id(request, self.model.id, failed.id)

        self.assertEqual(
            resolve_active_proposal(request, self.model, self.user).id,
            failed.id,
        )

    def test_get_or_create_reuses_existing_active_proposal_without_creating(self):
        request = _request_with_session()

        working = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, working.id)

        proposal, error_response = get_or_create_active_proposal(
            request, self.model, self.user,
        )

        self.assertIsNone(error_response)
        self.assertEqual(proposal.id, working.id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 1)

    def test_get_or_create_creates_a_fresh_proposal_when_none_is_active(self):
        request = _request_with_session()

        proposal, error_response = get_or_create_active_proposal(
            request, self.model, self.user,
        )

        self.assertIsNone(error_response)
        self.assertEqual(proposal.status, Proposal.Status.WORKING)
        self.assertEqual(proposal.title, "Proposal 1")

        # The new proposal is now the session's active pointer.
        self.assertEqual(
            resolve_active_proposal(request, self.model, self.user).id,
            proposal.id,
        )

    @override_settings(PROPOSAL_MAX_LIVE_PER_MODEL=5)
    def test_get_or_create_succeeds_at_the_cap_boundary(self):
        request = _request_with_session()

        for _ in range(4):
            Proposal.objects.create(
                model=self.model,
                created_by=self.user,
                status=Proposal.Status.WORKING,
            )

        # No session pointer -- 4 live proposals already exist, one
        # more is still allowed (5th).
        proposal, error_response = get_or_create_active_proposal(
            request, self.model, self.user,
        )

        self.assertIsNone(error_response)
        self.assertIsNotNone(proposal)
        self.assertEqual(
            live_proposals_queryset(self.model, self.user).count(),
            5,
        )

    @override_settings(PROPOSAL_MAX_LIVE_PER_MODEL=5)
    def test_get_or_create_fails_past_the_cap(self):
        request = _request_with_session()

        for _ in range(5):
            Proposal.objects.create(
                model=self.model,
                created_by=self.user,
                status=Proposal.Status.WORKING,
            )

        proposal, error_response = get_or_create_active_proposal(
            request, self.model, self.user,
        )

        self.assertIsNone(proposal)
        self.assertIsNotNone(error_response)
        self.assertEqual(error_response.status_code, 409)
        self.assertEqual(
            live_proposals_queryset(self.model, self.user).count(),
            5,
        )

    def test_resolve_returns_an_ai_sourced_proposal_pointed_to_by_session(self):
        """
        resolve_active_proposal filters on created_by + status only --
        Proposal.source (USER vs AI) is provenance, never a gate on which
        proposal may be the active working context.
        """

        request = _request_with_session()

        ai_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, ai_proposal.id)

        resolved = resolve_active_proposal(request, self.model, self.user)

        self.assertEqual(resolved.id, ai_proposal.id)
        self.assertEqual(resolved.source, Proposal.Source.AI)

    def test_get_or_create_reuses_an_active_ai_proposal_without_creating_a_user_one(self):
        """
        The active AI proposal must not be silently replaced by a fresh
        USER proposal just because the generic get-or-create path doesn't
        know (or care) which source produced the session's active pointer.
        """

        request = _request_with_session()

        ai_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, ai_proposal.id)

        proposal, error_response = get_or_create_active_proposal(
            request, self.model, self.user,
        )

        self.assertIsNone(error_response)
        self.assertEqual(proposal.id, ai_proposal.id)
        self.assertEqual(proposal.source, Proposal.Source.AI)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 1)

    def test_switching_the_active_pointer_from_a_user_to_an_ai_proposal_changes_context(self):
        request = _request_with_session()

        user_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )

        ai_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )

        set_active_proposal_id(request, self.model.id, user_proposal.id)
        self.assertEqual(resolve_active_proposal(request, self.model, self.user).id, user_proposal.id)

        set_active_proposal_id(request, self.model.id, ai_proposal.id)
        self.assertEqual(resolve_active_proposal(request, self.model, self.user).id, ai_proposal.id)

    def test_live_proposals_queryset_includes_unacknowledged_completed_only(self):
        acknowledged = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.COMPLETED,
        )
        acknowledged.acknowledged_at = timezone.now()
        acknowledged.save(update_fields=["acknowledged_at"])

        unacknowledged = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.COMPLETED,
        )

        live_ids = set(
            live_proposals_queryset(self.model, self.user).values_list("id", flat=True)
        )

        self.assertIn(unacknowledged.id, live_ids)
        self.assertNotIn(acknowledged.id, live_ids)
