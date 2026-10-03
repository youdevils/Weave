import json
import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.bulk_edit import (
    MAX_BULK_SELECTION,
    collect_effective_state,
)
from model.services.proposal.proposal import ProposalService
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class BulkEditTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.owner_user = CustomUser.objects.create_user(
            email="owner@example.com", password="test-password",
        )
        cls.editor_user = CustomUser.objects.create_user(
            email="editor@example.com", password="test-password",
        )
        cls.viewer_user = CustomUser.objects.create_user(
            email="viewer@example.com", password="test-password",
        )
        cls.outsider_user = CustomUser.objects.create_user(
            email="outsider@example.com", password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.owner_user, role=WorkspaceMember.Role.OWNER,
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.editor_user, role=WorkspaceMember.Role.EDITOR,
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.viewer_user, role=WorkspaceMember.Role.VIEWER,
        )

        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

        cls.object_type = ObjectType.objects.create(
            model=cls.model, name="Application", key="application", is_active=True,
        )

        cls.owner_attribute = AttributeDefinition.objects.create(
            object_type=cls.object_type, name="Owner", key="owner",
            data_type=AttributeDefinition.DataType.TEXT, nullable=True, is_active=True,
        )
        cls.certified_attribute = AttributeDefinition.objects.create(
            object_type=cls.object_type, name="Certified", key="certified",
            data_type=AttributeDefinition.DataType.BOOLEAN, nullable=False, is_active=True,
        )
        cls.status_attribute = AttributeDefinition.objects.create(
            object_type=cls.object_type, name="Status", key="status",
            data_type=AttributeDefinition.DataType.CHOICE, nullable=False, is_active=True,
            config={"choices": ["Active", "Inactive", "Pending"]},
        )

        other_workspace = Workspace.objects.create(name="Other Workspace")
        cls.other_model = Model.objects.create(
            workspace=other_workspace, name="Other Model", revision=1,
        )
        cls.other_object_type = ObjectType.objects.create(
            model=cls.other_model, name="Other", key="other", is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.owner_user)

    def bulk_url(self):
        return reverse(
            "model:data_object_bulk_edit", args=[self.model.id, self.object_type.id],
        )

    def make_object(self, name, owner="Original Owner", certified=False, status="Active"):
        return Object.objects.create(
            model=self.model, object_type=self.object_type, name=name,
            attributes={"owner": owner, "certified": certified, "status": status},
        )

    def post_bulk(self, object_ids, action="", extra=None, user=None):
        if user is not None:
            self.client.force_login(user)

        data = {"object_id": [str(i) for i in object_ids]}
        if action:
            data["action"] = action
        if extra:
            for key, value in extra.items():
                data[key] = value

        return self.client.post(self.bulk_url(), data)

    def preview(self, object_ids, extra=None, user=None):
        return self.post_bulk(object_ids, action="preview", extra=extra, user=user)

    def apply(self, object_ids, fingerprint, extra=None, user=None):
        extra = dict(extra or {})
        extra["preview_fingerprint"] = fingerprint
        return self.post_bulk(object_ids, action="apply", extra=extra, user=user)

    def preview_then_apply(self, object_ids, extra=None, user=None):
        preview_response = self.preview(object_ids, extra=extra, user=user)
        fingerprint = preview_response.context["preview_fingerprint"]
        return self.apply(object_ids, fingerprint, extra=extra, user=user)

    def working_proposal(self, user=None):
        return Proposal.objects.get(
            model=self.model, created_by=(user or self.owner_user),
            source=Proposal.Source.USER, status=Proposal.Status.WORKING,
        )


