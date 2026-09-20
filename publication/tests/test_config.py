import uuid

from model.services.appearance import AppearanceService
from publication.services.config import (
    DEFAULT_DEPTH,
    MAX_DEPTH,
    ConfigError,
    sanitise_default_view,
    sanitise_presentation,
    sanitise_scope,
)
from publication.services.filenames import default_filename, normalise_filename
from publication.services.normalise import normalise_config

from .base import PublicationTestCase


class ScopeSanitiserTests(PublicationTestCase):

    def test_empty_input_is_the_whole_model(self):
        scope, notices = sanitise_scope(None, self.canonical())

        self.assertTrue(scope.is_whole_model)
        self.assertEqual(scope.depth, DEFAULT_DEPTH)
        self.assertEqual(notices, [])

    def test_known_ids_are_kept_and_unknown_ones_reported(self):
        gone = str(uuid.uuid4())
        scope, notices = sanitise_scope(
            {
                "object_types": {"excluded": [str(self.team_type.id), gone]},
                "relationship_types": {"excluded": [gone]},
                "traversal": {"roots": [gone], "depth": 2},
            },
            self.canonical(),
        )

        self.assertEqual(scope.excluded_object_types, (str(self.team_type.id),))
        self.assertEqual(scope.excluded_relationship_types, ())
        self.assertEqual(scope.roots, ())
        self.assertEqual({n["kind"] for n in notices}, {"object_type", "relationship_type", "object"})
        self.assertTrue(all(n["section"] == "Scope" for n in notices))

    def test_an_attribute_whose_definition_is_gone_is_dropped(self):
        gone = {"type_id": str(self.person_type.id), "key": "deleted", "op": "contains", "value": "x"}

        scope, notices = sanitise_scope({"attribute_filters": [gone]}, self.canonical())

        self.assertEqual(scope.attribute_filters, ())
        self.assertEqual([n["kind"] for n in notices], ["attribute_filter"])

    def test_depth_is_clamped_and_null_means_unlimited(self):
        canonical = self.canonical()

        self.assertEqual(sanitise_scope({"traversal": {"depth": 99}}, canonical)[0].depth, MAX_DEPTH)
        self.assertEqual(sanitise_scope({"traversal": {"depth": -3}}, canonical)[0].depth, 0)
        self.assertIsNone(sanitise_scope({"traversal": {"depth": None}}, canonical)[0].depth)
        self.assertEqual(sanitise_scope({"traversal": {"depth": "deep"}}, canonical)[0].depth, DEFAULT_DEPTH)
        self.assertEqual(sanitise_scope({"traversal": {"depth": True}}, canonical)[0].depth, DEFAULT_DEPTH)

    def test_garbage_shapes_do_not_raise(self):
        scope, _ = sanitise_scope({"object_types": "x", "relationship_types": [], "traversal": 5}, self.canonical())

        self.assertTrue(scope.is_whole_model)

    def test_a_non_list_filter_document_is_an_error(self):
        with self.assertRaises(ConfigError):
            sanitise_scope({"attribute_filters": "nope"}, self.canonical())

    def test_the_stored_form_round_trips(self):
        raw = {
            "object_types": {"excluded": [str(self.team_type.id)]},
            "attribute_filters": [
                {"type_id": str(self.person_type.id), "key": "status", "op": "in", "value": ["Active"]}
            ],
            "traversal": {"roots": [], "depth": 3},
        }
        canonical = self.canonical()

        scope, _ = sanitise_scope(raw, canonical)
        again, notices = sanitise_scope(scope.to_dict(), canonical)

        self.assertEqual(again, scope)
        self.assertEqual(notices, [])


