import uuid

from django.test import TestCase

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace
from account.models import CustomUser


class ProposalServiceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(
            name="Test Workspace",
        )

        cls.user = CustomUser.objects.create_user(
            email="test@example.com",
            password="test-password",
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
            description="Original description",
            revision=3,
        )

    # ---------------------------------------------------------
    # Working proposal
    # ---------------------------------------------------------

    def test_get_or_create_working_creates_proposal(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        self.assertEqual(proposal.model, self.model)
        self.assertEqual(proposal.created_by, self.user)
        self.assertEqual(
            proposal.status,
            Proposal.Status.WORKING,
        )
        self.assertEqual(
            proposal.base_revision,
            self.model.revision,
        )

    def test_get_or_create_working_reuses_existing_proposal(self):
        first = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        second = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        self.assertEqual(first.id, second.id)

        self.assertEqual(
            Proposal.objects.filter(
                model=self.model,
                created_by=self.user,
                status=Proposal.Status.WORKING,
            ).count(),
            1,
        )

    # ---------------------------------------------------------
    # Recording changes
    # ---------------------------------------------------------

    def test_record_change_creates_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        change = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        self.assertIsNotNone(change.id)
        self.assertEqual(change.proposal, proposal)
        self.assertEqual(
            change.operation,
            ProposalChange.Operation.UPDATE,
        )
        self.assertEqual(change.target_type, "model")
        self.assertEqual(change.target_id, self.model.id)
        self.assertEqual(
            change.before,
            {
                "description": "Original description",
            },
        )
        self.assertEqual(
            change.after,
            {
                "description": "Proposed description",
            },
        )

    def test_recording_same_target_updates_existing_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        first = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "First proposal",
            },
        )

        second = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Second proposal",
            },
        )

        self.assertEqual(first.id, second.id)

        self.assertEqual(
            ProposalChange.objects.filter(
                proposal=proposal,
                target_type="model",
                target_id=self.model.id,
            ).count(),
            1,
        )

        second.refresh_from_db()

        self.assertEqual(
            second.after,
            {
                "description": "Second proposal",
            },
        )

    # ---------------------------------------------------------
    # Canonical model protection
    # ---------------------------------------------------------

    def test_recording_change_does_not_modify_canonical_model(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        self.model.refresh_from_db()

        self.assertEqual(
            self.model.description,
            "Original description",
        )

        self.assertEqual(
            self.model.revision,
            3,
        )

    # ---------------------------------------------------------
    # Discarding individual changes
    # ---------------------------------------------------------

    def test_discard_change_removes_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        result = ProposalService.discard_change(
            proposal=proposal,
            target_type="model",
            target_id=self.model.id,
        )

        self.assertEqual(result[0], 1)

        self.assertFalse(
            proposal.changes.filter(
                target_type="model",
                target_id=self.model.id,
            ).exists()
        )

    # ---------------------------------------------------------
    # Abandoning a proposal
    # ---------------------------------------------------------

    def test_abandon_deletes_working_proposal(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        proposal_id = proposal.id

        ProposalService.abandon(proposal)

        self.assertFalse(
            Proposal.objects.filter(
                id=proposal_id,
            ).exists()
        )

    def test_abandon_deletes_proposal_changes(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        self.assertTrue(
            ProposalChange.objects.filter(
                proposal=proposal,
            ).exists()
        )

        proposal_id = proposal.id

        ProposalService.abandon(proposal)

        self.assertFalse(
            Proposal.objects.filter(
                id=proposal_id,
            ).exists()
        )

        self.assertFalse(
            ProposalChange.objects.filter(
                proposal_id=proposal_id,
            ).exists()
        )

    def test_abandon_does_not_modify_canonical_model(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        ProposalService.abandon(proposal)

        self.model.refresh_from_db()

        self.assertEqual(
            self.model.description,
            "Original description",
        )

        self.assertEqual(
            self.model.revision,
            3,
        )

    # ---------------------------------------------------------
    # Submission
    # ---------------------------------------------------------

    def test_submit_moves_working_proposal_to_proposed(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        ProposalService.submit(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.PROPOSED,
        )

        self.assertIsNotNone(
            proposal.submitted_at,
        )

    # ---------------------------------------------------------
    # Lifecycle protection
    # ---------------------------------------------------------

    def test_proposed_proposal_cannot_record_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="model",
                target_id=self.model.id,
                before={
                    "description": "Original description",
                },
                after={
                    "description": "Another description",
                },
            )

    def test_proposed_proposal_cannot_discard_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Proposed description",
            },
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.discard_change(
                proposal=proposal,
                target_type="model",
                target_id=self.model.id,
            )

    def test_proposed_proposal_cannot_be_abandoned(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.abandon(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.PROPOSED,
        )

    def test_working_proposal_can_be_submitted_only_once(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.submit(proposal)

    # ---------------------------------------------------------
    # Working proposal after validation failure
    # ---------------------------------------------------------

    def test_working_proposal_can_be_modified_after_returning_to_working(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "First proposal",
            },
        )

        ProposalService.submit(proposal)

        # Simulate validation failure returning the proposal
        # to working state. ValidationService will own this
        # behaviour once implemented.
        proposal.status = Proposal.Status.WORKING
        proposal.save(update_fields=["status"])

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="model",
            target_id=self.model.id,
            before={
                "description": "Original description",
            },
            after={
                "description": "Corrected proposal",
            },
        )

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.WORKING,
        )

        change = proposal.changes.get(
            target_type="model",
            target_id=self.model.id,
        )

        self.assertEqual(
            change.after,
            {
                "description": "Corrected proposal",
            },
        )

    def test_working_proposal_can_be_resubmitted_after_validation_failure(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.submit(proposal)

        # Simulate validation failure.
        proposal.status = Proposal.Status.WORKING
        proposal.save(update_fields=["status"])

        ProposalService.submit(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.PROPOSED,
        )

        self.assertIsNotNone(
            proposal.submitted_at,
        )


class DiscardChildrenTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="discard-children@example.com",
            password="test-password",
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
            revision=1,
        )

    def setUp(self):
        self.proposal = ProposalService.get_or_create_working(self.model, self.user)

    def _record(self, target_type, target_id, parent_type=None, parent_id=None):
        ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type=target_type,
            target_id=target_id,
            parent_type=parent_type or "",
            parent_id=parent_id,
            before=None,
            after={},
        )

    def test_discard_children_discards_only_matching_child_target_types(self):

        object_type_id = uuid.uuid4()
        attribute_id = uuid.uuid4()
        object_id = uuid.uuid4()

        self._record("ObjectType", object_type_id, "Model", self.model.id)
        self._record("AttributeDefinition", attribute_id, "ObjectType", object_type_id)
        self._record("Object", object_id, "ObjectType", object_type_id)

        discarded = ProposalService.discard_children(
            proposal=self.proposal,
            parent_type="ObjectType",
            parent_id=object_type_id,
            child_target_types={"AttributeDefinition", "Object"},
        )

        self.assertEqual(discarded, {"AttributeDefinition": {attribute_id}, "Object": {object_id}})

        self.assertFalse(self.proposal.changes.filter(target_type="AttributeDefinition").exists())
        self.assertFalse(self.proposal.changes.filter(target_type="Object").exists())

        # The parent itself is untouched by discard_children.
        self.assertTrue(self.proposal.changes.filter(target_type="ObjectType").exists())

    def test_discard_children_leaves_unrelated_children_untouched(self):

        object_type_id = uuid.uuid4()
        other_object_type_id = uuid.uuid4()
        attribute_id = uuid.uuid4()
        unrelated_attribute_id = uuid.uuid4()

        self._record("AttributeDefinition", attribute_id, "ObjectType", object_type_id)
        self._record("AttributeDefinition", unrelated_attribute_id, "ObjectType", other_object_type_id)

        ProposalService.discard_children(
            proposal=self.proposal,
            parent_type="ObjectType",
            parent_id=object_type_id,
            child_target_types={"AttributeDefinition"},
        )

        self.assertFalse(
            self.proposal.changes.filter(target_id=attribute_id).exists()
        )
        self.assertTrue(
            self.proposal.changes.filter(target_id=unrelated_attribute_id).exists()
        )

    def test_discard_children_returns_discarded_ids_by_type(self):

        relationship_type_id = uuid.uuid4()
        rule_id = uuid.uuid4()
        relationship_id = uuid.uuid4()

        self._record("RelationshipTypeRule", rule_id, "RelationshipType", relationship_type_id)
        self._record("Relationship", relationship_id, "RelationshipType", relationship_type_id)

        discarded = ProposalService.discard_children(
            proposal=self.proposal,
            parent_type="RelationshipType",
            parent_id=relationship_type_id,
            child_target_types={"AttributeDefinition", "RelationshipTypeRule", "Relationship"},
        )

        self.assertEqual(
            discarded,
            {"RelationshipTypeRule": {rule_id}, "Relationship": {relationship_id}},
        )
