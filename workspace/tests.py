import uuid

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask

CONFIRMATION = (
    "This will permanently delete the model and all of its data, including "
    "objects, relationships, proposals and evidence. This cannot be undone."
)


class DeleteModelViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Mine")
        cls.other_workspace = Workspace.objects.create(name="Theirs")

        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="pw")

        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.owner, role=WorkspaceMember.Role.OWNER
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.editor, role=WorkspaceMember.Role.EDITOR
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.viewer, role=WorkspaceMember.Role.VIEWER
        )
        WorkspaceMember.objects.create(
            workspace=cls.other_workspace, user=cls.stranger, role=WorkspaceMember.Role.OWNER
        )

    def build_model(self, workspace, name, proposal_status=Proposal.Status.WORKING):
        model = Model.objects.create(workspace=workspace, name=name)

        person = ObjectType.objects.create(model=model, name="Person", key="person")
        knows = RelationshipType.objects.create(model=model, name="Knows", key="knows")
        alice = Object.objects.create(model=model, object_type=person, name="Alice")
        bob = Object.objects.create(model=model, object_type=person, name="Bob")
        Relationship.objects.create(
            model=model, relationship_type=knows, subject=alice, object=bob
        )

        proposal = Proposal.objects.create(
            model=model,
            created_by=self.owner if workspace == self.workspace else self.stranger,
            status=proposal_status,
        )
        change = ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=uuid.uuid4(),
            parent_type="Model",
            parent_id=model.id,
            after={"name": "Thing"},
        )
        EvidenceReference.objects.create(change=change, source="Spec")

        return model

    def delete_url(self, model):
        return reverse("workspace:delete_model", args=[model.id])

    def message_texts(self, response):
        return [str(message) for message in get_messages(response.wsgi_request)]

    def assert_untouched(self, model):
        self.assertTrue(Model.objects.filter(id=model.id).exists())
        self.assertEqual(Object.objects.filter(model=model).count(), 2)
        self.assertEqual(Relationship.objects.filter(model=model).count(), 1)
        self.assertEqual(Proposal.objects.filter(model=model).count(), 1)
        self.assertEqual(ProposalChange.objects.filter(proposal__model=model).count(), 1)
        self.assertEqual(EvidenceReference.objects.filter(change__proposal__model=model).count(), 1)

    # ---------------------------------------------------------------
    # Success
    # ---------------------------------------------------------------

    def test_owner_deletes_the_model_and_returns_to_the_workspace(self):
        doomed = self.build_model(self.workspace, "Doomed")
        kept = self.build_model(self.workspace, "Kept")
        self.client.force_login(self.owner)

        response = self.client.post(self.delete_url(doomed), follow=True)

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertFalse(Model.objects.filter(id=doomed.id).exists())
        self.assertEqual(Object.objects.filter(model=doomed).count(), 0)
        self.assertEqual(Proposal.objects.filter(model=doomed).count(), 0)
        self.assertEqual(ProposalChange.objects.filter(proposal__model=doomed).count(), 0)
        self.assertEqual(EvidenceReference.objects.filter(change__proposal__model=doomed).count(), 0)

        # The remaining model is untouched and still listed; the deleted one is not.
        self.assert_untouched(kept)
        self.assertContains(response, "Kept")
        self.assertNotContains(response, reverse("model:overview", args=[doomed.id]))
        self.assertContains(response, "permanently deleted")

    def test_no_model_owned_rows_are_left_behind(self):
        model = self.build_model(self.workspace, "Only")
        self.client.force_login(self.owner)

        self.client.post(self.delete_url(model))

        for table in (
            ObjectType,
            RelationshipType,
            Object,
            Relationship,
            Proposal,
            ProposalChange,
            EvidenceReference,
        ):
            self.assertEqual(table.objects.count(), 0, table.__name__)

    # ---------------------------------------------------------------
    # Not allowed
    # ---------------------------------------------------------------

    def test_a_user_outside_the_workspace_cannot_delete_it(self):
        model = self.build_model(self.workspace, "Mine")
        self.client.force_login(self.stranger)

        response = self.client.post(self.delete_url(model))

        self.assertEqual(response.status_code, 404)
        self.assert_untouched(model)

    def test_a_workspace_member_who_is_not_an_owner_cannot_delete_it(self):
        model = self.build_model(self.workspace, "Mine")

        for user in (self.editor, self.viewer):
            with self.subTest(user=user.email):
                self.client.force_login(user)

                response = self.client.post(self.delete_url(model))

                self.assertEqual(response.status_code, 403)
                self.assert_untouched(model)

    def test_anonymous_users_are_sent_to_log_in(self):
        model = self.build_model(self.workspace, "Mine")

        response = self.client.post(self.delete_url(model))

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], reverse("workspace:index"))
        self.assert_untouched(model)

    def test_get_does_not_delete(self):
        model = self.build_model(self.workspace, "Mine")
        self.client.force_login(self.owner)

        response = self.client.get(self.delete_url(model))

        self.assertEqual(response.status_code, 405)
        self.assert_untouched(model)

    def test_unknown_model_is_not_found(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("workspace:delete_model", args=[uuid.uuid4()])
        )

        self.assertEqual(response.status_code, 404)

    # ---------------------------------------------------------------
    # Background processing
    # ---------------------------------------------------------------

    def test_a_model_with_a_proposal_in_flight_is_not_deleted(self):
        for status in (Proposal.Status.QUEUED, Proposal.Status.PROCESSING):
            with self.subTest(status=status):
                model = self.build_model(self.workspace, f"Busy {status}", status)
                self.client.force_login(self.owner)

                response = self.client.post(self.delete_url(model), follow=True)

                self.assertRedirects(response, reverse("workspace:index"))
                self.assertTrue(Model.objects.filter(id=model.id).exists())
                self.assertContains(response, "queued or being processed")
                self.assertContains(response, f"Busy {status}")

    def test_a_model_with_an_active_assisted_task_is_not_deleted(self):
        for status in (
            AssistedTask.Status.QUEUED,
            AssistedTask.Status.RUNNING,
            AssistedTask.Status.READY_FOR_REVIEW,
        ):
            with self.subTest(status=status):
                model = self.build_model(self.workspace, f"Assisted {status}")
                AssistedTask.objects.create(
                    workspace=self.workspace,
                    creator=self.owner,
                    operation=AssistedTask.Operation.CREATE,
                    model=model,
                    status=status,
                    submitted_intent="Track widgets.",
                )
                self.client.force_login(self.owner)

                response = self.client.post(self.delete_url(model), follow=True)

                self.assertRedirects(response, reverse("workspace:index"))
                self.assertTrue(Model.objects.filter(id=model.id).exists())
                self.assertContains(response, "assisted operation in progress")


class DashboardDeleteControlTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Mine")
        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")

        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.owner, role=WorkspaceMember.Role.OWNER
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.viewer, role=WorkspaceMember.Role.VIEWER
        )

        cls.model = Model.objects.create(workspace=cls.workspace, name="Mine")

    def test_owner_sees_a_delete_action_with_an_explicit_confirmation(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("workspace:index"))

        self.assertContains(response, "Delete this model?")
        self.assertContains(response, CONFIRMATION)
        self.assertContains(
            response,
            f'action="{reverse("workspace:delete_model", args=[self.model.id])}"',
        )

    def test_the_only_way_to_delete_is_the_confirmation_form(self):
        # The card's Delete button only opens the modal; no link deletes.
        self.client.force_login(self.owner)

        response = self.client.get(reverse("workspace:index"))

        self.assertContains(response, 'data-bs-toggle="modal"')
        self.assertContains(response, "data-bs-dismiss=\"modal\"")
        self.assertContains(response, "Cancel")
        self.assertEqual(Model.objects.filter(id=self.model.id).count(), 1)

    def test_a_viewer_is_not_offered_deletion(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("workspace:index"))

        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Delete this model?")
        self.assertNotContains(response, reverse("workspace:delete_model", args=[self.model.id]))
