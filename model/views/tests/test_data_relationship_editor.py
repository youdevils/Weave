import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace, WorkspaceMember


class DataRelationshipEditorTestCase(TestCase):

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
        cls.team_type = ObjectType.objects.create(
            model=cls.model, name="Team", key="team", is_active=True,
        )

        cls.uses_type = RelationshipType.objects.create(
            model=cls.model, name="Uses", key="uses", is_active=True,
        )

        RelationshipTypeRule.objects.create(
            relationship_type=cls.uses_type,
            subject_type=cls.process_type,
            object_type=cls.app_type,
        )

        cls.criticality_attribute = AttributeDefinition.objects.create(
            relationship_type=cls.uses_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

        cls.finance = Object.objects.create(
            model=cls.model, object_type=cls.process_type, name="Finance Reporting",
        )
        cls.power_bi = Object.objects.create(
            model=cls.model, object_type=cls.app_type, name="Power BI",
        )
        cls.team = Object.objects.create(
            model=cls.model, object_type=cls.team_type, name="Finance Team",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def create_url(self):
        return reverse(
            "model:data_relationship_create",
            args=[self.model.id, self.uses_type.id],
        )

    def edit_url(self, relationship_id):
        return reverse(
            "model:data_relationship_edit",
            args=[self.model.id, self.uses_type.id, relationship_id],
        )

    def working_proposal(self):
        return Proposal.objects.get(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )


class CreateRelationshipTests(DataRelationshipEditorTestCase):

    def test_create_with_allowed_endpoints_records_proposal(self):
        response = self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.power_bi.id),
                "attr_criticality": "High",
            },
        )

        self.assertEqual(response.status_code, 302)

        proposal = self.working_proposal()
        change = proposal.changes.get(target_type="Relationship")

        self.assertEqual(change.operation, ProposalChange.Operation.CREATE)
        self.assertEqual(change.after["subject_id"], str(self.finance.id))
        self.assertEqual(change.after["object_id"], str(self.power_bi.id))
        self.assertEqual(change.after["attributes"]["criticality"], "High")

        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 0)

        review_response = self.client.get(reverse("model:proposal", args=[self.model.id]))
        self.assertContains(review_response, "Finance Reporting")

    def test_create_rejects_endpoint_pair_not_permitted_by_rule(self):
        # Team is not an allowed object type for the Uses relationship's
        # single rule (Process -> Application).
        response = self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.team.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProposalChange.objects.filter(target_type="Relationship").exists())

    def test_create_requires_both_endpoints(self):
        response = self.client.post(self.create_url(), {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a subject.")
        self.assertContains(response, "Choose an object.")
        self.assertFalse(ProposalChange.objects.filter(target_type="Relationship").exists())


class UpdateRelationshipTests(DataRelationshipEditorTestCase):

    def setUp(self):
        super().setUp()

        self.relationship = Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=self.finance,
            object=self.power_bi,
            attributes={"criticality": "Low"},
        )

    def test_attribute_value_update_records_dot_namespaced_change(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="Relationship", after__field="attributes.criticality",
        )
        self.assertEqual(change.after["value"], "High")

        self.relationship.refresh_from_db()
        self.assertEqual(self.relationship.attributes["criticality"], "Low")

        get_response = self.client.get(self.edit_url(self.relationship.id))
        self.assertEqual(
            get_response.context["proposed_values"]["attributes"]["criticality"],
            "High",
        )

    def test_invalid_choice_value_rejected(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "Medium"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            ProposalChange.objects.filter(after__field="attributes.criticality").exists()
        )

    def test_lifecycle_toggle_records_change_and_canonical_unchanged(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"action": "set_relationship_status", "is_active": "false"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="Relationship", after__field="is_active",
        )
        self.assertIs(change.after["value"], False)

        self.relationship.refresh_from_db()
        self.assertTrue(self.relationship.is_active)

    def test_discard_removes_change(self):
        self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )

        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "action": "discard"},
        )

        self.assertTrue(response.json()["success"])
        self.assertFalse(
            ProposalChange.objects.filter(after__field="attributes.criticality").exists()
        )


class ProposalOnlyRelationshipTests(DataRelationshipEditorTestCase):

    def _create_proposal_only_relationship(self):
        self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.power_bi.id),
            },
        )

        change = ProposalChange.objects.get(
            target_type="Relationship", operation=ProposalChange.Operation.CREATE,
        )

        return change.target_id

    def test_editing_proposal_only_relationship_mutates_create_change(self):
        relationship_id = self._create_proposal_only_relationship()

        response = self.client.post(
            self.edit_url(relationship_id),
            {"field": "attributes.criticality", "value": "High"},
        )

        self.assertTrue(response.json()["success"])

        changes = ProposalChange.objects.filter(
            target_type="Relationship", target_id=relationship_id,
        )
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().after["attributes"]["criticality"], "High")

    def test_discard_removes_proposal_only_relationship_entirely(self):
        relationship_id = self._create_proposal_only_relationship()

        proposal = self.working_proposal()

        response = self.client.post(
            reverse("model:data_relationships", args=[self.model.id, self.uses_type.id]),
            {"action": "discard_relationship_proposal", "relationship_id": str(relationship_id)},
        )

        self.assertTrue(response.json()["success"])
        self.assertFalse(proposal.changes.filter(target_type="Relationship").exists())
        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 0)


