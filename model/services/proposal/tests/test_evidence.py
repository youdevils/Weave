import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal import submission
from model.services.proposal.evidence import (
    CHANGE_NOTE_MAX_LENGTH,
    MAX_EVIDENCE_PER_CHANGE,
    EvidenceService,
)
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


class EvidenceTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

    def setUp(self):
        self.proposal = ProposalService.get_or_create_working(self.model, self.user)
        self.change = self.record_type("alpha")

    def record_type(self, key, proposal=None, description=""):
        return ProposalService.record_change(
            proposal=proposal or self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=uuid.uuid4(),
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={
                "name": key.title(),
                "key": key,
                "description": description,
                "sort_order": 0,
                "is_active": True,
            },
        )

    def add(self, source="Contract.pdf", locator="p. 4", note="Signed", change=None, proposal=None):
        return EvidenceService.add(proposal or self.proposal, (change or self.change).id, source, locator, note)

    def lock(self, status):
        Proposal.objects.filter(id=self.proposal.id).update(status=status)
        self.proposal.refresh_from_db()


class AddEvidenceTests(EvidenceTestCase):

    def test_add_persists_evidence_against_the_change(self):
        evidence = self.add()

        self.assertEqual(evidence.change, self.change)
        self.assertEqual((evidence.source, evidence.locator, evidence.note), ("Contract.pdf", "p. 4", "Signed"))
        self.assertEqual(list(self.change.evidence.all()), [evidence])

    def test_locator_and_note_are_optional(self):
        evidence = EvidenceService.add(self.proposal, self.change.id, "https://example.com/spec")

        self.assertEqual((evidence.locator, evidence.note), ("", ""))

    def test_values_are_stripped(self):
        evidence = self.add(source="  Contract  ", locator=" p. 4 ", note="  ok ")

        self.assertEqual((evidence.source, evidence.locator, evidence.note), ("Contract", "p. 4", "ok"))

    def test_a_change_can_have_many_evidence_references(self):
        self.add(source="A")
        self.add(source="B")
        self.add(source="C")

        self.assertEqual(self.change.evidence.count(), 3)

    def test_the_same_source_may_be_repeated_across_changes(self):
        other = self.record_type("beta")

        self.add(source="Contract.pdf", change=self.change)
        self.add(source="Contract.pdf", change=other)

        self.assertEqual(EvidenceReference.objects.filter(source="Contract.pdf").count(), 2)
        self.assertEqual(self.change.evidence.count(), 1)
        self.assertEqual(other.evidence.count(), 1)

    def test_blank_source_is_rejected(self):
        for source in ("", "   ", None):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    EvidenceService.add(self.proposal, self.change.id, source)

        self.assertFalse(EvidenceReference.objects.exists())

    def test_over_long_values_are_rejected(self):
        with self.assertRaises(ValueError):
            self.add(source="x" * 501)
        with self.assertRaises(ValueError):
            self.add(locator="x" * 501)
        with self.assertRaises(ValueError):
            self.add(note="x" * 2001)

    def test_per_change_cap(self):
        for i in range(MAX_EVIDENCE_PER_CHANGE):
            self.add(source=f"S{i}")

        with self.assertRaises(ValueError):
            self.add(source="one too many")

    def test_a_change_of_another_proposal_is_not_found(self):
        other_proposal = Proposal.objects.create(model=self.model, created_by=self.user)
        foreign = self.record_type("gamma", proposal=other_proposal)

        with self.assertRaises(ProposalChange.DoesNotExist):
            EvidenceService.add(self.proposal, foreign.id, "Source")

        self.assertFalse(EvidenceReference.objects.exists())

    def test_an_unknown_or_malformed_change_id_is_not_found(self):
        for change_id in (uuid.uuid4(), "not-a-uuid", None):
            with self.subTest(change_id=change_id):
                with self.assertRaises(ProposalChange.DoesNotExist):
                    EvidenceService.add(self.proposal, change_id, "Source")