class PermissionTests(BulkEditTestCase):

    def test_viewer_cannot_bulk_edit(self):
        obj = self.make_object("App 1")

        response = self.post_bulk([obj.id], user=self.viewer_user)
        self.assertEqual(response.status_code, 403)

    def test_non_member_gets_404(self):
        obj = self.make_object("App 1")

        response = self.post_bulk([obj.id], user=self.outsider_user)
        self.assertEqual(response.status_code, 404)

    def test_owner_can_bulk_edit(self):
        obj = self.make_object("App 1")

        response = self.post_bulk([obj.id], user=self.owner_user)
        self.assertEqual(response.status_code, 200)

    def test_editor_can_bulk_edit(self):
        obj = self.make_object("App 1")

        response = self.post_bulk([obj.id], user=self.editor_user)
        self.assertEqual(response.status_code, 200)


class InputBoundingTests(BulkEditTestCase):

    def test_empty_selection_is_rejected(self):
        response = self.client.post(self.bulk_url(), {})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProposalChange.objects.exists())

    def test_selection_over_the_maximum_is_rejected(self):
        ids = [str(uuid.uuid4()) for _ in range(MAX_BULK_SELECTION + 1)]
        response = self.client.post(self.bulk_url(), {"object_id": ids})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProposalChange.objects.exists())

    def test_duplicate_ids_are_deduplicated_without_error(self):
        obj = self.make_object("App 1")

        response = self.post_bulk([obj.id, obj.id, obj.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["objects"]), 1)


class NoChangeTests(BulkEditTestCase):

    def test_preview_with_everything_nochange_writes_nothing(self):
        obj = self.make_object("App 1")

        response = self.preview([obj.id])
        self.assertTrue(response.context["result"].ok)
        self.assertFalse(ProposalChange.objects.exists())

    def test_apply_with_everything_nochange_writes_nothing(self):
        obj = self.make_object("App 1")

        response = self.preview_then_apply([obj.id])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProposalChange.objects.exists())


class SetFieldTests(BulkEditTestCase):

    def test_set_attribute_across_objects_creates_one_update_change_each(self):
        objects = [
            self.make_object("App 1", owner="A"),
            self.make_object("App 2", owner="B"),
            self.make_object("App 3", owner="C"),
        ]
        ids = [obj.id for obj in objects]

        response = self.preview_then_apply(
            ids, extra={"mode__attributes.owner": "set", "value__attributes.owner": "Shared Owner"},
        )
        self.assertEqual(response.status_code, 302)

        changes = ProposalChange.objects.filter(
            target_type="Object", after__field="attributes.owner",
        )
        self.assertEqual(changes.count(), 3)
        for change in changes:
            self.assertEqual(change.after["value"], "Shared Owner")
            self.assertEqual(change.operation, ProposalChange.Operation.UPDATE)

    def test_setting_back_to_canonical_value_discards_the_pending_change(self):
        obj = self.make_object("App 1", owner="A")

        self.preview_then_apply(
            [obj.id], extra={"mode__attributes.owner": "set", "value__attributes.owner": "B"},
        )
        self.assertTrue(
            ProposalChange.objects.filter(target_type="Object", after__field="attributes.owner").exists()
        )

        self.preview_then_apply(
            [obj.id], extra={"mode__attributes.owner": "set", "value__attributes.owner": "A"},
        )
        self.assertFalse(
            ProposalChange.objects.filter(target_type="Object", after__field="attributes.owner").exists()
        )


class BaselinePreservationTests(BulkEditTestCase):
    """
    Regression for review point 3: a second edit to a field that already
    has a pending change must never replace that change's `before`
    baseline with the first edit's proposed value.
    """

    def test_bulk_editing_an_already_pending_field_preserves_the_original_baseline(self):
        obj = self.make_object("App 1", owner="Original")

        proposal = ProposalService.get_or_create_working(self.model, self.owner_user)
        activate_proposal(self.client, self.model.id, proposal)

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=obj.id,
            parent_type="ObjectType",
            parent_id=self.object_type.id,
            field="attributes.owner",
            before={"field": "attributes.owner", "value": "Original"},
            after={"field": "attributes.owner", "value": "First"},
        )

        self.preview_then_apply(
            [obj.id], extra={"mode__attributes.owner": "set", "value__attributes.owner": "Second"},
        )

        change = ProposalChange.objects.get(target_type="Object", after__field="attributes.owner")
        self.assertEqual(change.before, {"field": "attributes.owner", "value": "Original"})
        self.assertEqual(change.after, {"field": "attributes.owner", "value": "Second"})


