import re
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from ingestion.models import ImportSource
from ingestion.services import source_file
from ingestion.services.errors import SourceFileError
from ingestion.services.proposals import create_import_proposal
from ingestion.tests.base import ImportTestCase, csv_bytes
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.proposal import Proposal
from model.services.model_deletion.deletion import delete_model
from model.services.proposal.proposal import ProposalService

MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
NAME = {"column": 1, "field": "field.name"}


class SourcePersistenceTests(ImportTestCase):

    def test_an_upload_is_persisted_as_a_staged_source_with_a_generated_name(self):
        source = self.stage([["App ID", "Name"], ["A1", "One"]], filename="Applications 2024.csv")

        self.assertEqual(source.original_filename, "Applications 2024.csv")
        self.assertRegex(source.stored_name, r"^[0-9a-f]{32}\.csv$")
        self.assertEqual((source.file_format, source.row_count), ("csv", 1))
        self.assertEqual(source.model, self.model)
        self.assertEqual(source.uploaded_by, self.editor)
        self.assertIsNone(source.imported_at)
        self.assertEqual(bytes(source.content), csv_bytes([["App ID", "Name"], ["A1", "One"]]))
        self.assertEqual(len(source.sha256), 64)

    def test_stored_names_are_unique_even_for_identical_filenames_and_content(self):
        rows = [["App ID"], ["A1"]]
        first = self.stage(rows, "same.csv", user=self.editor)
        second = self.stage(rows, "same.csv", user=self.owner)

        self.assertNotEqual(first.stored_name, second.stored_name)
        self.assertEqual(ImportSource.objects.filter(stored_name=first.stored_name).count(), 1)

    def test_the_stored_name_is_the_database_only_never_a_path_or_the_original_name(self):
        source = self.stage([["A"], ["1"]], filename="../../etc/passwd.csv")

        self.assertEqual(source.original_filename, "passwd.csv")
        self.assertNotIn("passwd", source.stored_name)
        self.assertNotIn("/", source.stored_name)

    def test_nothing_is_written_to_the_filesystem(self):
        with patch("builtins.open", side_effect=AssertionError("filesystem write")):
            self.stage([["A"], ["1"]])

    def test_display_names_are_sanitised(self):
        self.assertEqual(source_file.sanitise_filename("a\\b\\c.csv"), "c.csv")
        self.assertEqual(source_file.sanitise_filename("x‮gnp.csv"), "xgnp.csv")
        self.assertEqual(source_file.sanitise_filename("a\x00b\nc.csv"), "ab c.csv")
        self.assertEqual(source_file.sanitise_filename(""), "upload")
        self.assertLessEqual(len(source_file.sanitise_filename("x" * 500 + ".csv")), 200)
        self.assertTrue(source_file.sanitise_filename("x" * 500 + ".csv").endswith(".csv"))

    def test_unsupported_extensions_are_rejected(self):
        for name in ("data.txt", "data.ods", "data.csv.exe", "data", "data.xlsm"):
            with self.assertRaises(SourceFileError, msg=name):
                source_file.store_upload(self.model, self.editor, name, csv_bytes([["A"], ["1"]]))

    def test_an_unreadable_file_never_becomes_a_source(self):
        with self.assertRaises(SourceFileError):
            source_file.store_upload(self.model, self.editor, "bad.xlsx", b"PK\x03\x04junk")

        self.assertFalse(ImportSource.objects.exists())

    def test_content_must_match_the_extension(self):
        with self.assertRaises(SourceFileError):
            source_file.store_upload(self.model, self.editor, "sneaky.xls", csv_bytes([["A"], ["1"]]))

    @override_settings(IMPORT_MAX_FILE_BYTES=20)
    def test_the_size_limit_is_enforced_by_the_service_too(self):
        with self.assertRaises(SourceFileError) as raised:
            source_file.store_upload(self.model, self.editor, "big.csv", csv_bytes([["A"], ["x" * 50]]))

        self.assertEqual(raised.exception.code, "file_too_large")

    def test_an_empty_upload_is_rejected(self):
        with self.assertRaises(SourceFileError):
            source_file.store_upload(self.model, self.editor, "empty.csv", b"")


