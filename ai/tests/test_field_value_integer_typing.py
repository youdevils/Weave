from django.test import SimpleTestCase

from ai.services.change_plan import FieldValue


class FieldValueIntegerTypingTests(SimpleTestCase):
    """
    Regression coverage for the cardinality-renders-as-float bug: a clean
    integer passed into FieldValue.of() must come back out of .native() as a
    real int, not a float, since FieldValue.number_value is the single
    channel every AI-supplied numeric value (including RelationshipTypeRule
    cardinalities) flows through on its way into ProposalChange.after/before.
    """

    def test_representative_integers_stay_integers(self):
        for value in (0, 1, 2, 8, 10):
            with self.subTest(value=value):
                field_value = FieldValue.of(value)
                self.assertEqual(field_value.number_value, value)
                self.assertIsInstance(field_value.number_value, int)
                self.assertEqual(field_value.native(), value)
                self.assertIsInstance(field_value.native(), int)

    def test_fractional_values_stay_float(self):
        field_value = FieldValue.of(1.5)
        self.assertEqual(field_value.number_value, 1.5)
        self.assertIsInstance(field_value.number_value, float)
        self.assertIsInstance(field_value.native(), float)

    def test_round_trip_through_json_preserves_integer_type(self):
        for value in (0, 1, 2, 8, 10):
            with self.subTest(value=value):
                dumped = FieldValue.of(value).model_dump_json()
                restored = FieldValue.model_validate_json(dumped)
                self.assertIsInstance(restored.number_value, int)
                self.assertEqual(restored.native(), value)
