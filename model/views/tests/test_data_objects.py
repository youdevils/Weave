from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.services.proposal.proposal import ProposalService
from model.models.proposal import ProposalChange
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

        response = self.client.get(self._url())

        self.assertContains(response, "Retired")

    def test_pending_create_record_appears_separately_from_table(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        import uuid

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
