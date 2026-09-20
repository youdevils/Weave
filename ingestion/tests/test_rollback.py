from unittest.mock import patch

from ingestion.models import ImportSource
from ingestion.services.proposals import create_import_proposal
from ingestion.tests.base import ImportTestCase
from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.evidence import EvidenceService
from model.services.proposal.proposal import ProposalService

MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
NAME = {"column": 1, "field": "field.name"}


class RollbackTests(ImportTestCase):
    """A failure at any step of creating the proposal leaves nothing behind."""

    def setUp(self):
        self.make_app("Existing", "A0")
        self.source = self.stage([["App ID", "Name"], ["A1", "One"], ["A0", "Renamed"]])
        self.mapping = self.object_mapping(MATCH, NAME)

    def assert_nothing_left(self):
        self.assertEqual(Proposal.objects.count(), 0)
        self.assertEqual(ProposalChange.objects.count(), 0)
        self.assertEqual(EvidenceReference.objects.count(), 0)
        self.assertEqual(list(Object.objects.values_list("name", flat=True)), ["Existing"])

        source = ImportSource.objects.get(pk=self.source.pk)
        self.assertIsNone(source.imported_at)
        self.assertIsNone(source.proposal)

    def test_failure_while_persisting_evidence(self):
        with patch.object(EvidenceService, "add_for_changes", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assert_nothing_left()

    def test_failure_while_recording_the_changes(self):
        with patch.object(ProposalService, "record_changes_bulk", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assert_nothing_left()

    def test_failure_while_creating_the_proposal(self):
        with patch.object(ProposalService, "create_working", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assert_nothing_left()

    def test_failure_after_the_changes_are_written_still_rolls_everything_back(self):
        real = EvidenceService.add_for_changes

        def add_then_fail(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("late failure")

        with patch.object(EvidenceService, "add_for_changes", side_effect=add_then_fail):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assert_nothing_left()

    def test_failure_stamping_the_source(self):
        with patch("ingestion.services.proposals.timezone.now", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assert_nothing_left()

    def test_a_failed_attempt_can_simply_be_retried(self):
        with patch.object(EvidenceService, "add_for_changes", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_import_proposal(self.model, self.editor, self.source, self.mapping)

        result = create_import_proposal(self.model, self.editor, self.source, self.mapping)

        self.assertEqual(Proposal.objects.count(), 1)
        self.assertEqual(result.proposal.changes.count(), 2)
        self.assertEqual(EvidenceReference.objects.count(), 2)
