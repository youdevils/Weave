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
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from model.views.tests.proposal_test_utils import activate_proposal
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

        review_response = self.client.get(
            reverse("model:proposal", args=[self.model.id, proposal.id])
        )
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


class DataRelationshipEditorProposalCapTests(DataRelationshipEditorTestCase):
    """
    The implicit auto-create-on-edit path must respect the live
    proposal cap just like the explicit "+ New proposal" action.
    """

    def test_create_is_rejected_once_the_live_proposal_cap_is_reached(self):
        for _ in range(5):
            Proposal.objects.create(
                model=self.model,
                created_by=self.user,
                status=Proposal.Status.WORKING,
            )

        response = self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.power_bi.id),
                "attr_criticality": "High",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            Proposal.objects.filter(model=self.model, created_by=self.user).count(),
            5,
        )
        self.assertFalse(Relationship.objects.filter(model=self.model).exists())
        self.assertFalse(
            ProposalChange.objects.filter(target_type="Relationship").exists()
        )


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


class EndpointEditingTests(DataRelationshipEditorTestCase):
    """
    An existing relationship's subject and object are edited in place,
    through the same inline proposal-editor fields as an Object's Name —
    never by retiring and recreating the relationship.
    """

    def setUp(self):
        super().setUp()

        self.tableau = Object.objects.create(
            model=self.model, object_type=self.app_type, name="Tableau",
        )
        self.payroll = Object.objects.create(
            model=self.model, object_type=self.process_type, name="Payroll",
        )

        self.relationship = Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=self.finance,
            object=self.power_bi,
            attributes={"criticality": "Low"},
        )

    def set_endpoint(self, field, value, relationship_id=None):
        return self.client.post(
            self.edit_url(relationship_id or self.relationship.id),
            {"field": field, "value": str(value)},
        )

    @staticmethod
    def payload(response):
        # with_updated_sidebar adds the refreshed sidebar to every JSON reply.
        return {k: v for k, v in response.json().items() if k != "sidebar_html"}

    def endpoint_changes(self):
        return ProposalChange.objects.filter(
            target_type="Relationship",
            target_id=self.relationship.id,
            after__field__in=["subject_id", "object_id"],
        )

    # -- controls ------------------------------------------------------------

    def test_existing_relationship_exposes_endpoint_edit_controls(self):
        response = self.client.get(self.edit_url(self.relationship.id))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        for field in ("subject_id", "object_id"):
            self.assertIn(f'data-field="{field}"', content)
            self.assertIn(f'data-field-editor="{field}"', content)

        # Subject, Object and the Criticality attribute each get the same
        # inline Edit control an Object's fields do; status keeps its toggle.
        self.assertEqual(content.count('data-proposal-action="edit"'), 3)
        self.assertIn("data-relationship-lifecycle", content)

        # The pickers offer only Objects the relationship's rules permit.
        self.assertEqual(
            {c.name for c in response.context["subject_choices"]},
            {"Finance Reporting", "Payroll"},
        )
        self.assertEqual(
            {c.name for c in response.context["object_choices"]},
            {"Power BI", "Tableau"},
        )

    # -- proposal recording --------------------------------------------------

    def test_changing_object_records_field_update_without_touching_canonical(self):
        response = self.set_endpoint("object_id", self.tableau.id)

        self.assertEqual(
            self.payload(response),
            {
                "success": True,
                "value": str(self.tableau.id),
                "display": "Tableau",
                "proposed": True,
            },
        )

        change = self.endpoint_changes().get()
        self.assertEqual(change.operation, ProposalChange.Operation.UPDATE)
        self.assertEqual(change.parent_type, "RelationshipType")
        self.assertEqual(change.parent_id, self.uses_type.id)
        self.assertEqual(change.before, {"field": "object_id", "value": str(self.power_bi.id)})
        self.assertEqual(change.after, {"field": "object_id", "value": str(self.tableau.id)})

        # The same relationship is edited — nothing retired or created.
        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="Relationship",
                operation__in=[ProposalChange.Operation.CREATE, ProposalChange.Operation.DELETE],
            ).exists()
        )
        self.assertFalse(ProposalChange.objects.filter(after__field="is_active").exists())

        self.relationship.refresh_from_db()
        self.assertEqual(self.relationship.object_id, self.power_bi.id)

    def test_editor_and_list_show_the_proposed_endpoint(self):
        self.set_endpoint("subject_id", self.payroll.id)

        response = self.client.get(self.edit_url(self.relationship.id))

        self.assertEqual(response.context["subject_endpoint"].name, "Payroll")
        self.assertEqual(response.context["object_endpoint"].name, "Power BI")
        self.assertTrue(response.context["proposed_fields"]["subject_id"])
        self.assertFalse(response.context["proposed_fields"]["object_id"])

        list_response = self.client.get(
            reverse("model:data_relationships", args=[self.model.id, self.uses_type.id])
        )
        (row,) = list_response.context["rows"]
        self.assertEqual(row.subject_name, "Payroll")
        self.assertEqual(row.subject_id, self.payroll.id)
        self.assertTrue(row.is_proposed)

    def test_repeated_edits_update_one_change(self):
        self.set_endpoint("object_id", self.tableau.id)
        self.set_endpoint("object_id", self.tableau.id)

        self.assertEqual(self.endpoint_changes().count(), 1)

    def test_choosing_the_recorded_endpoint_again_discards_the_change(self):
        self.set_endpoint("object_id", self.tableau.id)

        response = self.set_endpoint("object_id", self.power_bi.id)

        self.assertEqual(response.json()["proposed"], False)
        self.assertEqual(response.json()["display"], "Power BI")
        self.assertFalse(self.endpoint_changes().exists())

    def test_discard_restores_the_recorded_endpoint(self):
        self.set_endpoint("object_id", self.tableau.id)

        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "object_id", "action": "discard"},
        )

        self.assertEqual(
            self.payload(response),
            {
                "success": True,
                "value": str(self.power_bi.id),
                "display": "Power BI",
                "proposed": False,
            },
        )
        self.assertFalse(self.endpoint_changes().exists())

    def test_endpoint_edit_leaves_other_pending_changes_alone(self):
        self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )
        self.set_endpoint("object_id", self.tableau.id)
        self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "object_id", "action": "discard"},
        )

        self.assertTrue(
            ProposalChange.objects.filter(after__field="attributes.criticality").exists()
        )

    # -- validation ----------------------------------------------------------

    def test_object_of_a_type_the_rules_do_not_allow_is_rejected(self):
        response = self.set_endpoint("object_id", self.team.id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Choose an object.")
        self.assertFalse(self.endpoint_changes().exists())

    def test_unknown_object_is_rejected(self):
        response = self.set_endpoint("subject_id", uuid.uuid4())

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Choose a subject.")
        self.assertFalse(self.endpoint_changes().exists())

    def test_retired_object_is_rejected(self):
        self.tableau.is_active = False
        self.tableau.save()

        response = self.set_endpoint("object_id", self.tableau.id)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.endpoint_changes().exists())

    def test_type_pair_must_be_permitted_with_the_other_endpoint(self):
        # A second rule makes Team a valid subject, but only towards a
        # Process — so Team -> Power BI (Application) is not permitted.
        RelationshipTypeRule.objects.create(
            relationship_type=self.uses_type,
            subject_type=self.team_type,
            object_type=self.process_type,
        )

        response = self.set_endpoint("subject_id", self.team.id)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"],
            "This combination of types is not permitted by the relationship's rules.",
        )
        self.assertFalse(self.endpoint_changes().exists())

    def test_pair_check_uses_the_other_endpoints_pending_value(self):
        RelationshipTypeRule.objects.create(
            relationship_type=self.uses_type,
            subject_type=self.team_type,
            object_type=self.process_type,
        )

        # Once the object is (proposed to be) a Process, a Team subject fits.
        self.assertEqual(self.set_endpoint("object_id", self.payroll.id).status_code, 400)

        self.relationship.subject = self.team
        self.relationship.save()
        self.assertTrue(self.set_endpoint("object_id", self.payroll.id).json()["success"])

        response = self.set_endpoint("subject_id", self.finance.id)
        self.assertEqual(response.status_code, 400)

    def test_unknown_field_is_still_rejected(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "relationship_type_id", "value": str(self.uses_type.id)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Unsupported field.")

    # -- proposal-only data --------------------------------------------------

    def test_proposal_only_relationship_endpoint_edit_mutates_create_change(self):
        self.client.post(
            self.create_url(),
            {"subject_id": str(self.finance.id), "object_id": str(self.power_bi.id)},
        )
        create = ProposalChange.objects.get(
            target_type="Relationship", operation=ProposalChange.Operation.CREATE,
        )

        response = self.set_endpoint("object_id", self.tableau.id, create.target_id)

        self.assertTrue(response.json()["success"])
        create.refresh_from_db()
        self.assertEqual(create.after["object_id"], str(self.tableau.id))
        self.assertEqual(
            ProposalChange.objects.filter(target_id=create.target_id).count(), 1,
        )

    def test_endpoint_can_be_a_proposal_only_object(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

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

        response = self.set_endpoint("object_id", new_app_id)

        self.assertEqual(response.json()["display"], "New App")
        self.assertEqual(
            self.client.get(self.edit_url(self.relationship.id)).context["object_endpoint"].name,
            "New App",
        )

        # Discarding that proposed Object drops the re-point with it.
        self.client.post(
            reverse("model:data_objects", args=[self.model.id, self.app_type.id]),
            {"action": "discard_object_proposal", "object_id": str(new_app_id)},
        )

        self.assertFalse(self.endpoint_changes().exists())
        self.assertTrue(
            Relationship.objects.filter(id=self.relationship.id, object=self.power_bi).exists()
        )

    # -- review --------------------------------------------------------------

    def test_proposal_review_names_the_endpoints(self):
        self.set_endpoint("object_id", self.tableau.id)
        proposal = self.working_proposal()

        response = self.client.get(
            reverse("model:proposal", args=[self.model.id, proposal.id])
        )

        change = next(
            c
            for group in response.context["change_groups"]
            for c in group["changes"]
            if c.target_type == "Relationship"
        )
        self.assertEqual(change.review_label, "Object")
        self.assertEqual((change.review_before, change.review_after), ("Power BI", "Tableau"))
        self.assertNotContains(response, str(self.tableau.id))

    # -- submission ----------------------------------------------------------

    def _submit_and_process(self):
        proposal = self.working_proposal()
        ProposalService.submit(proposal)
        submission.process(submission.claim_next(self.model.id).id)
        proposal.refresh_from_db()
        self.relationship.refresh_from_db()
        return proposal

    def test_submitted_endpoint_edit_updates_the_same_relationship(self):
        self.set_endpoint("subject_id", self.payroll.id)
        self.set_endpoint("object_id", self.tableau.id)
        self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )

        proposal = self._submit_and_process()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.relationship.subject_id, self.payroll.id)
        self.assertEqual(self.relationship.object_id, self.tableau.id)
        self.assertEqual(self.relationship.attributes, {"criticality": "High"})
        self.assertTrue(self.relationship.is_active)
        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 1)

        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, 2)

    def test_cardinality_still_applies_on_submission(self):
        rule = self.uses_type.rules.get()
        rule.subject_maximum = 1
        rule.save()

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=self.payroll,
            object=self.tableau,
        )

        # Tableau may have at most one subject; re-pointing gives it a second.
        self.set_endpoint("object_id", self.tableau.id)

        proposal = self._submit_and_process()

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        codes = {e.code for e in proposal.submission_result.errors.all()}
        self.assertIn("subject_cardinality_maximum", codes)
        self.assertEqual(self.relationship.object_id, self.power_bi.id)


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
        activate_proposal(self.client, self.model.id, proposal)

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
        activate_proposal(self.client, self.model.id, proposal)

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
        activate_proposal(self.client, self.model.id, proposal)

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
        activate_proposal(self.client, self.model.id, proposal)

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