class ClearTests(BulkEditTestCase):

    def test_clearing_a_nullable_attribute_sets_it_to_none(self):
        obj = self.make_object("App 1", owner="Something")

        self.preview_then_apply([obj.id], extra={"mode__attributes.owner": "clear"})

        change = ProposalChange.objects.get(target_type="Object", after__field="attributes.owner")
        self.assertIsNone(change.after["value"])

    def test_clearing_a_non_nullable_attribute_is_rejected_and_writes_nothing(self):
        obj = self.make_object("App 1", certified=True)

        response = self.preview([obj.id], extra={"mode__attributes.certified": "clear"})
        self.assertFalse(response.context["result"].ok)
        self.assertFalse(ProposalChange.objects.exists())


class MixedValuesTests(BulkEditTestCase):

    def test_collect_effective_state_reports_mixed_values(self):
        same_a = self.make_object("App 1", owner="X")
        same_b = self.make_object("App 2", owner="Y")

        objects = [(same_a, False), (same_b, False)]
        effective = collect_effective_state(objects, [self.owner_attribute], None)

        self.assertTrue(effective["attributes.owner"]["is_mixed"])

    def test_collect_effective_state_reports_uniform_values(self):
        same_a = self.make_object("App 1", owner="X")
        same_b = self.make_object("App 2", owner="X")

        objects = [(same_a, False), (same_b, False)]
        effective = collect_effective_state(objects, [self.owner_attribute], None)

        self.assertFalse(effective["attributes.owner"]["is_mixed"])
        self.assertEqual(effective["attributes.owner"]["value"], "X")


class AtomicityTests(BulkEditTestCase):

    def test_an_invalid_field_leaves_every_selected_object_unchanged(self):
        objects = [self.make_object("App 1"), self.make_object("App 2")]
        ids = [obj.id for obj in objects]

        response = self.preview(
            ids, extra={"mode__attributes.status": "set", "value__attributes.status": "Not A Choice"},
        )
        self.assertFalse(response.context["result"].ok)
        self.assertFalse(ProposalChange.objects.exists())

    def test_a_foreign_object_id_rejects_the_whole_batch(self):
        own = self.make_object("App 1")
        foreign = Object.objects.create(
            model=self.other_model, object_type=self.other_object_type, name="Foreign",
        )

        response = self.post_bulk(
            [own.id, foreign.id],
            extra={"mode__attributes.owner": "set", "value__attributes.owner": "Shared"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProposalChange.objects.exists())

    def test_a_nonexistent_object_id_rejects_the_whole_batch(self):
        own = self.make_object("App 1")

        response = self.post_bulk([own.id, uuid.uuid4()])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProposalChange.objects.exists())


class ProposalOnlyObjectTests(BulkEditTestCase):

    def test_bulk_edit_merges_into_the_create_change_rather_than_a_separate_update(self):
        canonical = self.make_object("App 1", owner="Canonical Owner")

        create_response = self.client.post(
            reverse("model:data_object_create", args=[self.model.id, self.object_type.id]),
            {"name": "Proposed App", "attr_owner": "Proposed Owner"},
        )
        self.assertEqual(create_response.status_code, 302)

        create_change = ProposalChange.objects.get(
            target_type="Object", operation=ProposalChange.Operation.CREATE,
        )
        proposed_id = create_change.target_id

        self.preview_then_apply(
            [canonical.id, proposed_id],
            extra={"mode__attributes.owner": "set", "value__attributes.owner": "Bulk Owner"},
        )

        create_change.refresh_from_db()
        self.assertEqual(create_change.after["attributes"]["owner"], "Bulk Owner")

        update_changes = ProposalChange.objects.filter(
            target_type="Object", target_id=proposed_id, operation=ProposalChange.Operation.UPDATE,
        )
        self.assertFalse(update_changes.exists())

        canonical_change = ProposalChange.objects.get(target_type="Object", target_id=canonical.id)
        self.assertEqual(canonical_change.after["value"], "Bulk Owner")


