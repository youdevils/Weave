import ast

from django.test import SimpleTestCase, TestCase

from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType
from model.services import keys
from workspace.models import Workspace


class SlugifyKeyTests(SimpleTestCase):

    def test_spaced_name_becomes_underscore_slug(self):
        self.assertEqual(keys.slugify_key("Customer Type"), "customer_type")

    def test_already_underscored_name_is_unchanged(self):
        self.assertEqual(keys.slugify_key("depends_on"), "depends_on")

    def test_unsluggable_name_returns_empty_string(self):
        for name in ("???", "", "   "):
            with self.subTest(name=name):
                self.assertEqual(keys.slugify_key(name), "")


class MakeUniqueKeyTests(SimpleTestCase):

    def test_returns_base_slug_when_unused(self):
        self.assertEqual(keys.make_unique_key("Widget", used_keys=set()), "widget")

    def test_appends_deterministic_numeric_suffix_on_collision(self):
        self.assertEqual(keys.make_unique_key("Widget", used_keys={"widget"}), "widget_2")
        self.assertEqual(
            keys.make_unique_key("Widget", used_keys={"widget", "widget_2"}), "widget_3"
        )

    def test_is_deterministic_not_random(self):
        used = {"widget"}
        self.assertEqual(
            keys.make_unique_key("Widget", used_keys=used),
            keys.make_unique_key("Widget", used_keys=used),
        )

    def test_respects_max_length_after_suffixing(self):
        long_name = "x" * 150
        used = {"x" * keys.MAX_KEY_LENGTH}

        candidate = keys.make_unique_key(long_name, used_keys=used)

        self.assertLessEqual(len(candidate), keys.MAX_KEY_LENGTH)
        self.assertNotIn(candidate, used)
        self.assertTrue(candidate.endswith("_2"))

    def test_returns_none_for_unsluggable_name(self):
        self.assertIsNone(keys.make_unique_key("???", used_keys=set()))


class ExistingKeysForTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model")
        cls.other_model = Model.objects.create(workspace=cls.workspace, name="Other Model")

        ObjectType.objects.create(model=cls.model, name="Widget", key="widget")
        ObjectType.objects.create(model=cls.other_model, name="Gadget", key="gadget")
        RelationshipType.objects.create(model=cls.model, name="Uses", key="uses")

    def test_returns_keys_for_object_type_scoped_to_model(self):
        self.assertEqual(keys.existing_keys_for("ObjectType", self.model), {"widget"})

    def test_returns_keys_for_relationship_type_scoped_to_model(self):
        self.assertEqual(keys.existing_keys_for("RelationshipType", self.model), {"uses"})

    def test_scoped_to_model_not_global(self):
        self.assertNotIn("gadget", keys.existing_keys_for("ObjectType", self.model))
        self.assertEqual(keys.existing_keys_for("ObjectType", self.other_model), {"gadget"})

    def test_supports_true_for_object_type_and_relationship_type_only(self):
        self.assertTrue(keys.supports("ObjectType"))
        self.assertTrue(keys.supports("RelationshipType"))
        self.assertFalse(keys.supports("AttributeDefinition"))
        self.assertFalse(keys.supports("Object"))
        self.assertFalse(keys.supports("Relationship"))


class KeysModuleHasNoAiOrAssistedDependencyTests(SimpleTestCase):
    """
    Structural proof (not just an assertion in prose) that model.services.keys
    does not depend on `ai` or `assisted` -- the later broader key-management
    refactor needs this module to remain reusable independent of either.
    """

    def test_no_import_of_ai_or_assisted(self):
        import model.services.keys as keys_module

        with open(keys_module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=keys_module.__file__)

        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])

        self.assertNotIn("ai", imported_roots)
        self.assertNotIn("assisted", imported_roots)
