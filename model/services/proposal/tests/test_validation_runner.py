import uuid

from django.db import transaction
from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService
from model.services.proposal.validation_runner import apply_and_validate
from workspace.models import Workspace


class ValidationRunnerTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(
            email="runner@example.com",
            password="test-password",
        )

    def _new_model(self, revision=1):
        return Model.objects.create(
            workspace=self.workspace,
            name="Test Model",
            revision=revision,
        )

    def _working_proposal_with_object_type_create(self, model, key="alpha"):
        proposal = ProposalService.get_or_create_working(model, self.user)
        object_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": key.title(),
                "key": key,
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        return proposal, object_type_id

    def _working_proposal_with_invalid_change(self, model):
        """An UPDATE targeting a Model field that doesn't exist -- guaranteed
        to produce a ValidationIssue without touching any real canonical row."""

        proposal = ProposalService.get_or_create_working(model, self.user)

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            before=None,
            after={"field": "not_a_real_field", "value": "x"},
        )

        return proposal


class ApplyAndValidateTests(ValidationRunnerTestCase):

    def test_apply_and_validate_returns_combined_issues(self):
        model = self._new_model()
        proposal = self._working_proposal_with_invalid_change(model)

        with transaction.atomic():
            outcome = apply_and_validate(model, proposal)
            transaction.set_rollback(True)

        self.assertTrue(outcome.issues)
        self.assertEqual(outcome.issues[0].code, "invalid_change")

    def test_apply_and_validate_writes_are_visible_within_the_open_transaction(self):
        model = self._new_model()
        proposal, object_type_id = self._working_proposal_with_object_type_create(model)

        with transaction.atomic():
            outcome = apply_and_validate(model, proposal)

            self.assertEqual(outcome.issues, [])
            self.assertTrue(ObjectType.objects.filter(id=object_type_id).exists())

            transaction.set_rollback(True)

        self.assertFalse(ObjectType.objects.filter(id=object_type_id).exists())

    def test_apply_and_validate_does_not_touch_proposal_or_evidence_tables(self):
        model = self._new_model()
        proposal, _ = self._working_proposal_with_object_type_create(model)

        status_before = proposal.status
        validation_status_before = proposal.validation_status

        with transaction.atomic():
            apply_and_validate(model, proposal)
            transaction.set_rollback(True)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, status_before)
        self.assertEqual(proposal.validation_status, validation_status_before)

    def test_apply_and_validate_reports_before_revision(self):
        model = self._new_model(revision=7)
        proposal, _ = self._working_proposal_with_object_type_create(model)

        with transaction.atomic():
            outcome = apply_and_validate(model, proposal)
            transaction.set_rollback(True)

        self.assertEqual(outcome.before_revision, 7)