class UpdateAndRemoveEvidenceTests(EvidenceTestCase):

    def test_update_edits_only_that_evidence(self):
        first = self.add(source="A")
        second = self.add(source="B")

        EvidenceService.update(self.proposal, first.id, "A2", "sec 2", "new note")

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.source, first.locator, first.note), ("A2", "sec 2", "new note"))
        self.assertEqual(second.source, "B")

    def test_update_validates_like_add(self):
        evidence = self.add()

        with self.assertRaises(ValueError):
            EvidenceService.update(self.proposal, evidence.id, "  ")

        evidence.refresh_from_db()
        self.assertEqual(evidence.source, "Contract.pdf")

    def test_remove_deletes_only_that_evidence_and_keeps_the_change(self):
        first = self.add(source="A")
        second = self.add(source="B")

        returned = EvidenceService.remove(self.proposal, first.id)

        self.assertEqual(returned.id, self.change.id)
        self.assertEqual(list(self.change.evidence.all()), [second])
        self.assertTrue(ProposalChange.objects.filter(id=self.change.id).exists())

    def test_evidence_of_another_proposal_is_not_found(self):
        other_proposal = Proposal.objects.create(model=self.model, created_by=self.user)
        foreign = self.record_type("gamma", proposal=other_proposal)
        foreign_evidence = self.add(change=foreign, proposal=other_proposal)

        with self.assertRaises(EvidenceReference.DoesNotExist):
            EvidenceService.update(self.proposal, foreign_evidence.id, "Hijacked")
        with self.assertRaises(EvidenceReference.DoesNotExist):
            EvidenceService.remove(self.proposal, foreign_evidence.id)

        foreign_evidence.refresh_from_db()
        self.assertEqual(foreign_evidence.source, "Contract.pdf")

    def test_malformed_evidence_id_is_not_found(self):
        with self.assertRaises(EvidenceReference.DoesNotExist):
            EvidenceService.remove(self.proposal, "not-a-uuid")


class EditableStatusTests(EvidenceTestCase):

    def test_only_editable_proposals_accept_evidence_changes(self):
        evidence = self.add()

        for status in (
            Proposal.Status.QUEUED,
            Proposal.Status.PROCESSING,
            Proposal.Status.COMPLETED,
        ):
            with self.subTest(status=status):
                self.lock(status)

                with self.assertRaises(ValueError):
                    self.add(source="Nope")
                with self.assertRaises(ValueError):
                    EvidenceService.update(self.proposal, evidence.id, "Nope")
                with self.assertRaises(ValueError):
                    EvidenceService.remove(self.proposal, evidence.id)
                with self.assertRaises(ValueError):
                    EvidenceService.set_change_note(self.proposal, "Nope")

        evidence.refresh_from_db()
        self.assertEqual(evidence.source, "Contract.pdf")
        self.assertEqual(EvidenceReference.objects.count(), 1)

    def test_a_failed_proposal_is_editable(self):
        self.lock(Proposal.Status.FAILED)

        self.assertEqual(self.add(source="After failure").source, "After failure")


class NoSideEffectsTests(EvidenceTestCase):
    """Evidence is optional context: it never disturbs review or validation state."""

    def setUp(self):
        super().setUp()
        Proposal.objects.filter(id=self.proposal.id).update(validation_status=Proposal.ValidationStatus.VALID)
        ProposalChange.objects.filter(id=self.change.id).update(review_status=ProposalChange.ReviewStatus.REVIEWED)
        self.proposal.refresh_from_db()

    def assert_untouched(self):
        self.proposal.refresh_from_db()
        self.change.refresh_from_db()
        self.assertEqual(self.proposal.validation_status, Proposal.ValidationStatus.VALID)
        self.assertEqual(self.change.review_status, ProposalChange.ReviewStatus.REVIEWED)

    def test_add_update_remove_leave_review_and_validation_state_alone(self):
        evidence = self.add()
        self.assert_untouched()

        EvidenceService.update(self.proposal, evidence.id, "Changed")
        self.assert_untouched()

        EvidenceService.remove(self.proposal, evidence.id)
        self.assert_untouched()

    def test_change_note_leaves_review_and_validation_state_alone(self):
        EvidenceService.set_change_note(self.proposal, "Why")

        self.assert_untouched()

    def test_a_proposal_without_evidence_still_submits(self):
        self.assertFalse(EvidenceReference.objects.exists())

        ProposalService.submit(self.proposal)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.QUEUED)


class ChangeNoteTests(EvidenceTestCase):

    def test_change_note_is_stored_in_the_summary_field(self):
        EvidenceService.set_change_note(self.proposal, "  Quarterly clean-up  ")

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "Quarterly clean-up")

    def test_blank_clears_the_note(self):
        EvidenceService.set_change_note(self.proposal, "Something")
        EvidenceService.set_change_note(self.proposal, "   ")

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "")

    def test_over_long_note_is_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceService.set_change_note(self.proposal, "x" * (CHANGE_NOTE_MAX_LENGTH + 1))

    def test_the_note_is_not_required_to_submit(self):
        self.assertEqual(self.proposal.summary, "")

        ProposalService.submit(self.proposal)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.QUEUED)


