from django.test import SimpleTestCase

from model.models.attribute_definition import AttributeDefinition
from model.services import coercion
from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX, attribute_field_name
from model.views import data_context

DataType = AttributeDefinition.DataType


class CoerceAttributeValueTests(SimpleTestCase):

    def test_blank_is_none(self):
        for blank in (None, "", "   "):
            self.assertIsNone(coercion.coerce_attribute_value(DataType.TEXT, blank))

    def test_numbers(self):
        self.assertEqual(coercion.coerce_attribute_value(DataType.NUMBER, " 42 "), 42)
        self.assertEqual(coercion.coerce_attribute_value(DataType.NUMBER, "1.5"), 1.5)

        with self.assertRaises(ValueError):
            coercion.coerce_attribute_value(DataType.NUMBER, "abc")

    def test_booleans(self):
        for text in ("true", "YES", "1", "on"):
            self.assertIs(coercion.coerce_attribute_value(DataType.BOOLEAN, text), True)

        for text in ("false", "No", "0", "off"):
            self.assertIs(coercion.coerce_attribute_value(DataType.BOOLEAN, text), False)

        with self.assertRaises(ValueError):
            coercion.coerce_attribute_value(DataType.BOOLEAN, "maybe")

    def test_other_types_are_trimmed_text(self):
        self.assertEqual(coercion.coerce_attribute_value(DataType.TEXT, "  hi  "), "hi")
        self.assertEqual(coercion.coerce_attribute_value(DataType.CHOICE, "gold"), "gold")


class ExistingImportersKeepWorkingTests(SimpleTestCase):
    """The editors and the model graph import these names from data_context."""

    def test_data_context_reexports_the_moved_helpers(self):
        self.assertIs(data_context.coerce_attribute_value, coercion.coerce_attribute_value)
        self.assertEqual(data_context.ATTRIBUTE_FIELD_PREFIX, ATTRIBUTE_FIELD_PREFIX)
        self.assertIs(data_context.attribute_field_name, attribute_field_name)
        self.assertEqual(attribute_field_name("owner"), "attributes.owner")
