from django.test import TestCase

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType
from workspace.models import Workspace


class AttributeDefinitionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(
            name="Test Workspace",
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
        )

        cls.object_type = ObjectType.objects.create(
            model=cls.model,
            name="Test Object",
            key="test_object",
        )

        cls.second_object_type = ObjectType.objects.create(
            model=cls.model,
            name="Second Object",
            key="second_object",
        )

        cls.relationship_type = RelationshipType.objects.create(
            model=cls.model,
            name="Test Relationship",
            key="test_relationship",
        )

    def _object_definition(self, **kwargs):
        defaults = {
            "object_type": self.object_type,
            "name": "Test Attribute",
            "key": "test_attribute",
            "data_type": AttributeDefinition.DataType.TEXT,
        }

        defaults.update(kwargs)

        return AttributeDefinition(**defaults)

    def _relationship_definition(self, **kwargs):
        defaults = {
            "relationship_type": self.relationship_type,
            "name": "Test Attribute",
            "key": "test_attribute",
            "data_type": AttributeDefinition.DataType.TEXT,
        }

        defaults.update(kwargs)

        return AttributeDefinition(**defaults)

    # ---------------------------------------------------------
    # Ownership
    # ---------------------------------------------------------

    def test_definition_requires_exactly_one_owner(self):
        definition = AttributeDefinition(
            name="Test Attribute",
            key="test_attribute",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_definition_cannot_have_both_owners(self):
        definition = AttributeDefinition(
            object_type=self.object_type,
            relationship_type=self.relationship_type,
            name="Test Attribute",
            key="test_attribute",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_object_type_definition_is_valid_owner_configuration(self):
        definition = self._object_definition()

        definition.full_clean()

    def test_relationship_type_definition_is_valid_owner_configuration(self):
        definition = self._relationship_definition()

        definition.full_clean()

    # ---------------------------------------------------------
    # TEXT configuration
    # ---------------------------------------------------------

    def test_text_config_allows_min_length(self):
        definition = self._object_definition(
            config={"min_length": 3},
        )

        definition.full_clean()

    def test_text_config_allows_max_length(self):
        definition = self._object_definition(
            config={"max_length": 100},
        )

        definition.full_clean()

    def test_text_config_rejects_unknown_keys(self):
        definition = self._object_definition(
            config={"pattern": "^[A-Z]+$"},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_text_config_rejects_negative_min_length(self):
        definition = self._object_definition(
            config={"min_length": -1},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_text_config_rejects_negative_max_length(self):
        definition = self._object_definition(
            config={"max_length": -1},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_text_config_rejects_min_greater_than_max(self):
        definition = self._object_definition(
            config={
                "min_length": 10,
                "max_length": 5,
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    # ---------------------------------------------------------
    # NUMBER configuration
    # ---------------------------------------------------------

    def test_number_config_accepts_numeric_limits(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "min": 0,
                "max": 100,
            },
        )

        definition.full_clean()

    def test_number_config_rejects_non_numeric_min(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "min": "zero",
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_number_config_rejects_non_numeric_max(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "max": "one hundred",
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_number_config_rejects_min_greater_than_max(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "min": 100,
                "max": 10,
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_number_config_rejects_unknown_keys(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "precision": 2,
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    # ---------------------------------------------------------
    # BOOLEAN / DATE / DATETIME configuration
    # ---------------------------------------------------------

    def test_boolean_config_must_be_empty(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.BOOLEAN,
            config={"something": True},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_date_config_must_be_empty(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.DATE,
            config={"something": True},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_datetime_config_must_be_empty(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.DATETIME,
            config={"something": True},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    # ---------------------------------------------------------
    # CHOICE configuration
    # ---------------------------------------------------------

    def test_choice_requires_choices(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={},
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_choice_accepts_valid_choices(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "green"],
            },
        )

        definition.full_clean()

    def test_choice_rejects_empty_choices(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": [],
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_choice_rejects_non_string_choices(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", 2, "green"],
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_choice_rejects_duplicate_choices(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "red"],
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_choice_rejects_unknown_config_keys(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "green"],
                "multiple": True,
            },
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    # ---------------------------------------------------------
    # Default values
    # ---------------------------------------------------------

    def test_text_default_must_match_type(self):
        definition = self._object_definition(
            default_value="active",
        )

        definition.full_clean()

    def test_number_default_must_match_type(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            default_value=5,
        )

        definition.full_clean()

    def test_boolean_default_must_match_type(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.BOOLEAN,
            default_value=True,
        )

        definition.full_clean()

    def test_invalid_default_type_is_rejected(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            default_value="high",
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_default_must_respect_number_limits(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "min": 1,
                "max": 5,
            },
            default_value=10,
        )

        with self.assertRaises(Exception):
            definition.full_clean()

    def test_default_must_be_valid_choice(self):
        definition = self._object_definition(
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "green"],
            },
            default_value="blue",
        )

        with self.assertRaises(Exception):
            definition.full_clean()
