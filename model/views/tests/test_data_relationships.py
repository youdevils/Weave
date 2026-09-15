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
from model.views.tests.proposal_test_utils import activate_proposal
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
        activate_proposal(self.client, self.model.id, proposal)

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

    def test_pending_relationship_with_proposal_only_endpoint_does_not_show_unknown(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

        power_bi_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=power_bi_id,
            parent_type="ObjectType",
            parent_id=self.app_type.id,
            before=None,
            after={"name": "Power BI", "description": "", "is_active": True, "attributes": {}},
        )

        finance = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Finance Reporting",
        )

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
                "object_id": str(power_bi_id),
                "is_active": True,
                "attributes": {},
            },
        )

        response = self.client.get(self._url())

        pending = response.context["pending_rows"][0]
        self.assertEqual(pending.subject_name, "Finance Reporting")
        self.assertEqual(pending.object_name, "Power BI")
        self.assertNotEqual(pending.object_name, "Unknown")


class DataProposalOnlyRelationshipTypeTests(TestCase):
    """
    A proposal-only (CREATE) RelationshipType must be usable as a Data
    type: its Data pages must resolve, and Relationships (with rules)
    can be created under it, all without any canonical RelationshipType/
    RelationshipTypeRule/Relationship row ever existing.
    """

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
        cls.finance = Object.objects.create(
            model=cls.model, object_type=cls.process_type, name="Finance Reporting",
        )
        cls.power_bi = Object.objects.create(
            model=cls.model, object_type=cls.app_type, name="Power BI",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _create_proposed_relationship_type_with_rule(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

        relationship_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipType",
            target_id=relationship_type_id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={
                "name": "Uses", "key": "uses", "description": "",
                "sort_order": 0, "is_active": True,
            },
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipTypeRule",
            target_id=uuid.uuid4(),
            parent_type="RelationshipType",
            parent_id=relationship_type_id,
            before=None,
            after={
                "subject_type_id": str(self.process_type.id),
                "object_type_id": str(self.app_type.id),
                "subject_minimum": 0, "subject_maximum": None, "subject_required": False,
                "object_minimum": 0, "object_maximum": None, "object_required": False,
            },
        )

        return proposal, relationship_type_id

    def test_data_relationship_types_picker_resolves(self):
        self._create_proposed_relationship_type_with_rule()

        response = self.client.get(
            reverse("model:data_relationship_types", args=[self.model.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uses")
        self.assertEqual(RelationshipType.objects.count(), 0)

    def test_data_relationships_index_resolves_for_proposal_only_type(self):
        _proposal, relationship_type_id = self._create_proposed_relationship_type_with_rule()

        response = self.client.get(
            reverse("model:data_relationships", args=[self.model.id, relationship_type_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RelationshipType.objects.count(), 0)

    def test_create_relationship_under_proposal_only_relationship_type_stays_proposal_only(self):
        _proposal, relationship_type_id = self._create_proposed_relationship_type_with_rule()

        response = self.client.post(
            reverse("model:data_relationship_create", args=[self.model.id, relationship_type_id]),
            {"subject_id": str(self.finance.id), "object_id": str(self.power_bi.id)},
        )

        self.assertEqual(response.status_code, 302)

        index_response = self.client.get(
            reverse("model:data_relationships", args=[self.model.id, relationship_type_id]),
        )

        self.assertEqual(len(index_response.context["pending_rows"]), 1)

        self.assertEqual(RelationshipType.objects.count(), 0)
        self.assertEqual(RelationshipTypeRule.objects.count(), 0)
        self.assertEqual(Relationship.objects.count(), 0)

    def test_discard_proposal_only_relationship_type_cascades_to_rule_and_relationship(self):
        proposal, relationship_type_id = self._create_proposed_relationship_type_with_rule()

        self.client.post(
            reverse("model:data_relationship_create", args=[self.model.id, relationship_type_id]),
            {"subject_id": str(self.finance.id), "object_id": str(self.power_bi.id)},
        )

        response = self.client.post(
            reverse("model:relationship_types", args=[self.model.id]),
            {
                "action": "discard_relationship_type_proposal",
                "relationship_type_id": str(relationship_type_id),
            },
        )

        self.assertTrue(response.json()["success"])

        self.assertFalse(proposal.changes.filter(target_type="RelationshipType").exists())
        self.assertFalse(proposal.changes.filter(target_type="RelationshipTypeRule").exists())
        self.assertFalse(proposal.changes.filter(target_type="Relationship").exists())

        not_found_response = self.client.get(
            reverse("model:data_relationships", args=[self.model.id, relationship_type_id]),
        )
        self.assertEqual(not_found_response.status_code, 404)