class LifecycleTests(BulkEditTestCase):

    def test_bulk_retire_across_objects(self):
        objects = [self.make_object("App 1"), self.make_object("App 2")]
        ids = [obj.id for obj in objects]

        self.preview_then_apply(ids, extra={"mode__is_active": "retire"})

        changes = ProposalChange.objects.filter(target_type="Object", after__field="is_active")
        self.assertEqual(changes.count(), 2)
        for change in changes:
            self.assertEqual(change.after["value"], False)


class PreviewApplyTests(BulkEditTestCase):

    def test_apply_without_a_preceding_preview_is_rejected(self):
        obj = self.make_object("App 1")

        response = self.apply(
            [obj.id], fingerprint="not-a-real-fingerprint",
            extra={"mode__attributes.owner": "set", "value__attributes.owner": "X"},
        )
        self.assertFalse(response.context["previewed"])
        self.assertFalse(ProposalChange.objects.exists())

    def test_apply_after_the_proposal_changed_underneath_the_preview_is_rejected(self):
        obj = self.make_object("App 1", owner="A")

        preview_response = self.preview(
            [obj.id], extra={"mode__attributes.owner": "set", "value__attributes.owner": "B"},
        )
        fingerprint = preview_response.context["preview_fingerprint"]

        # Simulate a second tab changing the same working proposal.
        proposal = ProposalService.get_or_create_working(self.model, self.owner_user)
        activate_proposal(self.client, self.model.id, proposal)
        other_obj = self.make_object("App 2", owner="Z")
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=other_obj.id,
            parent_type="ObjectType",
            parent_id=self.object_type.id,
            field="attributes.owner",
            before={"field": "attributes.owner", "value": "Z"},
            after={"field": "attributes.owner", "value": "Unrelated change"},
        )

        response = self.apply(
            [obj.id], fingerprint=fingerprint,
            extra={"mode__attributes.owner": "set", "value__attributes.owner": "B"},
        )
        self.assertTrue(response.context["stale_preview"])
        self.assertFalse(
            ProposalChange.objects.filter(target_id=obj.id, after__field="attributes.owner").exists()
        )

    def test_a_valid_matching_preview_applies_successfully(self):
        obj = self.make_object("App 1", owner="A")

        response = self.preview_then_apply(
            [obj.id], extra={"mode__attributes.owner": "set", "value__attributes.owner": "B"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("bulk_edited=1", response.url)


class EquivalenceTests(BulkEditTestCase):
    """
    Review point 10: bulk edit must produce the same ProposalChange state
    as the equivalent sequence of individual single-field edits.
    """

    def test_bulk_edit_matches_sequential_individual_edits(self):
        bulk_objects = [
            self.make_object("Bulk 1", owner="A", status="Active"),
            self.make_object("Bulk 2", owner="B", status="Pending"),
        ]
        individual_objects = [
            self.make_object("Individual 1", owner="A", status="Active"),
            self.make_object("Individual 2", owner="B", status="Pending"),
        ]

        self.preview_then_apply(
            [obj.id for obj in bulk_objects],
            extra={"mode__attributes.status": "set", "value__attributes.status": "Inactive"},
        )

        edit_url_name = "model:data_object_edit"
        for obj in individual_objects:
            self.client.post(
                reverse(edit_url_name, args=[self.model.id, self.object_type.id, obj.id]),
                {"field": "attributes.status", "value": "Inactive"},
            )

        def normalize(objects):
            rows = [
                (
                    change.operation,
                    change.after.get("field"),
                    change.before,
                    change.after,
                )
                for obj in objects
                for change in ProposalChange.objects.filter(target_type="Object", target_id=obj.id)
            ]
            return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))

        self.assertEqual(normalize(bulk_objects), normalize(individual_objects))
