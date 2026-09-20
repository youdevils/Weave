import json
import uuid
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from model.services.appearance import AppearanceService
from publication.models import Publication
from publication.services import publishing
from publication.services.bundle import compute_digest
from publication.services.defaults import resolve_defaults
from publication.services.portable.validator import split_document

from .base import PublicationTestCase


class PublishFixture(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(self.alice, self.ops)

    def raw(self, **overrides):
        return {"title": "Board pack", "filename": "board.html", **overrides}

    def expected_for(self, raw):
        """What the page would send back: the revision and digest of its preview."""
        result = publishing.preview(self.model.id, raw)
        return {"revision": result.revision, "digest": result.digest}

    def publish(self, raw=None, expected=None, user=None):
        raw = raw if raw is not None else self.raw()
        return publishing.publish(
            self.model.id, user or self.editor, raw, expected if expected is not None else self.expected_for(raw)
        )


class PreviewTests(PublishFixture):

    def test_preview_describes_exactly_what_publish_will_contain(self):
        raw = self.raw(scope={"object_types": {"excluded": [str(self.team_type.id)]}})

        preview = publishing.preview(self.model.id, raw)
        artifact = self.publish(raw)

        self.assertEqual(preview.summary["objects"], 1)
        self.assertEqual(preview.summary["totalObjects"], 2)
        (block,) = split_document(artifact.html)["data"]
        embedded = json.loads(block)
        self.assertEqual(embedded["dataset"], preview.bundle["dataset"])
        self.assertEqual(embedded["digest"], preview.digest)

    def test_preview_writes_nothing(self):
        publishing.preview(self.model.id, self.raw())

        self.assertEqual(Publication.objects.count(), 0)

    def test_preview_does_not_take_the_row_lock(self):
        with CaptureQueriesContext(connection) as queries:
            publishing.preview(self.model.id, self.raw())

        self.assertFalse([q for q in queries if "FOR UPDATE" in q["sql"]])

    def test_preview_reports_notices_for_stale_settings(self):
        raw = self.raw(scope={"object_types": {"excluded": [str(uuid.uuid4())]}})

        preview = publishing.preview(self.model.id, raw)

        self.assertEqual([n["kind"] for n in preview.notices], ["object_type"])

    def test_a_malformed_definition_is_an_invalid_publication(self):
        with self.assertRaises(publishing.InvalidPublication):
            publishing.preview(self.model.id, "nope")

    @override_settings(PUBLICATION_MAX_OBJECTS=1)
    def test_an_oversized_selection_previews_counts_but_no_bundle(self):
        preview = publishing.preview(self.model.id, self.raw())

        self.assertIsNone(preview.bundle)
        self.assertIsNone(preview.digest)
        self.assertIn("at most 1", preview.too_large)
        self.assertEqual(preview.summary["objects"], 2)

    @override_settings(PUBLICATION_MAX_BYTES=100)
    def test_a_selection_over_the_byte_limit_is_too_large_too(self):
        preview = publishing.preview(self.model.id, self.raw())

        self.assertIsNone(preview.bundle)
        self.assertIn("too large", preview.too_large)


class SuccessfulPublishTests(PublishFixture):

    def test_a_publication_records_the_definition_that_was_used(self):
        raw = self.raw(
            description="For the board",
            scope={"traversal": {"roots": [str(self.alice.id)], "depth": 0}},
            presentation={"theme_colour": "#00aa00"},
            default_view={"selection": {"kind": "object", "id": str(self.alice.id)}, "limit": 50},
        )
        AppearanceService.update_customisation(self.model, "object", "background", "#ff0000")

        artifact = self.publish(raw)

        publication = Publication.objects.get()
        self.assertEqual(artifact.publication, publication)
        self.assertEqual(publication.model, self.model)
        self.assertEqual(publication.source_revision, self.model.revision)
        self.assertEqual(publication.sequence, 1)
        self.assertEqual(publication.title, "Board pack")
        self.assertEqual(publication.description, "For the board")
        self.assertEqual(publication.filename, "board.html")
        self.assertEqual(publication.published_by, self.editor)
        self.assertEqual(publication.scope["traversal"], {"roots": [str(self.alice.id)], "depth": 0})
        self.assertEqual(publication.presentation["theme_colour"], "#00AA00")
        self.assertEqual(publication.default_view["selection"], {"kind": "object", "id": str(self.alice.id)})
        self.assertEqual(publication.default_view["limit"], 50)
        self.assertEqual(publication.appearance_snapshot["objects"], {"background": "#FF0000"})
        self.assertEqual((publication.object_count, publication.relationship_count), (1, 0))
        self.assertEqual(publication.format_version, 1)

    def test_the_stored_digest_is_the_digest_of_what_is_in_the_file(self):
        artifact = self.publish()

        (block,) = split_document(artifact.html)["data"]
        embedded = json.loads(block)
        self.assertEqual(compute_digest(embedded), artifact.publication.content_digest)
        self.assertEqual(embedded["publication"]["id"], str(artifact.publication.id))
        self.assertEqual(embedded["publication"]["sequence"], 1)
        self.assertEqual(embedded["publication"]["publishedAt"], artifact.publication.published_at.isoformat())

    def test_the_stored_scope_is_the_sanitised_one(self):
        gone = str(uuid.uuid4())
        raw = self.raw(scope={"object_types": {"excluded": [gone]}, "traversal": {"depth": 99}})

        self.publish(raw)

        scope = Publication.objects.get().scope
        self.assertEqual(scope["object_types"]["excluded"], [])
        self.assertEqual(scope["traversal"]["depth"], 5)

    def test_each_publication_is_a_new_immutable_record(self):
        first = self.publish().publication
        snapshot = Publication.objects.filter(pk=first.pk).values().get()

        self.make_object(self.team_type, "Later Team")
        second = self.publish(self.raw(title="Second")).publication

        self.assertEqual((first.sequence, second.sequence), (1, 2))
        self.assertEqual(Publication.objects.filter(pk=first.pk).values().get(), snapshot)

    def test_the_model_row_is_locked_while_publishing(self):
        with CaptureQueriesContext(connection) as queries:
            self.publish()

        self.assertTrue([q for q in queries if "FOR UPDATE" in q["sql"]])

    def test_only_canonical_content_is_published(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Proposed Pat")
        self.update(proposal, "Object", self.alice.id, "name", "Alice Renamed")

        artifact = self.publish()

        self.assertNotIn("Proposed Pat", artifact.html)
        self.assertNotIn("Alice Renamed", artifact.html)
        self.assertIn("Alice", artifact.html)

    def test_the_html_is_not_stored_anywhere(self):
        artifact = self.publish()

        row = Publication.objects.filter(pk=artifact.publication.pk).values().get()
        self.assertNotIn(artifact.html[:200], json.dumps(row, default=str))
        self.assertLess(len(json.dumps(row, default=str)), 20_000)


class RefusedPublishTests(PublishFixture):
    """Nothing is stored (and no sequence number is used) when a publish is refused or fails."""

    def assertNothingStored(self):
        self.assertEqual(Publication.objects.count(), 0)

    def test_publishing_requires_a_preview(self):
        for expected in (None, {}, {"revision": 1}, {"digest": "x"}, "nope"):
            with self.subTest(expected=expected), self.assertRaises(publishing.InvalidPublication):
                publishing.publish(self.model.id, self.editor, self.raw(), expected)
        self.assertNothingStored()

    def test_a_revision_change_since_the_preview_is_refused(self):
        raw = self.raw()
        expected = self.expected_for(raw)
        self.model.revision += 1
        self.model.save(update_fields=["revision"])

        with self.assertRaises(publishing.PublicationStale) as caught:
            publishing.publish(self.model.id, self.editor, raw, expected)

        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.details["revision"], self.model.revision)
        self.assertNothingStored()

    def test_new_content_since_the_preview_is_refused(self):
        raw = self.raw()
        expected = self.expected_for(raw)
        self.make_object(self.team_type, "Added after the preview")

        with self.assertRaises(publishing.PublicationStale):
            publishing.publish(self.model.id, self.editor, raw, expected)
        self.assertNothingStored()

    def test_an_appearance_change_since_the_preview_is_refused_even_though_the_revision_is_the_same(self):
        raw = self.raw()
        expected = self.expected_for(raw)
        AppearanceService.update_customisation(self.model, "object", "background", "#ff0000")

        with self.assertRaises(publishing.PublicationStale):
            publishing.publish(self.model.id, self.editor, raw, expected)
        self.assertNothingStored()

    def test_a_metadata_only_change_since_the_preview_is_fine(self):
        raw = self.raw()
        expected = self.expected_for(raw)

        artifact = publishing.publish(self.model.id, self.editor, {**raw, "title": "Renamed after preview"}, expected)

        self.assertEqual(artifact.publication.title, "Renamed after preview")

    def test_a_failure_while_rendering_leaves_no_publication(self):
        raw = self.raw()
        expected = self.expected_for(raw)

        with mock.patch.object(publishing, "render_document", side_effect=RuntimeError("boom")):
            with self.assertRaises(publishing.PublicationGenerationFailed) as caught:
                publishing.publish(self.model.id, self.editor, raw, expected)

        self.assertEqual(caught.exception.status, 500)
        self.assertNotIn("boom", str(caught.exception))
        self.assertNothingStored()

    def test_a_document_that_fails_validation_is_never_published(self):
        raw = self.raw()
        expected = self.expected_for(raw)

        with mock.patch.object(publishing, "render_document", return_value="<html><body>no data, no csp</body></html>"):
            with self.assertRaises(publishing.PublicationGenerationFailed):
                publishing.publish(self.model.id, self.editor, raw, expected)

        self.assertNothingStored()

    def test_a_failed_attempt_does_not_use_up_the_sequence_number(self):
        raw = self.raw()
        expected = self.expected_for(raw)
        with mock.patch.object(publishing, "render_document", side_effect=RuntimeError("boom")):
            with self.assertRaises(publishing.PublicationGenerationFailed):
                publishing.publish(self.model.id, self.editor, raw, expected)

        self.assertEqual(self.publish(raw).publication.sequence, 1)

    @override_settings(PUBLICATION_MAX_OBJECTS=1)
    def test_an_oversized_selection_is_refused(self):
        with self.assertRaises(publishing.PublicationTooLarge) as caught:
            publishing.publish(self.model.id, self.editor, self.raw(), {"revision": 1, "digest": "x"})

        self.assertEqual(caught.exception.status, 422)
        self.assertNothingStored()

    def test_a_failure_does_not_change_the_defaults_for_the_next_publication(self):
        self.publish(self.raw(title="First good one", filename="first.html"))
        before = resolve_defaults(self.model, self.canonical())[0].config

        raw = self.raw(title="Doomed", filename="doomed.html")
        expected = self.expected_for(raw)
        with mock.patch.object(publishing, "render_document", side_effect=RuntimeError("boom")):
            with self.assertRaises(publishing.PublicationGenerationFailed):
                publishing.publish(self.model.id, self.editor, raw, expected)

        after = resolve_defaults(self.model, self.canonical())[0].config
        self.assertEqual(after, before)
        self.assertEqual(after.title, "First good one")


class DefaultsAfterPublishTests(PublishFixture):

    def test_a_successful_publication_becomes_the_default_for_the_next(self):
        raw = self.raw(
            title="Quarterly",
            filename="quarterly.html",
            scope={"object_types": {"excluded": [str(self.team_type.id)]}},
            presentation={"theme_colour": "#123456"},
        )
        self.publish(raw)

        config = resolve_defaults(self.model, self.canonical())[0].config

        self.assertEqual(config.title, "Quarterly")
        self.assertEqual(config.filename, "quarterly.html")
        self.assertEqual(config.scope.excluded_object_types, (str(self.team_type.id),))
        self.assertEqual(config.presentation.theme_colour, "#123456")
