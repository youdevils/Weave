import uuid

from django.db.models import ProtectedError
from django.test import TestCase

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import (
    ProposalSubmissionResult,
    ProposalValidationError,
)
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.model_deletion import ModelDeletionBlocked, delete_model
from workspace.models import Workspace

# Every table that holds model-owned rows. Counted globally, because
# ProposalChange, EvidenceReference and the submission results have no foreign
# key to the Model and are owned through their Proposal.
OWNED_TABLES = (
    ObjectType,
    RelationshipType,
    RelationshipTypeRule,
    AttributeDefinition,
    Object,
    Relationship,
    Proposal,
    ProposalChange,
    EvidenceReference,
    ProposalSubmissionResult,
    ProposalValidationError,
)


def counts():
    return {table: table.objects.count() for table in OWNED_TABLES}


class ModelDeletionTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(
            email="owner@example.com",
            password="test-password",
        )

    def build_model(self, name="Model", proposal_status=Proposal.Status.COMPLETED):
        """A model with every kind of owned row, including evidence."""

        model = Model.objects.create(workspace=self.workspace, name=name)

        person = ObjectType.objects.create(model=model, name="Person", key="person")
        team = ObjectType.objects.create(model=model, name="Team", key="team")
        member_of = RelationshipType.objects.create(model=model, name="Member of", key="member_of")

        RelationshipTypeRule.objects.create(
            relationship_type=member_of,
            subject_type=person,
            object_type=team,
        )
        AttributeDefinition.objects.create(
            object_type=person,
            name="Owner",
            key="owner",
            data_type=AttributeDefinition.DataType.TEXT,
        )
        AttributeDefinition.objects.create(
            relationship_type=member_of,
            name="Since",
            key="since",
            data_type=AttributeDefinition.DataType.DATE,
        )

        alice = Object.objects.create(model=model, object_type=person, name="Alice")
        ops = Object.objects.create(model=model, object_type=team, name="Ops")
        Relationship.objects.create(
            model=model,
            relationship_type=member_of,
            subject=alice,
            object=ops,
        )

        proposal = Proposal.objects.create(
            model=model,
            created_by=self.user,
            status=proposal_status,
        )
        change = ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=uuid.uuid4(),
            parent_type="Model",
            parent_id=model.id,
            after={"name": "Thing"},
        )
        EvidenceReference.objects.create(change=change, source="Spec v2", locator="p. 4")

        result = ProposalSubmissionResult.objects.create(
            proposal=proposal,
            outcome=ProposalSubmissionResult.Outcome.VALIDATION_FAILED,
        )
        ProposalValidationError.objects.create(
            result=result,
            change=change,
            code="bad",
            message="Bad change.",
        )

        return model


class DeleteModelTests(ModelDeletionTestCase):

    def test_every_owned_table_starts_populated(self):
        # Guards the tests below against passing on an empty fixture.
        self.build_model()

        for table, count in counts().items():
            self.assertGreater(count, 0, table.__name__)

    def test_deletes_the_model_and_everything_it_owns(self):
        model = self.build_model()

        delete_model(model)

        self.assertFalse(Model.objects.filter(id=model.id).exists())
        self.assertEqual(
            counts(),
            {table: 0 for table in OWNED_TABLES},
        )

    def test_leaves_other_models_untouched(self):
        keep = self.build_model("Keep")
        before = counts()
        doomed = self.build_model("Doomed")

        delete_model(doomed)

        self.assertEqual(counts(), before)
        self.assertTrue(Model.objects.filter(id=keep.id).exists())
        self.assertEqual(Object.objects.filter(model=keep).count(), 2)
        self.assertEqual(Proposal.objects.filter(model=keep).count(), 1)

    def test_deletes_types_that_still_have_objects_and_relationships(self):
        # Object.object_type and Relationship.relationship_type are PROTECT:
        # the types cannot be deleted directly while instances exist ...
        model = self.build_model()

        with self.assertRaises(ProtectedError):
            ObjectType.objects.filter(model=model).delete()
        with self.assertRaises(ProtectedError):
            RelationshipType.objects.filter(model=model).delete()

        # ... but deleting the model removes them in a safe order.
        delete_model(model)

        self.assertFalse(ObjectType.objects.exists())
        self.assertFalse(RelationshipType.objects.exists())

    def test_a_model_with_nothing_in_it_is_deleted(self):
        model = Model.objects.create(workspace=self.workspace, name="Empty")

        delete_model(model)

        self.assertFalse(Model.objects.filter(id=model.id).exists())


class DeleteModelBlockedTests(ModelDeletionTestCase):

    def assert_blocked(self, status):
        model = self.build_model(proposal_status=status)
        before = counts()

        with self.assertRaises(ModelDeletionBlocked):
            delete_model(model)

        self.assertTrue(Model.objects.filter(id=model.id).exists())
        self.assertEqual(counts(), before)

    def test_a_queued_proposal_blocks_deletion(self):
        self.assert_blocked(Proposal.Status.QUEUED)

    def test_a_processing_proposal_blocks_deletion(self):
        self.assert_blocked(Proposal.Status.PROCESSING)

    def test_a_queued_proposal_on_a_different_model_does_not_block(self):
        self.build_model("Busy", proposal_status=Proposal.Status.QUEUED)
        model = self.build_model("Idle")

        delete_model(model)

        self.assertFalse(Model.objects.filter(id=model.id).exists())

    def test_proposals_that_are_not_in_flight_do_not_block(self):
        for status in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
            Proposal.Status.COMPLETED,
        ):
            with self.subTest(status=status):
                model = self.build_model(proposal_status=status)

                delete_model(model)

                self.assertFalse(Model.objects.filter(id=model.id).exists())
