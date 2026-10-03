import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from workspace.models import Workspace, WorkspaceMember


class ObjectTypesBulkStatusTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.owner_user = CustomUser.objects.create_user(
            email="owner@example.com", password="test-password",
        )
        cls.viewer_user = CustomUser.objects.create_user(
            email="viewer@example.com", password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.owner_user, role=WorkspaceMember.Role.OWNER,
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.viewer_user, role=WorkspaceMember.Role.VIEWER,
        )

        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

        cls.type_a = ObjectType.objects.create(
            model=cls.model, name="Application", key="application", is_active=True,
        )
        cls.type_b = ObjectType.objects.create(
            model=cls.model, name="Server", key="server", is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.owner_user)

    def url(self):
        return reverse("model:object_types", args=[self.model.id])

    def bulk_status(self, type_ids, is_active, user=None):
        if user is not None:
            self.client.force_login(user)

        return self.client.post(
            self.url(),
            {
                "action": "bulk_set_object_type_status",
                "is_active": "true" if is_active else "false",
                "object_type_id": [str(i) for i in type_ids],
            },
        )

    def single_status(self, object_type, is_active):
        return self.client.post(
            reverse("model:object_type_edit", args=[self.model.id, object_type.id]),
            {"action": "set_object_type_status", "is_active": "true" if is_active else "false"},
        )


class PermissionTests(ObjectTypesBulkStatusTestCase):

    def test_viewer_cannot_bulk_toggle(self):
        response = self.bulk_status([self.type_a.id], False, user=self.viewer_user)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProposalChange.objects.exists())


class AtomicityTests(ObjectTypesBulkStatusTestCase):

    def test_an_unresolvable_id_rejects_the_whole_batch(self):
        response = self.bulk_status([self.type_a.id, uuid.uuid4()], False)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProposalChange.objects.exists())

    def test_a_valid_batch_applies_to_every_type(self):
        response = self.bulk_status([self.type_a.id, self.type_b.id], False)
        self.assertTrue(response.json()["success"])

        changes = ProposalChange.objects.filter(target_type="ObjectType", after__field="is_active")
        self.assertEqual(changes.count(), 2)
        for change in changes:
            self.assertEqual(change.after["value"], False)


class ParityTests(ObjectTypesBulkStatusTestCase):

    def test_bulk_toggle_produces_the_same_change_shape_as_the_single_item_toggle(self):
        self.single_status(self.type_a, False)
        single_change = ProposalChange.objects.get(target_type="ObjectType", target_id=self.type_a.id)

        self.bulk_status([self.type_b.id], False)
        bulk_change = ProposalChange.objects.get(target_type="ObjectType", target_id=self.type_b.id)

        self.assertEqual(single_change.operation, bulk_change.operation)
        self.assertEqual(single_change.after["field"], bulk_change.after["field"])
        self.assertEqual(single_change.after["value"], bulk_change.after["value"])
        self.assertEqual(single_change.before, bulk_change.before)
        self.assertEqual(single_change.parent_type, bulk_change.parent_type)
