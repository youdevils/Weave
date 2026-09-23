from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal
from model.services.model_template.loader import TEMPLATES, template_has_data
from workspace.models import Workspace, WorkspaceMember


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="owner@example.com",
            password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.workspace,
            user=cls.user,
            role=WorkspaceMember.Role.OWNER,
        )

    def make_model(self):
        return Model.objects.create(workspace=self.workspace, name="M")


class ModelTemplateReviewSuccessTests(Base):

    def setUp(self):
        self.client.force_login(self.user)

    def test_successful_instantiation_redirects_to_workspace_index(self):
        model = self.make_model()

        response = self.client.post(
            reverse(
                "workspace:model_template_review",
                kwargs={"model_id": model.id, "template_key": "delivery_project"},
            )
        )

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertEqual(ObjectType.objects.filter(model=model).count(), 15)

        proposal = Proposal.objects.get(model=model)
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)


class ModelTemplateReviewFailureTests(Base):

    def setUp(self):
        self.client.force_login(self.user)

    def test_failed_instantiation_removes_the_model_and_shows_the_user_facing_message(self):
        model = self.make_model()

        broken_template = {
            "key": "broken",
            "name": "Broken",
            "description": "",
            "object_types": [
                {"key": "a", "name": "A", "description": "", "sort_order": 0, "attributes": []},
                {"key": "b", "name": "B", "description": "", "sort_order": 0, "attributes": []},
            ],
            "relationship_types": [
                {
                    "key": "r",
                    "name": "R",
                    "description": "",
                    "sort_order": 0,
                    "attributes": [],
                    "rules": [
                        {
                            "subject_type": "a",
                            "object_type": "b",
                            "subject_minimum": 0,
                            "subject_maximum": None,
                            "object_minimum": 1,
                            "object_maximum": None,
                        },
                    ],
                },
            ],
            "objects": [
                {"key": "a1", "type": "a", "name": "A1", "description": "", "attributes": {}},
                {"key": "b1", "type": "b", "name": "B1", "description": "", "attributes": {}},
            ],
            "relationships": [],
        }

        TEMPLATES["broken"] = broken_template
        self.addCleanup(TEMPLATES.pop, "broken", None)

        response = self.client.post(
            reverse(
                "workspace:model_template_review",
                kwargs={"model_id": model.id, "template_key": "broken"},
            ),
            follow=True,
        )

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertFalse(Model.objects.filter(id=model.id).exists())

        messages = list(response.context["messages"])
        self.assertTrue(
            any(
                "could not be created from this template" in str(message)
                for message in messages
            )
        )


class ModelStartingPointTests(Base):

    def setUp(self):
        self.client.force_login(self.user)

    def test_starting_point_cards_show_model_and_data_pills(self):
        model = self.make_model()

        response = self.client.get(
            reverse("workspace:model_starting_point", kwargs={"model_id": model.id})
        )

        self.assertContains(response, "MODEL")
        self.assertContains(response, "DATA")

    def test_has_data_is_derived_from_template_content_not_hard_coded(self):
        with_data = {"objects": [{"key": "o", "type": "t", "name": "O"}]}
        without_data = {"objects": []}
        also_without_data = {}

        self.assertTrue(template_has_data(with_data))
        self.assertFalse(template_has_data(without_data))
        self.assertFalse(template_has_data(also_without_data))