class EvidenceLifecycleTests(EvidenceTestCase):

    def test_re_recording_a_change_keeps_its_evidence(self):
        evidence = self.add()

        again = ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=self.change.target_id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={"name": "Renamed", "key": "alpha", "description": "", "sort_order": 0, "is_active": True},
        )

        self.assertEqual(again.id, self.change.id)
        self.assertEqual(list(again.evidence.all()), [evidence])

    def test_re_recording_a_field_update_keeps_its_evidence(self):
        target_id = uuid.uuid4()

        def record(value):
            return ProposalService.record_change(
                proposal=self.proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Object",
                target_id=target_id,
                parent_type="ObjectType",
                parent_id=uuid.uuid4(),
                field="name",
                before={"field": "name", "value": "Old"},
                after={"field": "name", "value": value},
            )

        change = record("First")
        evidence = self.add(change=change)

        record("Second")

        change.refresh_from_db()
        self.assertEqual(change.after["value"], "Second")
        self.assertEqual(list(change.evidence.all()), [evidence])

    def test_editing_a_change_in_place_keeps_its_evidence(self):
        # The data editors fold edits to a proposal-only record into its CREATE payload.
        evidence = self.add()

        self.change.after = {**self.change.after, "name": "Edited"}
        self.change.save(update_fields=["after", "updated_at"])

        self.assertEqual(list(ProposalChange.objects.get(id=self.change.id).evidence.all()), [evidence])

    def test_discarding_a_change_removes_its_evidence(self):
        kept = self.record_type("beta")
        self.add(change=self.change)
        kept_evidence = self.add(change=kept)

        ProposalService.discard_change(
            proposal=self.proposal,
            target_type="ObjectType",
            target_id=self.change.target_id,
        )

        self.assertEqual(list(EvidenceReference.objects.all()), [kept_evidence])

    def test_discarding_one_field_change_only_removes_that_changes_evidence(self):
        target_id = uuid.uuid4()
        changes = {}
        for field in ("name", "description"):
            changes[field] = ProposalService.record_change(
                proposal=self.proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Object",
                target_id=target_id,
                parent_type="ObjectType",
                parent_id=uuid.uuid4(),
                field=field,
                before={"field": field, "value": "a"},
                after={"field": field, "value": "b"},
            )
            self.add(source=f"for {field}", change=changes[field])

        ProposalService.discard_change(
            proposal=self.proposal, target_type="Object", target_id=target_id, field="name"
        )

        self.assertEqual(list(EvidenceReference.objects.values_list("source", flat=True)), ["for description"])

    def test_discard_children_removes_child_evidence(self):
        parent_id = uuid.uuid4()
        child = ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=uuid.uuid4(),
            parent_type="ObjectType",
            parent_id=parent_id,
            before=None,
            after={"name": "Child", "description": "", "is_active": True, "attributes": {}},
        )
        self.add(change=child)

        ProposalService.discard_children(
            proposal=self.proposal,
            parent_type="ObjectType",
            parent_id=parent_id,
            child_target_types=("Object",),
        )

        self.assertFalse(EvidenceReference.objects.exists())

    def test_abandoning_a_proposal_leaves_no_orphaned_evidence(self):
        self.add()
        self.add(source="Other")

        ProposalService.abandon(self.proposal)

        self.assertFalse(ProposalChange.objects.exists())
        self.assertFalse(EvidenceReference.objects.exists())

    def test_removing_evidence_does_not_touch_the_change(self):
        evidence = self.add()
        before = ProposalChange.objects.get(id=self.change.id)

        EvidenceService.remove(self.proposal, evidence.id)

        after = ProposalChange.objects.get(id=self.change.id)
        self.assertEqual((after.after, after.review_status, after.updated_at), (before.after, before.review_status, before.updated_at))

    def test_evidence_survives_a_failed_submission_and_resubmission(self):
        # A duplicate key makes validation fail; the change (and its evidence) stay editable.
        from model.models.object_type import ObjectType

        ObjectType.objects.create(model=self.model, name="Alpha", key="alpha", is_active=True)
        evidence = self.add()

        ProposalService.submit(self.proposal)
        submission.claim_next(self.model.id)
        submission.process(self.proposal.id)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(list(ProposalChange.objects.get(id=self.change.id).evidence.all()), [evidence])

        # Fix the change, add more evidence, resubmit.
        fixed = ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=self.change.target_id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={"name": "Alpha 2", "key": "alpha_2", "description": "", "sort_order": 0, "is_active": True},
        )
        self.add(source="Second", change=fixed)
        self.assertEqual(fixed.evidence.count(), 2)

        ProposalService.submit(self.proposal)
        submission.claim_next(self.model.id)
        submission.process(self.proposal.id)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(ProposalChange.objects.get(id=self.change.id).evidence.count(), 2)

    def test_evidence_is_retained_after_approval(self):
        evidence = self.add()

        ProposalService.submit(self.proposal)
        submission.claim_next(self.model.id)
        submission.process(self.proposal.id)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertIsNotNone(self.proposal.completed_at)
        self.assertEqual(list(EvidenceReference.objects.all()), [evidence])
        self.assertEqual(evidence.change.proposal_id, self.proposal.id)

    def test_completed_at_is_only_set_on_success(self):
        from model.models.object_type import ObjectType

        ObjectType.objects.create(model=self.model, name="Alpha", key="alpha", is_active=True)

        ProposalService.submit(self.proposal)
        submission.claim_next(self.model.id)
        submission.process(self.proposal.id)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertIsNone(self.proposal.completed_at)