class StagedLifecycleTests(ImportTestCase):

    def test_a_new_upload_replaces_the_uploaders_earlier_staged_source(self):
        first = self.stage([["A"], ["1"]])
        second = self.stage([["A"], ["2"]])

        self.assertFalse(ImportSource.objects.filter(pk=first.pk).exists())
        self.assertTrue(ImportSource.objects.filter(pk=second.pk).exists())

    def test_it_does_not_touch_another_users_staged_source(self):
        theirs = self.stage([["A"], ["1"]], user=self.owner)
        self.stage([["A"], ["2"]], user=self.editor)

        self.assertTrue(ImportSource.objects.filter(pk=theirs.pk).exists())

    def test_a_staged_source_is_private_to_its_uploader(self):
        source = self.stage([["A"], ["1"]], user=self.editor)

        self.assertEqual(source_file.get_staged_source(self.model, self.editor, source.id), source)

        for user in (self.other_editor, self.owner):
            with self.assertRaises(ImportSource.DoesNotExist):
                source_file.get_staged_source(self.model, user, source.id)

    def test_a_staged_source_cannot_be_reached_through_another_model(self):
        source = self.stage([["A"], ["1"]])

        with self.assertRaises(ImportSource.DoesNotExist):
            source_file.get_staged_source(self.other_model, self.editor, source.id)

    def test_a_malformed_id_is_simply_not_found(self):
        for bad in ("nope", None, "", 5, "123e4567-e89b-12d3-a456-426614174000"):
            with self.assertRaises(ImportSource.DoesNotExist):
                source_file.get_staged_source(self.model, self.editor, bad)

    def test_old_staged_sources_are_swept_on_the_next_upload(self):
        old = self.stage([["A"], ["1"]], user=self.owner)
        ImportSource.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))

        self.stage([["A"], ["2"]], user=self.editor)

        self.assertFalse(ImportSource.objects.filter(pk=old.pk).exists())

    def test_recent_staged_sources_are_not_swept(self):
        recent = self.stage([["A"], ["1"]], user=self.owner)
        ImportSource.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(hours=2))

        self.stage([["A"], ["2"]], user=self.editor)

        self.assertTrue(ImportSource.objects.filter(pk=recent.pk).exists())

    def test_discarding_removes_the_source(self):
        source = self.stage([["A"], ["1"]])

        source_file.discard(source)

        self.assertFalse(ImportSource.objects.exists())


class EvidenceTests(ImportTestCase):

    def run_import(self, rows, user=None, filename="apps.csv"):
        user = user or self.editor
        source = self.stage(rows, filename, user=user)
        return source, create_import_proposal(self.model, user, source, self.object_mapping(MATCH, NAME))

    def test_every_change_gets_its_own_reference_pointing_at_the_stored_source(self):
        self.make_app("Old", "A0")

        source, result = self.run_import(
            [["App ID", "Name"], ["A1", "One"], ["A2", "Two"], ["A0", "Renamed"]], filename="Q3 apps.csv"
        )

        changes = list(result.proposal.changes.all())
        self.assertEqual(len(changes), 3)

        for change in changes:
            (evidence,) = change.evidence.all()
            self.assertEqual(evidence.source, source.stored_name)
            self.assertEqual(evidence.locator, "")
            self.assertEqual(evidence.note, "Data import: Q3 apps.csv")

        # Independent references: one per change, distinct rows.
        references = EvidenceReference.objects.filter(change__proposal=result.proposal)
        self.assertEqual(references.count(), 3)
        self.assertEqual(len({reference.id for reference in references}), 3)
        self.assertEqual(len({reference.change_id for reference in references}), 3)

    def test_the_source_value_resolves_back_to_exactly_one_file_in_this_model(self):
        source, result = self.run_import([["App ID", "Name"], ["A1", "One"]])

        evidence = EvidenceReference.objects.get(change__proposal=result.proposal)

        self.assertEqual(ImportSource.objects.get(model=self.model, stored_name=evidence.source), source)
        self.assertFalse(ImportSource.objects.filter(model=self.other_model, stored_name=evidence.source).exists())

    def test_no_op_rows_get_no_evidence(self):
        self.make_app("Same", "A1")

        _, result = self.run_import([["App ID", "Name"], ["A1", "Same"], ["A2", "New"]])

        self.assertEqual(EvidenceReference.objects.count(), 1)
        self.assertEqual(result.proposal.changes.count(), 1)

    def test_a_field_level_update_is_evidenced_per_field(self):
        self.make_app("Old", "A1", owner="Finance")
        source = self.stage([["App ID", "Name", "Owner"], ["A1", "New", "HR"]])

        result = create_import_proposal(
            self.model, self.editor, source,
            self.object_mapping(MATCH, NAME, {"column": 2, "field": "attribute.owner"}),
        )

        self.assertEqual(result.proposal.changes.count(), 2)
        self.assertEqual(EvidenceReference.objects.count(), 2)

    def test_an_imported_source_records_its_proposal_and_time(self):
        source, result = self.run_import([["App ID", "Name"], ["A1", "One"]])

        source.refresh_from_db()
        self.assertEqual(source.proposal, result.proposal)
        self.assertIsNotNone(source.imported_at)

    def test_an_imported_source_is_no_longer_reachable_as_a_staged_one(self):
        source, _ = self.run_import([["App ID", "Name"], ["A1", "One"]])

        with self.assertRaises(ImportSource.DoesNotExist):
            source_file.get_staged_source(self.model, self.editor, source.id)

    def test_the_same_file_imported_twice_gives_independent_references(self):
        rows = [["App ID", "Name"], ["A1", "One"]]
        first_source, first = self.run_import(rows)
        second_source, second = self.run_import([["App ID", "Name"], ["A2", "Two"]])

        first_ref = EvidenceReference.objects.get(change__proposal=first.proposal)
        second_ref = EvidenceReference.objects.get(change__proposal=second.proposal)
        self.assertNotEqual(first_ref.source, second_ref.source)


