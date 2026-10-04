import ast

from django.test import SimpleTestCase, TestCase

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.models.relationship_type import RelationshipType
from model.services import keys
from model.services.proposal.proposal import ProposalService
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


class IsValidKeyTests(SimpleTestCase):

    def test_a_key_round_tripped_through_slugify_is_valid(self):
        self.assertTrue(keys.is_valid_key("customer_account"))

    def test_a_hyphenated_value_is_not_valid(self):
        self.assertFalse(keys.is_valid_key("customer-account"))

    def test_blank_or_non_string_is_not_valid(self):
        self.assertFalse(keys.is_valid_key(""))
        self.assertFalse(keys.is_valid_key(None))
        self.assertFalse(keys.is_valid_key(123))

    def test_a_value_over_max_length_is_not_valid(self):
        self.assertFalse(keys.is_valid_key("x" * (keys.MAX_KEY_LENGTH + 1)))


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

    def test_returns_none_for_unsluggable_name_without_a_fallback(self):
        self.assertIsNone(keys.make_unique_key("???", used_keys=set()))

    def test_uses_the_fallback_when_name_has_no_sluggable_characters(self):
        self.assertEqual(keys.make_unique_key("???", used_keys=set(), fallback="object"), "object")

    def test_fallback_is_suffixed_on_collision_too(self):
        self.assertEqual(
            keys.make_unique_key("???", used_keys={"object"}, fallback="object"), "object_2"
        )


class ExistingKeysForTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model")
        cls.other_model = Model.objects.create(workspace=cls.workspace, name="Other Model")

        cls.object_type = ObjectType.objects.create(model=cls.model, name="Widget", key="widget")
        ObjectType.objects.create(model=cls.other_model, name="Gadget", key="gadget")
        cls.relationship_type = RelationshipType.objects.create(model=cls.model, name="Uses", key="uses")

    def test_returns_keys_for_object_type_scoped_to_model(self):
        self.assertEqual(keys.existing_keys_for("ObjectType", self.model), {"widget"})

    def test_returns_keys_for_relationship_type_scoped_to_model(self):
        self.assertEqual(keys.existing_keys_for("RelationshipType", self.model), {"uses"})

    def test_scoped_to_model_not_global(self):
        self.assertNotIn("gadget", keys.existing_keys_for("ObjectType", self.model))
        self.assertEqual(keys.existing_keys_for("ObjectType", self.other_model), {"gadget"})

    def test_supports_key_bearing_types(self):
        self.assertTrue(keys.supports("ObjectType"))
        self.assertTrue(keys.supports("RelationshipType"))
        self.assertTrue(keys.supports("AttributeDefinition"))
        self.assertTrue(keys.supports("Object"))
        self.assertFalse(keys.supports("Relationship"))

    def test_attribute_definition_keys_are_scoped_to_owning_object_type(self):
        AttributeDefinition.objects.create(
            object_type=self.object_type, name="Status", key="status", data_type="text",
        )

        self.assertEqual(
            keys.existing_keys_for(
                "AttributeDefinition", self.model,
                parent_type="ObjectType", parent_id=self.object_type.id,
            ),
            {"status"},
        )

    def test_attribute_definition_keys_do_not_leak_across_owning_types(self):
        other_type = ObjectType.objects.create(model=self.model, name="Other", key="other")
        AttributeDefinition.objects.create(
            object_type=other_type, name="Status", key="status", data_type="text",
        )

        self.assertEqual(
            keys.existing_keys_for(
                "AttributeDefinition", self.model,
                parent_type="ObjectType", parent_id=self.object_type.id,
            ),
            set(),
        )

    def test_attribute_definition_keys_are_scoped_to_owning_relationship_type(self):
        AttributeDefinition.objects.create(
            relationship_type=self.relationship_type, name="Since", key="since", data_type="text",
        )

        self.assertEqual(
            keys.existing_keys_for(
                "AttributeDefinition", self.model,
                parent_type="RelationshipType", parent_id=self.relationship_type.id,
            ),
            {"since"},
        )


class ClaimedKeysInProposalTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="u@example.com", password="x")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model")

    def test_none_when_no_proposal(self):
        self.assertEqual(keys.claimed_keys_in_proposal(None, "ObjectType"), set())

    def test_collects_keys_from_create_changes_of_the_same_type(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id="11111111-1111-1111-1111-111111111111",
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={"name": "Widget", "key": "widget", "description": "", "sort_order": 0, "is_active": True},
        )

        self.assertEqual(keys.claimed_keys_in_proposal(proposal, "ObjectType"), {"widget"})

    def test_attribute_definition_claims_are_scoped_to_the_same_parent(self):
        object_type = ObjectType.objects.create(model=self.model, name="Widget", key="widget")
        other_type = ObjectType.objects.create(model=self.model, name="Other", key="other")
        proposal = ProposalService.get_or_create_working(self.model, self.user)

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id="22222222-2222-2222-2222-222222222222",
            parent_type="ObjectType",
            parent_id=object_type.id,
            before=None,
            after={"name": "Status", "key": "status", "data_type": "text", "description": "", "required": False, "nullable": False, "default_value": None, "sort_order": 0, "config": {}, "is_active": True},
        )

        self.assertEqual(
            keys.claimed_keys_in_proposal(
                proposal, "AttributeDefinition", parent_type="ObjectType", parent_id=object_type.id,
            ),
            {"status"},
        )
        self.assertEqual(
            keys.claimed_keys_in_proposal(
                proposal, "AttributeDefinition", parent_type="ObjectType", parent_id=other_type.id,
            ),
            set(),
        )


class GenerateKeyTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="u2@example.com", password="x")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model")

    def test_derives_from_name(self):
        self.assertEqual(
            keys.generate_key("ObjectType", "Customer Account", model=self.model), "customer_account",
        )

    def test_avoids_a_canonical_collision(self):
        ObjectType.objects.create(model=self.model, name="Widget", key="widget")

        self.assertEqual(keys.generate_key("ObjectType", "Widget", model=self.model), "widget_2")

    def test_avoids_a_key_already_claimed_in_the_same_proposal(self):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id="33333333-3333-3333-3333-333333333333",
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={"name": "Widget", "key": "widget", "description": "", "sort_order": 0, "is_active": True},
        )

        self.assertEqual(
            keys.generate_key("ObjectType", "Widget", model=self.model, proposal=proposal), "widget_2",
        )

    def test_avoids_also_used_keys_the_caller_tracks_itself(self):
        self.assertEqual(
            keys.generate_key("ObjectType", "Widget", model=self.model, also_used={"widget"}), "widget_2",
        )

    def test_never_returns_none_even_for_an_unsluggable_name(self):
        self.assertEqual(keys.generate_key("ObjectType", "???", model=self.model), "object_type")

    def test_is_deterministic(self):
        self.assertEqual(
            keys.generate_key("ObjectType", "Widget", model=self.model),
            keys.generate_key("ObjectType", "Widget", model=self.model),
        )


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

    def test_no_module_level_import_of_proposal(self):
        """
        model.models.proposal/model.services.proposal are only imported
        lazily, inside claimed_keys_in_proposal -- this module is safe to
        import from ingestion's planners (see
        ingestion.tests.test_architecture.test_the_planners_do_not_read_proposals),
        which must never see proposal state.
        """

        import model.services.keys as keys_module

        with open(keys_module.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=keys_module.__file__)

        top_level_modules = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_modules.add(node.module)

        self.assertFalse(
            {m for m in top_level_modules if m.startswith(("model.models.proposal", "model.services.proposal"))},
        )
