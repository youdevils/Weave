import uuid

from django.test import TestCase

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal import submission
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

    def test_get_or_create_working_reuses_failed_proposal(self):
        first = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        first.status = Proposal.Status.FAILED
        first.save(update_fields=["status"])

        second = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        self.assertEqual(first.id, second.id)

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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
            },
        )

        self.assertIsNotNone(change.id)
        self.assertEqual(change.proposal, proposal)
        self.assertEqual(
            change.operation,
            ProposalChange.Operation.UPDATE,
        )
        self.assertEqual(change.target_type, "Model")
        self.assertEqual(change.target_id, self.model.id)
        self.assertEqual(
            change.before,
            {
                "field": "description",
                "value": "Original description",
            },
        )
        self.assertEqual(
            change.after,
            {
                "field": "description",
                "value": "Proposed description",
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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "First proposal",
            },
        )

        second = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Second proposal",
            },
        )

        self.assertEqual(first.id, second.id)

        self.assertEqual(
            ProposalChange.objects.filter(
                proposal=proposal,
                target_type="Model",
                target_id=self.model.id,
            ).count(),
            1,
        )

        second.refresh_from_db()

        self.assertEqual(
            second.after,
            {
                "field": "description",
                "value": "Second proposal",
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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
            },
        )

        result = ProposalService.discard_change(
            proposal=proposal,
            target_type="Model",
            target_id=self.model.id,
            field="description",
        )

        self.assertEqual(result[0], 1)

        self.assertFalse(
            proposal.changes.filter(
                target_type="Model",
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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
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
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
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

    def test_submit_moves_working_proposal_to_queued(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={
                "field": "description",
                "value": "Original description",
            },
            after={
                "field": "description",
                "value": "Proposed description",
            },
        )

        ProposalService.submit(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.QUEUED,
        )

        self.assertIsNotNone(
            proposal.submitted_at,
        )

    def test_submit_requires_at_least_one_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        with self.assertRaises(ValueError):
            ProposalService.submit(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.WORKING,
        )

    # ---------------------------------------------------------
    # Lifecycle protection
    # ---------------------------------------------------------

    def test_queued_proposal_cannot_record_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Proposed description"},
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Model",
                target_id=self.model.id,
                field="description",
                before={"field": "description", "value": "Original description"},
                after={"field": "description", "value": "Another description"},
            )

    def test_queued_proposal_cannot_discard_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Proposed description"},
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.discard_change(
                proposal=proposal,
                target_type="Model",
                target_id=self.model.id,
                field="description",
            )

    def test_queued_proposal_cannot_be_abandoned(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Proposed description"},
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.abandon(proposal)

        proposal.refresh_from_db()

        self.assertEqual(
            proposal.status,
            Proposal.Status.QUEUED,
        )

    def test_processing_proposal_cannot_record_change(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Proposed description"},
        )

        proposal.status = Proposal.Status.PROCESSING
        proposal.save(update_fields=["status"])

        with self.assertRaises(ValueError):
            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Model",
                target_id=self.model.id,
                field="description",
                before={"field": "description", "value": "Original description"},
                after={"field": "description", "value": "Another description"},
            )

    def test_working_proposal_can_be_submitted_only_once(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Proposed description"},
        )

        ProposalService.submit(proposal)

        with self.assertRaises(ValueError):
            ProposalService.submit(proposal)

    # ---------------------------------------------------------
    # Failed proposals stay editable and resubmittable
    # ---------------------------------------------------------

    def test_failed_proposal_can_be_edited_and_resubmitted_on_same_instance(self):
        proposal = ProposalService.get_or_create_working(
            self.model,
            self.user,
        )

        proposal_id = proposal.id

        # A field that doesn't exist on Model -- guaranteed to be
        # caught during apply and fail validation.
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="not_a_real_field",
            before={"field": "not_a_real_field", "value": "x"},
            after={"field": "not_a_real_field", "value": "y"},
        )

        ProposalService.submit(proposal)

        claimed = submission.claim_next(self.model.id)
        self.assertEqual(claimed.id, proposal.id)

        submission.process(proposal.id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(proposal.id, proposal_id)

        first_result = proposal.submission_result
        self.assertEqual(
            first_result.outcome,
            first_result.Outcome.VALIDATION_FAILED,
        )
        self.assertTrue(first_result.errors.exists())

        # Correct the proposal: discard the bad change, add a good one.
        ProposalService.discard_change(
            proposal=proposal,
            target_type="Model",
            target_id=self.model.id,
            field="not_a_real_field",
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            field="description",
            before={"field": "description", "value": "Original description"},
            after={"field": "description", "value": "Corrected description"},
        )

        # Resubmit -- same Proposal row, not a new one.
        ProposalService.submit(proposal)

        proposal.refresh_from_db()
        self.assertEqual(proposal.id, proposal_id)
        self.assertEqual(proposal.status, Proposal.Status.QUEUED)

        self.assertEqual(
            Proposal.objects.filter(model=self.model, created_by=self.user).count(),
            1,
        )

        claimed_again = submission.claim_next(self.model.id)
        self.assertEqual(claimed_again.id, proposal.id)

        submission.process(proposal.id)

        proposal.refresh_from_db()
        self.model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.model.description, "Corrected description")
        self.assertEqual(self.model.revision, 4)

        # The previous failure result was replaced, not accumulated.
        proposal.submission_result.refresh_from_db()
        second_result = proposal.submission_result
        self.assertEqual(second_result.id, first_result.id)
        self.assertEqual(second_result.outcome, second_result.Outcome.SUCCESS)
        self.assertFalse(second_result.errors.exists())


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