class SourceLifecycleTests(ImportTestCase):

    def import_one(self, app_id="A1"):
        source = self.stage([["App ID", "Name"], [app_id, "One"]])
        result = create_import_proposal(self.model, self.editor, source, self.object_mapping(MATCH, NAME))
        return source, result.proposal

    def test_discarding_a_change_or_its_evidence_keeps_the_source(self):
        source, proposal = self.import_one()
        change = proposal.changes.get()

        ProposalService.discard_change(proposal=proposal, target_type="Object", target_id=change.target_id)
        sweep = source_file.sweep(self.model)

        self.assertFalse(EvidenceReference.objects.exists())
        self.assertTrue(ImportSource.objects.filter(pk=source.pk).exists())
        self.assertEqual(sweep[0], 0)

    def test_abandoning_the_proposal_takes_its_evidence_and_the_source_is_then_swept(self):
        source, proposal = self.import_one()

        ProposalService.abandon(proposal)

        self.assertFalse(EvidenceReference.objects.exists())
        source.refresh_from_db()
        self.assertIsNone(source.proposal)

        source_file.sweep(self.model)

        self.assertFalse(ImportSource.objects.filter(pk=source.pk).exists())

    def test_a_source_whose_proposal_exists_is_kept_by_the_sweep(self):
        source, _ = self.import_one()

        source_file.sweep(self.model)

        self.assertTrue(ImportSource.objects.filter(pk=source.pk).exists())

    def test_deleting_the_model_removes_its_sources(self):
        source, _ = self.import_one()
        self.stage([["A"], ["1"]], user=self.owner)
        other_source = ImportSource.objects.create(
            model=self.other_model, uploaded_by=self.stranger, original_filename="x.csv",
            stored_name="f" * 32 + ".csv", file_format="csv", size_bytes=1, sha256="0" * 64, content=b"a",
        )

        delete_model(Model.objects.get(pk=self.model.pk))

        self.assertFalse(ImportSource.objects.filter(model_id=self.model.id).exists())
        self.assertFalse(EvidenceReference.objects.exists())
        self.assertTrue(ImportSource.objects.filter(pk=other_source.pk).exists())

    def test_sweeping_one_model_never_touches_another(self):
        old = ImportSource.objects.create(
            model=self.other_model, uploaded_by=self.stranger, original_filename="x.csv",
            stored_name="e" * 32 + ".csv", file_format="csv", size_bytes=1, sha256="0" * 64, content=b"a",
        )
        ImportSource.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))

        source_file.sweep(self.model)

        self.assertTrue(ImportSource.objects.filter(pk=old.pk).exists())

    def test_the_source_admin_never_exposes_the_bytes(self):
        from django.contrib import admin

        model_admin = admin.site._registry[ImportSource]

        self.assertIn("content", model_admin.exclude)
        self.assertNotIn("content", model_admin.list_display)
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
