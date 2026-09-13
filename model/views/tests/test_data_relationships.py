import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace, WorkspaceMember


class DataRelationshipsIndexViewTests(TestCase):

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

        cls.process_type = ObjectType.objects.create(
            model=cls.model, name="Process", key="process", is_active=True,
        )
        cls.app_type = ObjectType.objects.create(
            model=cls.model, name="Application", key="application", is_active=True,
        )

        cls.uses_type = RelationshipType.objects.create(
            model=cls.model, name="Uses", key="uses", is_active=True,
        )

        RelationshipTypeRule.objects.create(
            relationship_type=cls.uses_type,
            subject_type=cls.process_type,
            object_type=cls.app_type,
            subject_minimum=0,
            object_minimum=0,
        )

        cls.criticality_attribute = AttributeDefinition.objects.create(
            relationship_type=cls.uses_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self):
        return reverse(
            "model:data_relationships",
            args=[self.model.id, self.uses_type.id],
        )

    def test_empty_state_renders(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No uses relationships yet")

    def test_columns_include_active_attribute(self):
        response = self.client.get(self._url())

        self.assertIn(self.criticality_attribute, response.context["columns"])

    def test_lists_canonical_relationships_with_endpoints(self):
        finance = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Finance Reporting",
        )
        power_bi = Object.objects.create(
            model=self.model, object_type=self.app_type, name="Power BI",
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=finance,
            object=power_bi,
            attributes={"criticality": "High"},
        )

        response = self.client.get(self._url())

        self.assertContains(response, "Finance Reporting")
        self.assertContains(response, "Power BI")
        self.assertContains(response, "High")

    def test_search_filters_by_subject_or_object_name(self):
        finance = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Finance Reporting",
        )
        claims = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Claims Processing",
        )
        power_bi = Object.objects.create(
            model=self.model, object_type=self.app_type, name="Power BI",
        )

        Relationship.objects.create(
            model=self.model, relationship_type=self.uses_type, subject=finance, object=power_bi,
        )
        Relationship.objects.create(
            model=self.model, relationship_type=self.uses_type, subject=claims, object=power_bi,
        )

        response = self.client.get(self._url(), {"q": "Finance"})

        self.assertContains(response, "Finance Reporting")
        self.assertNotContains(response, "Claims Processing")

    def test_pending_relationship_resolves_endpoint_names_from_create_payloads(self):
        finance = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Finance Reporting",
        )
        power_bi = Object.objects.create(
            model=self.model, object_type=self.app_type, name="Power BI",
        )

        proposal = ProposalService.get_or_create_working(self.model, self.user)

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Relationship",
            target_id=uuid.uuid4(),
            parent_type="RelationshipType",
            parent_id=self.uses_type.id,
            before=None,
            after={
                "subject_id": str(finance.id),
                "object_id": str(power_bi.id),
                "is_active": True,
                "attributes": {},
            },
        )

        response = self.client.get(self._url())

        self.assertEqual(len(response.context["rows"]), 0)
        self.assertEqual(len(response.context["pending_rows"]), 1)
        self.assertEqual(response.context["pending_rows"][0].subject_name, "Finance Reporting")
        self.assertEqual(response.context["pending_rows"][0].object_name, "Power BI")

        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 0)
