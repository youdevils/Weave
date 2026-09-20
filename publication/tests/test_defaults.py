import uuid

from model.services.appearance import AppearanceService
from publication.models import Publication
from publication.services.defaults import previous_publication, resolve_defaults
from publication.services.filenames import default_filename

from .base import PublicationTestCase


class DefaultsFixture(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")

    def defaults(self):
        return resolve_defaults(self.model, self.canonical())

    def stored_scope(self, **scope):
        return {
            "version": 1,
            "object_types": {"excluded": scope.get("excluded_types", [])},
            "relationship_types": {"excluded": []},
            "attribute_filters": scope.get("filters", []),
            "traversal": {"roots": scope.get("roots", []), "depth": scope.get("depth", 1)},
        }


class FirstPublicationTests(DefaultsFixture):

    def test_a_model_with_no_publication_gets_system_defaults(self):
        result, previous = self.defaults()

        self.assertIsNone(previous)
        config = result.config
        self.assertTrue(config.scope.is_whole_model)
        self.assertEqual(config.title, "Test Model")
        self.assertEqual(config.filename, default_filename("Test Model", 1))
        self.assertEqual(config.presentation.theme_colour, "#4C6EF5")
        self.assertEqual(result.notices, [])
        self.assertEqual(len(result.published.objects), 2)

    def test_the_model_accent_is_the_initial_theme_colour(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#123456")

        self.assertEqual(self.defaults()[0].config.presentation.theme_colour, "#123456")


class ReuseTests(DefaultsFixture):

    def test_the_previous_publication_supplies_the_defaults(self):
        self.make_publication(
            title="Board pack",
            description="For the board",
            filename="board.html",
            scope=self.stored_scope(excluded_types=[str(self.team_type.id)]),
            presentation={"version": 1, "theme_colour": "#00AA00"},
            default_view={
                "version": 1,
                "state": {"hiddenObjectTypes": [], "hiddenRelationshipTypes": [], "attributeFilters": [], "include": []},
                "selection": {"kind": "object", "id": str(self.alice.id)},
                "limit": 50,
            },
        )

        result, previous = self.defaults()

        self.assertEqual(previous.title, "Board pack")
        config = result.config
        self.assertEqual(config.title, "Board pack")
        self.assertEqual(config.description, "For the board")
        self.assertEqual(config.filename, "board.html")
        self.assertEqual(config.presentation.theme_colour, "#00AA00")
        self.assertEqual(config.scope.excluded_object_types, (str(self.team_type.id),))
        self.assertEqual(config.default_view.selection, {"kind": "object", "id": str(self.alice.id)})
        self.assertEqual(config.default_view.query.limit, 50)
        self.assertEqual([o.name for o in result.published.objects.values()], ["Alice"])
        self.assertEqual(result.notices, [])

    def test_the_most_recent_publication_wins(self):
        self.make_publication(sequence=1, title="Old")
        self.make_publication(sequence=3, title="Newest")
        self.make_publication(sequence=2, title="Middle")

        self.assertEqual(previous_publication(self.model).title, "Newest")
        self.assertEqual(self.defaults()[0].config.title, "Newest")

    def test_other_models_publications_are_ignored(self):
        from model.models.model import Model

        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        self.make_publication(model=other, title="Not mine")

        self.assertIsNone(previous_publication(self.model))
        self.assertEqual(self.defaults()[0].config.title, "Test Model")

    def test_defaults_are_a_copy_and_never_edit_the_previous_publication(self):
        stored = self.stored_scope(excluded_types=[str(uuid.uuid4())])  # stale on purpose
        publication = self.make_publication(scope=stored)

        self.defaults()

        fresh = Publication.objects.get(pk=publication.pk)
        self.assertEqual(fresh.scope, stored)
        self.assertEqual(fresh.scope["object_types"]["excluded"], stored["object_types"]["excluded"])

    def test_an_auto_generated_filename_follows_the_new_revision(self):
        self.make_publication(source_revision=1, filename=default_filename("Test Model", 1))
        self.model.revision = 4
        self.model.save(update_fields=["revision"])

        self.assertEqual(self.defaults()[0].config.filename, default_filename("Test Model", 4))

    def test_a_chosen_filename_is_kept_across_revisions(self):
        self.make_publication(source_revision=1, filename="quarterly-report.html")
        self.model.revision = 4
        self.model.save(update_fields=["revision"])

        self.assertEqual(self.defaults()[0].config.filename, "quarterly-report.html")


class ReconciliationTests(DefaultsFixture):

    def test_stale_settings_are_dropped_and_reported_not_fatal(self):
        gone = str(uuid.uuid4())
        self.make_publication(
            scope=self.stored_scope(
                excluded_types=[gone, str(self.team_type.id)],
                roots=[gone],
                filters=[{"type_id": str(self.person_type.id), "key": "deleted", "op": "contains", "value": "x"}],
            ),
            default_view={
                "version": 1,
                "state": {"hiddenObjectTypes": [gone], "include": [gone]},
                "selection": {"kind": "object", "id": gone},
                "limit": 300,
            },
            presentation={"version": 1, "theme_colour": "not-a-colour"},
        )

        result, _ = self.defaults()

        self.assertEqual(result.config.scope.excluded_object_types, (str(self.team_type.id),))
        self.assertEqual(result.config.scope.roots, ())
        self.assertEqual(result.config.scope.attribute_filters, ())
        self.assertIsNone(result.config.default_view.selection)
        self.assertEqual(result.config.presentation.theme_colour, "#4C6EF5")
        sections = sorted({n["section"] for n in result.notices})
        self.assertEqual(sections, ["Opening view", "Presentation", "Scope"])
        self.assertGreaterEqual(len(result.notices), 6)

    def test_content_deleted_since_the_last_publication_is_reconciled(self):
        self.make_publication(scope=self.stored_scope(roots=[str(self.ops.id)]))
        self.ops.delete()

        result, _ = self.defaults()

        self.assertEqual(result.config.scope.roots, ())
        self.assertEqual([n["kind"] for n in result.notices], ["object"])