class PresentationTests(PublicationTestCase):

    def test_a_valid_colour_is_normalised(self):
        presentation, notices = sanitise_presentation({"theme_colour": "#abc"}, "#4C6EF5")

        self.assertEqual(presentation.theme_colour, "#AABBCC")
        self.assertEqual(notices, [])

    def test_an_invalid_colour_falls_back_and_is_reported(self):
        presentation, notices = sanitise_presentation({"theme_colour": "javascript:1"}, "#4C6EF5")

        self.assertEqual(presentation.theme_colour, "#4C6EF5")
        self.assertEqual([n["kind"] for n in notices], ["colour"])

    def test_the_model_accent_is_the_default(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")

        self.assertEqual(self.normalised().config.presentation.theme_colour, "#00AA00")


class DefaultViewTests(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice")
        self.ops = self.make_object(self.team_type, "Ops")

    def test_it_is_reconciled_against_what_is_published_not_the_whole_model(self):
        raw = {
            "scope": {"object_types": {"excluded": [str(self.team_type.id)]}},
            "default_view": {"state": {"include": [str(self.ops.id), str(self.alice.id)]}},
        }

        result = self.normalised(raw)

        self.assertEqual(result.config.default_view.query.include, {str(self.alice.id)})
        self.assertEqual([n["section"] for n in result.notices], ["Opening view"])

    def test_a_selection_must_exist_in_the_published_dataset(self):
        published = self.normalised().published

        view, notices = sanitise_default_view({"selection": {"kind": "object", "id": str(self.alice.id)}}, published)
        self.assertEqual(view.selection, {"kind": "object", "id": str(self.alice.id)})
        self.assertEqual(notices, [])

        view, notices = sanitise_default_view({"selection": {"kind": "object", "id": str(uuid.uuid4())}}, published)
        self.assertIsNone(view.selection)
        self.assertEqual([n["kind"] for n in notices], ["selection"])

        view, _ = sanitise_default_view({"selection": {"kind": "wat", "id": str(self.alice.id)}}, published)
        self.assertIsNone(view.selection)

    def test_limit_is_clamped(self):
        published = self.normalised().published

        self.assertEqual(sanitise_default_view({"limit": 5000}, published)[0].query.limit, 1000)
        self.assertEqual(sanitise_default_view({}, published)[0].query.limit, 300)


class NormaliseConfigTests(PublicationTestCase):

    def test_a_non_object_definition_is_an_error(self):
        for raw in (None, [], "x", 3):
            with self.subTest(raw=raw), self.assertRaises(ConfigError):
                normalise_config(self.model, raw, self.canonical())

    def test_missing_metadata_takes_defaults(self):
        config = self.normalised({}).config

        self.assertEqual(config.title, "Test Model")
        self.assertEqual(config.description, "")
        self.assertEqual(config.filename, default_filename("Test Model", 1))

    def test_metadata_is_trimmed_and_bounded(self):
        raw = {"title": "  A   title  ", "description": "x" * 5000, "filename": "../../evil"}

        config = self.normalised(raw).config

        self.assertEqual(config.title, "A title")
        self.assertEqual(len(config.description), 1000)
        self.assertEqual(config.filename, "evil.html")


class FilenameTests(PublicationTestCase):

    def test_default_filename_uses_the_model_slug_and_revision(self):
        self.assertEqual(default_filename("Sales & Ops Model!", 7), "sales-ops-model-r7.html")
        self.assertEqual(default_filename("???", 2), "model-r2.html")

    def test_paths_and_control_characters_are_removed(self):
        cases = (
            ("../../etc/passwd", "etcpasswd.html"),
            ("C:\\Windows\\report", "CWindowsreport.html"),
            ('a"b<c>d|e?f*g', "abcdefg.html"),
            ("tab\tnew\nline", "tabnewline.html"),
            ("report.html", "report.html"),
            ("report.HTML.htm", "report.html"),
            ("  spaced   out  ", "spaced out.html"),
            ("trailing dots...", "trailing dots.html"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalise_filename(raw, "fallback.html"), expected)

    def test_unusable_names_fall_back(self):
        for raw in (None, "", "   ", "...", ".html", "CON", "nul.html", "com1", "LPT9.txt", "///"):
            with self.subTest(raw=raw):
                self.assertEqual(normalise_filename(raw, "fallback.html"), "fallback.html")

    def test_length_is_bounded_and_keeps_the_extension(self):
        name = normalise_filename("x" * 500, "fallback.html")

        self.assertEqual(len(name), 120)
        self.assertTrue(name.endswith(".html"))
