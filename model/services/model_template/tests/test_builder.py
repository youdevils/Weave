import uuid

from django.test import SimpleTestCase

from model.model_templates.business_process import BUSINESS_PROCESS_TEMPLATE
from model.model_templates.delivery_project import DELIVERY_PROJECT_TEMPLATE
from model.services.model_template.builder import (
    TemplateDefinitionError,
    build_template_changes,
)

MODEL_ID = uuid.uuid4()


def _by_type(specs, target_type):
    return [spec for spec in specs if spec["target_type"] == target_type]


class BuildTemplateChangesShapeTests(SimpleTestCase):
    """
    Exercised against the two real templates: one spec per defined thing,
    with parent/target ids that thread together correctly.
    """

    def _assert_one_spec_per_definition(self, template):
        change_set = build_template_changes(template, MODEL_ID)

        object_types = template.get("object_types", [])
        relationship_types = template.get("relationship_types", [])
        objects = template.get("objects", [])
        relationships = template.get("relationships", [])

        expected_attribute_count = sum(
            len(object_type.get("attributes", [])) for object_type in object_types
        ) + sum(
            len(relationship_type.get("attributes", [])) for relationship_type in relationship_types
        )
        expected_rule_count = sum(
            len(relationship_type.get("rules", [])) for relationship_type in relationship_types
        )

        self.assertEqual(len(_by_type(change_set.specs, "ObjectType")), len(object_types))
        self.assertEqual(len(_by_type(change_set.specs, "RelationshipType")), len(relationship_types))
        self.assertEqual(len(_by_type(change_set.specs, "AttributeDefinition")), expected_attribute_count)
        self.assertEqual(len(_by_type(change_set.specs, "RelationshipTypeRule")), expected_rule_count)
        self.assertEqual(len(_by_type(change_set.specs, "Object")), len(objects))
        self.assertEqual(len(_by_type(change_set.specs, "Relationship")), len(relationships))

        self.assertEqual(len(change_set.object_type_ids), len(object_types))
        self.assertEqual(len(change_set.relationship_type_ids), len(relationship_types))

        for spec in change_set.specs:
            self.assertEqual(spec["operation"], "create")
            self.assertIsNotNone(spec["target_id"])
            self.assertIn("before", spec)
            self.assertIn("after", spec)

    def test_delivery_project(self):
        self._assert_one_spec_per_definition(DELIVERY_PROJECT_TEMPLATE)

    def test_business_process(self):
        self._assert_one_spec_per_definition(BUSINESS_PROCESS_TEMPLATE)

    def test_object_type_creates_use_model_as_parent(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        for spec in _by_type(change_set.specs, "ObjectType"):
            self.assertEqual(spec["parent_type"], "Model")
            self.assertEqual(spec["parent_id"], MODEL_ID)

    def test_relationship_type_creates_use_model_as_parent(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        for spec in _by_type(change_set.specs, "RelationshipType"):
            self.assertEqual(spec["parent_type"], "Model")
            self.assertEqual(spec["parent_id"], MODEL_ID)

    def test_attribute_definitions_reference_their_types_pre_generated_id(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        object_type_uuids = set(change_set.object_type_ids.values())
        relationship_type_uuids = set(change_set.relationship_type_ids.values())

        for spec in _by_type(change_set.specs, "AttributeDefinition"):
            self.assertIn(spec["parent_type"], ("ObjectType", "RelationshipType"))
            if spec["parent_type"] == "ObjectType":
                self.assertIn(spec["parent_id"], object_type_uuids)
            else:
                self.assertIn(spec["parent_id"], relationship_type_uuids)

    def test_object_creates_carry_their_template_defined_key(self):
        # model.services.model_template keeps its own hand-authored slugs
        # as the real Object.key (developer-authored, not user input --
        # see model/services/keys.py's module docstring).
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        definitions_by_key = {
            definition["key"]: definition for definition in DELIVERY_PROJECT_TEMPLATE["objects"]
        }
        object_specs = _by_type(change_set.specs, "Object")
        self.assertEqual(len(object_specs), len(definitions_by_key))

        seen_keys = set()
        for spec in object_specs:
            key = spec["after"]["key"]
            self.assertIn(key, definitions_by_key)
            self.assertEqual(spec["after"]["name"], definitions_by_key[key]["name"])
            seen_keys.add(key)

        self.assertEqual(seen_keys, set(definitions_by_key))

    def test_rules_resolve_subject_and_object_type_ids(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        known_ids = {str(value) for value in change_set.object_type_ids.values()}
        relationship_type_uuids = set(change_set.relationship_type_ids.values())

        for spec in _by_type(change_set.specs, "RelationshipTypeRule"):
            self.assertIn(spec["after"]["subject_type_id"], known_ids)
            self.assertIn(spec["after"]["object_type_id"], known_ids)
            self.assertIn(spec["parent_id"], relationship_type_uuids)

    def test_objects_reference_their_object_types_pre_generated_id(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        object_type_uuids = set(change_set.object_type_ids.values())

        for spec in _by_type(change_set.specs, "Object"):
            self.assertEqual(spec["parent_type"], "ObjectType")
            self.assertIn(spec["parent_id"], object_type_uuids)

    def test_relationships_reference_known_objects_and_relationship_type(self):
        change_set = build_template_changes(DELIVERY_PROJECT_TEMPLATE, MODEL_ID)

        object_ids = {str(spec["target_id"]) for spec in _by_type(change_set.specs, "Object")}
        relationship_type_uuids = set(change_set.relationship_type_ids.values())

        for spec in _by_type(change_set.specs, "Relationship"):
            self.assertEqual(spec["parent_type"], "RelationshipType")
            self.assertIn(spec["parent_id"], relationship_type_uuids)
            self.assertIn(spec["after"]["subject_id"], object_ids)
            self.assertIn(spec["after"]["object_id"], object_ids)


class BuildTemplateChangesErrorTests(SimpleTestCase):

    def test_duplicate_object_type_key_raises(self):
        template = {
            "object_types": [
                {"key": "a", "name": "A", "attributes": []},
                {"key": "a", "name": "A2", "attributes": []},
            ],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_duplicate_relationship_type_key_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "relationship_types": [
                {"key": "r", "name": "R", "rules": []},
                {"key": "r", "name": "R2", "rules": []},
            ],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_rule_referencing_unknown_object_type_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "relationship_types": [
                {
                    "key": "r",
                    "name": "R",
                    "rules": [
                        {
                            "subject_type": "a",
                            "object_type": "missing",
                            "subject_minimum": 0,
                            "subject_maximum": None,
                            "object_minimum": 0,
                            "object_maximum": None,
                        },
                    ],
                },
            ],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_duplicate_object_key_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "objects": [
                {"key": "o1", "type": "a", "name": "One"},
                {"key": "o1", "type": "a", "name": "Two"},
            ],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_object_referencing_unknown_type_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "objects": [{"key": "o1", "type": "missing", "name": "One"}],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_relationship_referencing_unknown_relationship_type_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "objects": [
                {"key": "o1", "type": "a", "name": "One"},
                {"key": "o2", "type": "a", "name": "Two"},
            ],
            "relationships": [{"type": "missing", "subject": "o1", "object": "o2"}],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)

    def test_relationship_referencing_unknown_object_raises(self):
        template = {
            "object_types": [{"key": "a", "name": "A", "attributes": []}],
            "objects": [{"key": "o1", "type": "a", "name": "One"}],
            "relationship_types": [{"key": "r", "name": "R", "rules": []}],
            "relationships": [{"type": "r", "subject": "o1", "object": "missing"}],
        }

        with self.assertRaises(TemplateDefinitionError):
            build_template_changes(template, MODEL_ID)
