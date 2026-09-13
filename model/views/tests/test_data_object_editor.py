from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.review import ProposalReviewService
from workspace.models import Workspace, WorkspaceMember


class DataObjectEditorTestCase(TestCase):

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

        cls.object_type = ObjectType.objects.create(
            model=cls.model,
            name="Application",
            key="application",
            is_active=True,
        )

        cls.owner_attribute = AttributeDefinition.objects.create(
            object_type=cls.object_type,
            name="Owner",
            key="owner",
            data_type=AttributeDefinition.DataType.TEXT,
            is_active=True,
        )

        cls.certified_attribute = AttributeDefinition.objects.create(
            object_type=cls.object_type,
            name="Certified",
            key="certified",
            data_type=AttributeDefinition.DataType.BOOLEAN,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def create_url(self):
        return reverse(
            "model:data_object_create",
            args=[self.model.id, self.object_type.id],
        )

    def edit_url(self, object_id):
        return reverse(
            "model:data_object_edit",
            args=[self.model.id, self.object_type.id, object_id],
        )

    def working_proposal(self):
        return Proposal.objects.get(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )


class CreateObjectTests(DataObjectEditorTestCase):

    def test_create_with_valid_attributes_records_proposal_and_no_canonical_row(self):
        response = self.client.post(
            self.create_url(),
            {
                "name": "SAP S/4HANA",
                "description": "ERP platform",
                "attr_owner": "Finance Tech",
                "attr_certified": "true",
            },
        )

        self.assertEqual(response.status_code, 302)

        proposal = self.working_proposal()
        change = proposal.changes.get(target_type="Object")

        self.assertEqual(change.operation, ProposalChange.Operation.CREATE)
        self.assertEqual(change.after["name"], "SAP S/4HANA")
        self.assertEqual(change.after["attributes"]["owner"], "Finance Tech")
        self.assertIs(change.after["attributes"]["certified"], True)

        # Canonical data must remain untouched by construction alone.
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)

        # It appears in the existing proposal review page.
        review_response = self.client.get(reverse("model:proposal", args=[self.model.id]))
        self.assertContains(review_response, "SAP S/4HANA")

    def test_create_missing_required_name_is_rejected(self):
        response = self.client.post(
            self.create_url(),
            {"name": "", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Name is required.")
        self.assertFalse(ProposalChange.objects.filter(target_type="Object").exists())

    def test_create_invalid_boolean_attribute_is_rejected(self):
        response = self.client.post(
            self.create_url(),
            {
                "name": "SAP S/4HANA",
                "attr_certified": "maybe",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProposalChange.objects.filter(target_type="Object").exists())


class UpdateObjectTests(DataObjectEditorTestCase):

    def setUp(self):
        super().setUp()

        self.obj = Object.objects.create(
            model=self.model,
            object_type=self.object_type,
            name="SAP S/4HANA",
            description="Original",
            attributes={"owner": "Finance Tech", "certified": False},
        )

    def test_field_update_records_change_and_effective_value_shows(self):
        response = self.client.post(
            self.edit_url(self.obj.id),
            {"field": "name", "value": "Customer S/4HANA"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(target_type="Object", target_id=self.obj.id)
        self.assertEqual(change.after, {"field": "name", "value": "Customer S/4HANA"})

        # Canonical row is untouched.
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.name, "SAP S/4HANA")

        # Effective value on the editor page reflects the proposal.
        get_response = self.client.get(self.edit_url(self.obj.id))
        self.assertEqual(get_response.context["proposed_values"]["name"], "Customer S/4HANA")
        self.assertContains(get_response, "Customer S/4HANA")

    def test_repeated_field_save_dedups_to_one_change(self):
        self.client.post(self.edit_url(self.obj.id), {"field": "name", "value": "First"})
        self.client.post(self.edit_url(self.obj.id), {"field": "name", "value": "Second"})

        changes = ProposalChange.objects.filter(
            target_type="Object", target_id=self.obj.id, after__field="name",
        )

        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().after["value"], "Second")

    def test_saving_value_equal_to_canonical_discards_change(self):
        self.client.post(self.edit_url(self.obj.id), {"field": "name", "value": "Renamed"})
        self.assertTrue(
            ProposalChange.objects.filter(target_type="Object", after__field="name").exists()
        )

        self.client.post(self.edit_url(self.obj.id), {"field": "name", "value": "SAP S/4HANA"})

        self.assertFalse(
            ProposalChange.objects.filter(target_type="Object", after__field="name").exists()
        )

    def test_attribute_value_update_uses_dot_namespaced_field(self):
        response = self.client.post(
            self.edit_url(self.obj.id),
            {"field": "attributes.owner", "value": "Enterprise Platforms"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="Object", after__field="attributes.owner",
        )
        self.assertEqual(change.after["value"], "Enterprise Platforms")

        # Canonical attributes dict untouched.
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.attributes["owner"], "Finance Tech")

        get_response = self.client.get(self.edit_url(self.obj.id))
        self.assertEqual(
            get_response.context["proposed_values"]["attributes"]["owner"],
            "Enterprise Platforms",
        )

    def test_invalid_attribute_value_rejected(self):
        response = self.client.post(
            self.edit_url(self.obj.id),
            {"field": "attributes.certified", "value": "not-a-boolean"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            ProposalChange.objects.filter(after__field="attributes.certified").exists()
        )

    def test_lifecycle_toggle_records_change(self):
        response = self.client.post(
            self.edit_url(self.obj.id),
            {"action": "set_object_status", "is_active": "false"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(target_type="Object", after__field="is_active")
        self.assertIs(change.after["value"], False)

        self.obj.refresh_from_db()
        self.assertTrue(self.obj.is_active)

    def test_discard_field_removes_change_and_pending_state(self):
        self.client.post(self.edit_url(self.obj.id), {"field": "name", "value": "Renamed"})

        response = self.client.post(
            self.edit_url(self.obj.id),
            {"field": "name", "action": "discard"},
        )

        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["value"], "SAP S/4HANA")
        self.assertFalse(
            ProposalChange.objects.filter(target_type="Object", after__field="name").exists()
        )

        self.obj.refresh_from_db()
        self.assertEqual(self.obj.name, "SAP S/4HANA")


class ProposalOnlyObjectTests(DataObjectEditorTestCase):

    def _create_proposal_only_object(self):
        self.client.post(
            self.create_url(),
            {"name": "New App", "attr_owner": "Team A"},
        )

        change = ProposalChange.objects.get(target_type="Object", operation=ProposalChange.Operation.CREATE)

        return change.target_id

    def test_editing_proposal_only_object_mutates_create_change_in_place(self):
        object_id = self._create_proposal_only_object()

        response = self.client.post(
            self.edit_url(object_id),
            {"field": "attributes.owner", "value": "Team B"},
        )

        self.assertTrue(response.json()["success"])

        changes = ProposalChange.objects.filter(target_type="Object", target_id=object_id)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().after["attributes"]["owner"], "Team B")

    def test_discard_removes_proposal_only_object_entirely(self):
        object_id = self._create_proposal_only_object()

        proposal = self.working_proposal()

        response = self.client.post(
            reverse("model:data_objects", args=[self.model.id, self.object_type.id]),
            {"action": "discard_object_proposal", "object_id": str(object_id)},
        )

        self.assertTrue(response.json()["success"])
        self.assertFalse(proposal.changes.filter(target_type="Object").exists())
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)


class ReviewPageVisibilityTests(DataObjectEditorTestCase):

    def test_object_update_change_visible_on_review_page_with_target_label(self):
        obj = Object.objects.create(
            model=self.model, object_type=self.object_type, name="SAP S/4HANA",
        )

        self.client.post(self.edit_url(obj.id), {"field": "name", "value": "Renamed App"})

        response = self.client.get(reverse("model:proposal", args=[self.model.id]))

        self.assertContains(response, "Renamed App")

    def test_review_service_resolves_object_target(self):
        obj = Object.objects.create(
            model=self.model, object_type=self.object_type, name="SAP S/4HANA",
        )

        self.client.post(self.edit_url(obj.id), {"field": "name", "value": "Renamed App"})

        proposal = self.working_proposal()
        change = proposal.changes.get(target_type="Object")

        targets = ProposalReviewService.resolve_targets([change])
        create_lookup = ProposalReviewService.build_create_lookup([change])

        target = ProposalReviewService.change_target(change, targets, create_lookup, {})

        self.assertEqual(target["label"], "SAP S/4HANA")
