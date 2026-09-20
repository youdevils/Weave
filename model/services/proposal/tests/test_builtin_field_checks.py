"""
The apply step reports bad built-in values and missing endpoints as issues
before writing, instead of letting the database raise mid-proposal.
"""

import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


class BuiltinFieldCheckTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="W")
        cls.user = CustomUser.objects.create_user(email="u@example.com", password="pw")
        cls.model = Model.objects.create(workspace=cls.workspace, name="M")
        cls.object_type = ObjectType.objects.create(model=cls.model, name="Thing", key="thing")
        cls.relationship_type = RelationshipType.objects.create(model=cls.model, name="Rel", key="rel")
        RelationshipTypeRule.objects.create(
            relationship_type=cls.relationship_type, subject_type=cls.object_type, object_type=cls.object_type
        )
        cls.one = Object.objects.create(model=cls.model, object_type=cls.object_type, name="One")
        cls.two = Object.objects.create(model=cls.model, object_type=cls.object_type, name="Two")

    def submit(self, *changes):
        proposal = ProposalService.create_working(self.model, self.user)

        for change in changes:
            ProposalService.record_change(proposal=proposal, **change)

        ProposalService.submit(proposal)

        while (claimed := submission.claim_next(self.model.id)) is not None:
            submission.process(claimed.id)

        proposal.refresh_from_db()
        return proposal

    def object_create(self, **after):
        payload = {"name": "New", "description": "", "is_active": True, "attributes": {}}
        payload.update(after)
        return dict(
            operation="create", target_type="Object", target_id=uuid.uuid4(),
            parent_type="ObjectType", parent_id=self.object_type.id, before=None, after=payload,
        )

    def object_update(self, field, value):
        return dict(
            operation="update", target_type="Object", target_id=self.one.id,
            parent_type="ObjectType", parent_id=self.object_type.id, field=field,
            before={"field": field, "value": None}, after={"field": field, "value": value},
        )

    def error_codes(self, proposal):
        return set(proposal.submission_result.errors.values_list("code", flat=True))

    def assert_validation_failure(self, proposal, code):
        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(
            proposal.submission_result.outcome, ProposalSubmissionResult.Outcome.VALIDATION_FAILED
        )
        self.assertIn(code, self.error_codes(proposal))

    def test_a_valid_object_create_still_commits(self):
        proposal = self.submit(self.object_create(name="Fine"))

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertTrue(Object.objects.filter(name="Fine").exists())

    def test_a_create_with_a_blank_name_is_rejected_before_writing(self):
        proposal = self.submit(self.object_create(name=""))

        self.assert_validation_failure(proposal, "name_required")
        self.assertFalse(Object.objects.filter(name="").exists())

    def test_a_create_with_no_name_key_takes_the_default_and_is_rejected(self):
        change = self.object_create()
        del change["after"]["name"]

        proposal = self.submit(change)

        self.assert_validation_failure(proposal, "name_required")

    def test_a_create_with_an_overlong_name_is_rejected_not_crashed(self):
        proposal = self.submit(self.object_create(name="x" * 300))

        self.assert_validation_failure(proposal, "name_too_long")

    def test_a_create_with_a_non_boolean_is_active_is_rejected(self):
        proposal = self.submit(self.object_create(is_active="yes"))

        self.assert_validation_failure(proposal, "invalid_is_active")

    def test_updating_the_name_to_blank_is_rejected_and_leaves_the_object(self):
        proposal = self.submit(self.object_update("name", ""))

        self.assert_validation_failure(proposal, "name_required")
        self.one.refresh_from_db()
        self.assertEqual(self.one.name, "One")

    def test_updating_is_active_to_none_is_rejected_not_crashed(self):
        proposal = self.submit(self.object_update("is_active", None))

        self.assert_validation_failure(proposal, "invalid_is_active")
        self.one.refresh_from_db()
        self.assertTrue(self.one.is_active)

    def test_a_valid_is_active_update_commits(self):
        proposal = self.submit(self.object_update("is_active", False))

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.one.refresh_from_db()
        self.assertFalse(self.one.is_active)

    def test_a_relationship_with_a_missing_endpoint_is_reported_not_crashed(self):
        proposal = self.submit(
            dict(
                operation="create", target_type="Relationship", target_id=uuid.uuid4(),
                parent_type="RelationshipType", parent_id=self.relationship_type.id, before=None,
                after={"subject_id": str(self.one.id), "object_id": str(uuid.uuid4()),
                       "is_active": True, "attributes": {}},
            )
        )

        self.assert_validation_failure(proposal, "endpoint_not_found")
        self.assertFalse(Relationship.objects.exists())

    def test_an_endpoint_from_another_model_is_reported(self):
        other = Model.objects.create(workspace=self.workspace, name="Other")
        other_type = ObjectType.objects.create(model=other, name="Thing", key="thing")
        foreign = Object.objects.create(model=other, object_type=other_type, name="Foreign")

        proposal = self.submit(
            dict(
                operation="create", target_type="Relationship", target_id=uuid.uuid4(),
                parent_type="RelationshipType", parent_id=self.relationship_type.id, before=None,
                after={"subject_id": str(self.one.id), "object_id": str(foreign.id),
                       "is_active": True, "attributes": {}},
            )
        )

        self.assert_validation_failure(proposal, "endpoint_not_found")

    def test_a_relationship_whose_endpoints_are_created_in_the_same_proposal_commits(self):
        new_object = self.object_create(name="Fresh")

        proposal = self.submit(
            new_object,
            dict(
                operation="create", target_type="Relationship", target_id=uuid.uuid4(),
                parent_type="RelationshipType", parent_id=self.relationship_type.id, before=None,
                after={"subject_id": str(self.one.id), "object_id": str(new_object["target_id"]),
                       "is_active": True, "attributes": {}},
            ),
        )

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(Relationship.objects.count(), 1)

    def test_a_relationship_with_a_non_boolean_is_active_is_rejected(self):
        proposal = self.submit(
            dict(
                operation="create", target_type="Relationship", target_id=uuid.uuid4(),
                parent_type="RelationshipType", parent_id=self.relationship_type.id, before=None,
                after={"subject_id": str(self.one.id), "object_id": str(self.two.id),
                       "is_active": None, "attributes": {}},
            )
        )

        self.assert_validation_failure(proposal, "invalid_is_active")
