from django.test import SimpleTestCase

from model.services import entity_fields


class IllegalFieldsTests(SimpleTestCase):

    def test_relationship_type_rejects_endpoint_fields(self):
        """
        The exact reproduction of the original bug: RelationshipType has
        no subject/object fields at all -- those live on a separate
        RelationshipTypeRule entity.
        """
        self.assertEqual(
            entity_fields.illegal_fields("RelationshipType", ["to", "from"]),
            ["to", "from"],
        )

    def test_relationship_type_accepts_its_real_fields(self):
        self.assertEqual(
            entity_fields.illegal_fields("RelationshipType", ["name", "key", "description", "sort_order", "is_active"]),
            [],
        )

    def test_object_type_rejects_unknown_field(self):
        self.assertEqual(entity_fields.illegal_fields("ObjectType", ["bogus"]), ["bogus"])

    def test_object_type_accepts_its_real_fields(self):
        self.assertEqual(
            entity_fields.illegal_fields("ObjectType", ["name", "key", "description", "sort_order", "is_active"]),
            [],
        )

    def test_attribute_definition_accepts_its_real_fields(self):
        self.assertEqual(
            entity_fields.illegal_fields(
                "AttributeDefinition",
                ["name", "key", "data_type", "description", "required", "nullable",
                 "default_value", "sort_order", "config", "is_active"],
            ),
            [],
        )

    def test_relationship_type_rule_accepts_its_real_fields(self):
        self.assertEqual(
            entity_fields.illegal_fields(
                "RelationshipTypeRule",
                ["subject_type_id", "object_type_id", "subject_minimum",
                 "subject_maximum", "object_minimum", "object_maximum"],
            ),
            [],
        )

    def test_relationship_type_rule_has_no_name_or_key(self):
        self.assertEqual(
            entity_fields.illegal_fields("RelationshipTypeRule", ["name", "key"]),
            ["name", "key"],
        )

    def test_object_accepts_attribute_prefixed_fields(self):
        self.assertEqual(
            entity_fields.illegal_fields("Object", ["name", "description", "is_active", "attributes.cost"]),
            [],
        )

    def test_object_has_no_key(self):
        self.assertEqual(entity_fields.illegal_fields("Object", ["key"]), ["key"])

    def test_relationship_accepts_its_real_fields_including_attributes_prefix(self):
        self.assertEqual(
            entity_fields.illegal_fields(
                "Relationship",
                ["subject_id", "object_id", "valid_from", "valid_to", "is_active", "attributes.note"],
            ),
            [],
        )

    def test_unknown_target_type_rejects_everything(self):
        self.assertEqual(entity_fields.illegal_fields("NotARealType", ["anything"]), ["anything"])

    def test_preserves_input_order(self):
        self.assertEqual(
            entity_fields.illegal_fields("RelationshipType", ["from", "name", "to"]),
            ["from", "to"],
        )
