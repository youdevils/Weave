import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.services.proposal.proposal import ProposalService
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class DataObjectsIndexViewTests(TestCase):

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

        cls.other_workspace = Workspace.objects.create(name="Other Workspace")

        cls.other_user = CustomUser.objects.create_user(
            email="outsider@example.com",
            password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.other_workspace,
            user=cls.other_user,
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

    def setUp(self):
        self.client.force_login(self.user)

    def _url(self, **kwargs):
        return reverse(
            "model:data_objects",
            args=[self.model.id, self.object_type.id],
        )

    def test_index_requires_login(self):
        self.client.logout()

        response = self.client.get(self._url())

        self.assertNotEqual(response.status_code, 200)

    def test_non_member_gets_404(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 404)

    def test_empty_state_renders(self):
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No application records yet")

    def test_columns_include_active_attribute(self):
        response = self.client.get(self._url())

        self.assertIn(self.owner_attribute, response.context["columns"])

    def test_lists_canonical_objects(self):
        Object.objects.create(
            model=self.model,
            object_type=self.object_type,
            name="SAP S/4HANA",
            attributes={"owner": "Finance Tech"},
        )

        response = self.client.get(self._url())

        self.assertContains(response, "SAP S/4HANA")
        self.assertContains(response, "Finance Tech")

    def test_search_filters_by_name(self):
        Object.objects.create(
            model=self.model, object_type=self.object_type, name="SAP S/4HANA",
        )
        Object.objects.create(
            model=self.model, object_type=self.object_type, name="Salesforce",
        )

        response = self.client.get(self._url(), {"q": "SAP"})

        self.assertContains(response, "SAP S/4HANA")
        self.assertNotContains(response, "Salesforce")

    def test_sort_by_name_desc(self):
        Object.objects.create(
            model=self.model, object_type=self.object_type, name="Alpha",
        )
        Object.objects.create(
            model=self.model, object_type=self.object_type, name="Zeta",
        )

        response = self.client.get(self._url(), {"sort": "name_desc"})

        names = [row.name for row in response.context["rows"]]

        self.assertEqual(names, ["Zeta", "Alpha"])

    def test_pagination_splits_across_pages(self):
        for i in range(30):
            Object.objects.create(
                model=self.model,
                object_type=self.object_type,
                name=f"Record {i:02d}",
            )

        response = self.client.get(self._url())
        self.assertEqual(len(response.context["rows"]), 25)

        response_page_2 = self.client.get(self._url(), {"page": 2})
        self.assertEqual(len(response_page_2.context["rows"]), 5)

    def test_is_active_status_pill_rendered(self):
        Object.objects.create(
            model=self.model,
            object_type=self.object_type,
            name="Retired App",
            is_active=False,
        )

        response = self.client.get(self._url() + "?show=all")

        self.assertContains(response, "Retired")

    def test_pending_create_record_appears_separately_from_table(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

        new_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=new_id,
            parent_type="ObjectType",
            parent_id=self.object_type.id,
            before=None,
            after={
                "name": "New Vendor App",
                "description": "",
                "is_active": True,
                "attributes": {},
            },
        )

        response = self.client.get(self._url())

        self.assertEqual(len(response.context["rows"]), 0)
        self.assertEqual(len(response.context["pending_rows"]), 1)
        self.assertEqual(response.context["pending_rows"][0].name, "New Vendor App")
        self.assertContains(response, "New Vendor App")

        # The canonical database must remain unaffected by a
        # proposal-only CREATE.
        self.assertEqual(
            Object.objects.filter(model=self.model).count(),
            0,
        )


class DataProposalOnlyObjectTypeTests(TestCase):
    """
    A proposal-only (CREATE) ObjectType must be usable as a Data type:
    its Data pages must resolve, and Objects can be created under it,
    all without any canonical ObjectType/Object row ever existing.
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

    def setUp(self):
        self.client.force_login(self.user)

    def _create_proposed_object_type(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

        object_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={
                "name": "Vendor",
                "key": "vendor",
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        return proposal, object_type_id

    def test_data_object_types_picker_resolves(self):
        self._create_proposed_object_type()

        response = self.client.get(
            reverse("model:data_object_types", args=[self.model.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendor")
        self.assertEqual(ObjectType.objects.count(), 0)

    def test_data_objects_index_resolves_for_proposal_only_type(self):
        _proposal, object_type_id = self._create_proposed_object_type()

        response = self.client.get(
            reverse("model:data_objects", args=[self.model.id, object_type_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ObjectType.objects.count(), 0)

    def test_create_object_under_proposal_only_object_type_stays_proposal_only(self):
        _proposal, object_type_id = self._create_proposed_object_type()

        response = self.client.post(
            reverse("model:data_object_create", args=[self.model.id, object_type_id]),
            {"name": "Salesforce", "description": ""},
        )

        self.assertEqual(response.status_code, 302)

        index_response = self.client.get(
            reverse("model:data_objects", args=[self.model.id, object_type_id]),
        )

        self.assertEqual(len(index_response.context["pending_rows"]), 1)
        self.assertEqual(index_response.context["pending_rows"][0].name, "Salesforce")

        self.assertEqual(ObjectType.objects.count(), 0)
        self.assertEqual(Object.objects.count(), 0)

    def test_discard_proposal_only_object_type_cascades_to_object(self):
        proposal, object_type_id = self._create_proposed_object_type()

        self.client.post(
            reverse("model:data_object_create", args=[self.model.id, object_type_id]),
            {"name": "Salesforce", "description": ""},
        )

        response = self.client.post(
            reverse("model:object_types", args=[self.model.id]),
            {
                "action": "discard_object_type_proposal",
                "object_type_id": str(object_type_id),
            },
        )

        self.assertTrue(response.json()["success"])

        self.assertFalse(proposal.changes.filter(target_type="ObjectType").exists())
        self.assertFalse(proposal.changes.filter(target_type="Object").exists())

        # The Data page for the now-fully-discarded type is gone.
        not_found_response = self.client.get(
            reverse("model:data_objects", args=[self.model.id, object_type_id]),
        )
        self.assertEqual(not_found_response.status_code, 404)


class DataObjectRelationshipDiscardCascadeTests(TestCase):
    """
    Discarding a proposal-only Object must not leave a usable
    proposed Relationship referring to an unavailable proposed Object.
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
        cls.uses_type = RelationshipType.objects.create(
            model=cls.model, name="Uses", key="uses", is_active=True,
        )
        cls.finance = Object.objects.create(
            model=cls.model, object_type=cls.process_type, name="Finance Reporting",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_discard_proposal_only_object_cascades_to_relationship(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        activate_proposal(self.client, self.model.id, proposal)

        object_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=object_id,
            parent_type="ObjectType",
            parent_id=self.app_type.id,
            before=None,
            after={"name": "Power BI", "description": "", "is_active": True, "attributes": {}},
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
                "object_id": str(object_id),
                "is_active": True,
                "attributes": {},
            },
        )

        response = self.client.post(
            reverse("model:data_objects", args=[self.model.id, self.app_type.id]),
            {"action": "discard_object_proposal", "object_id": str(object_id)},
        )

        self.assertTrue(response.json()["success"])

        self.assertFalse(proposal.changes.filter(target_type="Object").exists())
        self.assertFalse(proposal.changes.filter(target_type="Relationship").exists())
        self.assertEqual(Relationship.objects.count(), 0)