class ProposalOnlyEndpointTests(DataRelationshipEditorTestCase):
    """
    Proposal-only Objects must be usable as Relationship endpoints,
    both as picker choices and when displaying an existing relationship
    whose endpoint is itself only a proposal-only Object.
    """

    def test_create_form_allowed_endpoints_include_proposal_only_object(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        new_app_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=new_app_id,
            parent_type="ObjectType",
            parent_id=self.app_type.id,
            before=None,
            after={"name": "New App", "description": "", "is_active": True, "attributes": {}},
        )

        get_response = self.client.get(self.create_url())

        object_choice_ids = {str(c.id) for c in get_response.context["object_choices"]}
        self.assertIn(str(new_app_id), object_choice_ids)

        post_response = self.client.post(
            self.create_url(),
            {"subject_id": str(self.finance.id), "object_id": str(new_app_id)},
        )

        self.assertEqual(post_response.status_code, 302)

        change = proposal.changes.get(
            target_type="Relationship", operation=ProposalChange.Operation.CREATE,
        )
        self.assertEqual(change.after["object_id"], str(new_app_id))

    def test_relationship_endpoint_that_is_itself_proposal_only_object_renders(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        new_app_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=new_app_id,
            parent_type="ObjectType",
            parent_id=self.app_type.id,
            before=None,
            after={"name": "New App", "description": "", "is_active": True, "attributes": {}},
        )

        relationship_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Relationship",
            target_id=relationship_id,
            parent_type="RelationshipType",
            parent_id=self.uses_type.id,
            before=None,
            after={
                "subject_id": str(self.finance.id),
                "object_id": str(new_app_id),
                "is_active": True,
                "attributes": {},
            },
        )

        response = self.client.get(self.edit_url(relationship_id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["relationship"].subject.name, "Finance Reporting")
        self.assertEqual(response.context["relationship"].object.name, "New App")
        self.assertContains(response, "New App")


class ProposalOnlyRelationshipTypeEditorTests(TestCase):
    """
    The Relationship record editor must resolve for a proposal-only
    (CREATE) RelationshipType.
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

    def setUp(self):
        self.client.force_login(self.user)

    def test_editor_opens_for_proposal_only_relationship_type(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

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

        response = self.client.get(
            reverse("model:data_relationship_create", args=[self.model.id, relationship_type_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RelationshipType.objects.count(), 0)


class ChoiceAttributeInDataEditorTests(DataRelationshipEditorTestCase):
    """
    A CHOICE AttributeDefinition's allowed values, configured in the
    ontology editor, must be presented by the Relationship Data
    editor — for both a proposal-only attribute and a canonical
    attribute with a pending config UPDATE.
    """

    def test_proposal_only_choice_attribute_options_render_in_data_create_form(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        attribute_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id=attribute_id,
            parent_type="RelationshipType",
            parent_id=self.uses_type.id,
            before=None,
            after={
                "name": "Sensitivity", "key": "sensitivity", "data_type": "choice",
                "description": "", "required": False, "nullable": True,
                "default_value": None, "sort_order": 0,
                "config": {"choices": ["Public", "Confidential"]},
                "is_active": True,
            },
        )

        response = self.client.get(self.create_url())

        self.assertEqual(response.status_code, 200)

        sensitivity_attribute = next(
            a for a in response.context["attribute_definitions"] if a.key == "sensitivity"
        )
        self.assertEqual(sensitivity_attribute.choices, ["Public", "Confidential"])
        self.assertContains(response, "Confidential")

    def test_canonical_attribute_with_pending_config_update_renders_in_data_editor(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="AttributeDefinition",
            target_id=self.criticality_attribute.id,
            parent_type="RelationshipType",
            parent_id=self.uses_type.id,
            field="config",
            before={"field": "config", "value": {"choices": ["Low", "High"]}},
            after={"field": "config", "value": {"choices": ["Low", "Medium", "High"]}},
        )

        relationship = Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=self.finance,
            object=self.power_bi,
        )

        response = self.client.get(self.edit_url(relationship.id))

        self.assertEqual(response.status_code, 200)

        criticality_attribute = next(
            a for a in response.context["attribute_definitions"] if a.key == "criticality"
        )
        self.assertEqual(criticality_attribute.choices, ["Low", "Medium", "High"])
        self.assertContains(response, "Medium")

        self.criticality_attribute.refresh_from_db()
        self.assertEqual(self.criticality_attribute.config, {"choices": ["Low", "High"]})
