from django.test import SimpleTestCase

from ingestion.services.coercion import coerce_attribute_cell, format_cell, format_is_active_cell
from model.models.attribute_definition import AttributeDefinition

DataType = AttributeDefinition.DataType


class FormatCellRoundTripTests(SimpleTestCase):
    """
    format_cell is the inverse of coerce_attribute_cell: for every value the
    coercer actually produces, formatting it and coercing the result back
    must reproduce the original value exactly -- the property the "download
    with current data" template relies on for a clean re-import.
    """

    def assertRoundTrips(self, data_type, value):
        cell = format_cell(data_type, value)
        self.assertEqual(coerce_attribute_cell(data_type, cell).value, value)

    def test_none_formats_as_a_blank_cell(self):
        for data_type in (DataType.TEXT, DataType.NUMBER, DataType.BOOLEAN, DataType.DATE, DataType.CHOICE):
            self.assertEqual(format_cell(data_type, None), "")

        self.assertRoundTrips(DataType.TEXT, None)

    def test_text_url_and_choice_round_trip_unchanged(self):
        self.assertRoundTrips(DataType.TEXT, "Finance")
        self.assertRoundTrips(DataType.URL, "https://example.com")
        self.assertRoundTrips(DataType.CHOICE, "gold")

    def test_numbers_round_trip_as_themselves(self):
        self.assertRoundTrips(DataType.NUMBER, 1200)
        self.assertRoundTrips(DataType.NUMBER, 12.5)
        self.assertRoundTrips(DataType.NUMBER, 0)

    def test_booleans_format_as_lowercase_text(self):
        self.assertEqual(format_cell(DataType.BOOLEAN, True), "true")
        self.assertEqual(format_cell(DataType.BOOLEAN, False), "false")
        self.assertRoundTrips(DataType.BOOLEAN, True)
        self.assertRoundTrips(DataType.BOOLEAN, False)

    def test_date_and_datetime_round_trip_the_stored_iso_string_unchanged(self):
        self.assertRoundTrips(DataType.DATE, "2024-01-01")
        self.assertRoundTrips(DataType.DATETIME, "2024-01-01T10:00:00")

    def test_is_active_formats_as_lowercase_text(self):
        self.assertEqual(format_is_active_cell(True), "true")
        self.assertEqual(format_is_active_cell(False), "false")
