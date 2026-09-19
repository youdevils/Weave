from django.test import SimpleTestCase

from model.models.attribute_definition import AttributeDefinition
from model.services.validation.attributes import (
    validate_attribute_value,
    validate_attributes,
)


class AttributeValidationTests(SimpleTestCase):

    def test_valid_attributes(self):
        definitions = [
            AttributeDefinition(
                key="name",
                name="Name",
                data_type=AttributeDefinition.DataType.TEXT,
                required=True,
            ),
            AttributeDefinition(
                key="criticality",
                name="Criticality",
                data_type=AttributeDefinition.DataType.NUMBER,
            ),
            AttributeDefinition(
                key="active",
                name="Active",
                data_type=AttributeDefinition.DataType.BOOLEAN,
            ),
        ]

        result = validate_attributes(
            {
                "name": "Gateway X",
                "criticality": 5,
                "active": True,
            },
            definitions,
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    def test_url_attribute_accepts_any_string_value(self):
        definition = AttributeDefinition(
            key="website",
            name="Website",
            data_type=AttributeDefinition.DataType.URL,
        )

        # Model integrity only requires a string. Format, scheme and
        # reachability are not the validator's concern.
        for value in (
            "https://example.com/docs",
            "not a url",
            "javascript:alert(1)",
            "//relative/path",
            "",
        ):
            with self.subTest(value=value):
                self.assertIsNone(
                    validate_attribute_value(definition, value, "website"),
                )

        result = validate_attributes({"website": "not a url"}, [definition])
        self.assertTrue(result.valid)

    def test_url_attribute_rejects_non_string_values(self):
        definition = AttributeDefinition(
            key="website",
            name="Website",
            data_type=AttributeDefinition.DataType.URL,
        )

        for value in (42, True, ["https://example.com"], {"url": "x"}):
            with self.subTest(value=value):
                issue = validate_attribute_value(definition, value, "website")
                self.assertEqual(issue.code, "invalid_attribute_type")

    def test_url_attribute_null_handling_follows_nullable(self):
        strict = AttributeDefinition(
            key="website", name="Website", data_type=AttributeDefinition.DataType.URL
        )
        nullable = AttributeDefinition(
            key="website",
            name="Website",
            data_type=AttributeDefinition.DataType.URL,
            nullable=True,
        )

        self.assertEqual(
            validate_attribute_value(strict, None, "website").code,
            "null_not_allowed",
        )
        self.assertIsNone(validate_attribute_value(nullable, None, "website"))

    def test_text_attribute_is_unaffected_by_url_support(self):
        definition = AttributeDefinition(
            key="notes", name="Notes", data_type=AttributeDefinition.DataType.TEXT
        )

        self.assertIsNone(
            validate_attribute_value(definition, "https://example.com", "notes")
        )
        self.assertEqual(
            validate_attribute_value(definition, 42, "notes").code,
            "invalid_attribute_type",
        )

    def test_unknown_attribute(self):
        definitions = [
            AttributeDefinition(
                key="name",
                name="Name",
                data_type=AttributeDefinition.DataType.TEXT,
            )
        ]

        result = validate_attributes(
            {
                "name": "Gateway X",
                "banana": "something",
            },
            definitions,
        )

        self.assertFalse(result.valid)
        self.assertEqual(
            result.issues[0].code,
            "unknown_attribute",
        )

    def test_required_attribute_missing(self):
        definitions = [
            AttributeDefinition(
                key="name",
                name="Name",
                data_type=AttributeDefinition.DataType.TEXT,
                required=True,
            )
        ]

        result = validate_attributes({}, definitions)

        self.assertFalse(result.valid)
        self.assertEqual(
            result.issues[0].code,
            "required_attribute",
        )

    def test_optional_attribute_missing_is_valid(self):
        definitions = [
            AttributeDefinition(
                key="name",
                name="Name",
                data_type=AttributeDefinition.DataType.TEXT,
            )
        ]

        result = validate_attributes({}, definitions)

        self.assertTrue(result.valid)

    def test_invalid_number(self):
        definition = AttributeDefinition(
            key="criticality",
            name="Criticality",
            data_type=AttributeDefinition.DataType.NUMBER,
        )

        issue = validate_attribute_value(
            definition,
            "high",
            "criticality",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_attribute_type",
        )

    def test_boolean_is_not_a_number(self):
        definition = AttributeDefinition(
            key="criticality",
            name="Criticality",
            data_type=AttributeDefinition.DataType.NUMBER,
        )

        issue = validate_attribute_value(
            definition,
            True,
            "criticality",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_attribute_type",
        )

    def test_valid_boolean(self):
        definition = AttributeDefinition(
            key="active",
            name="Active",
            data_type=AttributeDefinition.DataType.BOOLEAN,
        )

        issue = validate_attribute_value(
            definition,
            True,
            "active",
        )

        self.assertIsNone(issue)

    def test_invalid_boolean(self):
        definition = AttributeDefinition(
            key="active",
            name="Active",
            data_type=AttributeDefinition.DataType.BOOLEAN,
        )

        issue = validate_attribute_value(
            definition,
            "true",
            "active",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_attribute_type",
        )

    def test_valid_date(self):
        definition = AttributeDefinition(
            key="retirement_date",
            name="Retirement date",
            data_type=AttributeDefinition.DataType.DATE,
        )

        issue = validate_attribute_value(
            definition,
            "2027-12-31",
            "retirement_date",
        )

        self.assertIsNone(issue)

    def test_invalid_date(self):
        definition = AttributeDefinition(
            key="retirement_date",
            name="Retirement date",
            data_type=AttributeDefinition.DataType.DATE,
        )

        issue = validate_attribute_value(
            definition,
            "31/12/2027",
            "retirement_date",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_date",
        )

    def test_valid_datetime(self):
        definition = AttributeDefinition(
            key="last_reviewed",
            name="Last reviewed",
            data_type=AttributeDefinition.DataType.DATETIME,
        )

        issue = validate_attribute_value(
            definition,
            "2026-09-07T11:30:00+12:00",
            "last_reviewed",
        )

        self.assertIsNone(issue)

    def test_invalid_datetime(self):
        definition = AttributeDefinition(
            key="last_reviewed",
            name="Last reviewed",
            data_type=AttributeDefinition.DataType.DATETIME,
        )

        issue = validate_attribute_value(
            definition,
            "yesterday",
            "last_reviewed",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_datetime",
        )

    def test_valid_choice(self):
        definition = AttributeDefinition(
            key="status",
            name="Status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "green"],
            },
        )

        issue = validate_attribute_value(
            definition,
            "green",
            "status",
        )

        self.assertIsNone(issue)

    def test_invalid_choice(self):
        definition = AttributeDefinition(
            key="status",
            name="Status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={
                "choices": ["red", "amber", "green"],
            },
        )

        issue = validate_attribute_value(
            definition,
            "blue",
            "status",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "invalid_choice",
        )

    def test_nullable_allows_none(self):
        definition = AttributeDefinition(
            key="vendor",
            name="Vendor",
            data_type=AttributeDefinition.DataType.TEXT,
            nullable=True,
        )

        issue = validate_attribute_value(
            definition,
            None,
            "vendor",
        )

        self.assertIsNone(issue)

    def test_non_nullable_rejects_none(self):
        definition = AttributeDefinition(
            key="vendor",
            name="Vendor",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        issue = validate_attribute_value(
            definition,
            None,
            "vendor",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "null_not_allowed",
        )

    def test_text_min_length(self):
        definition = AttributeDefinition(
            key="name",
            name="Name",
            data_type=AttributeDefinition.DataType.TEXT,
            config={
                "min_length": 3,
            },
        )

        issue = validate_attribute_value(
            definition,
            "AB",
            "name",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "value_below_minimum",
        )

    def test_text_max_length(self):
        definition = AttributeDefinition(
            key="name",
            name="Name",
            data_type=AttributeDefinition.DataType.TEXT,
            config={
                "max_length": 5,
            },
        )

        issue = validate_attribute_value(
            definition,
            "TooLong",
            "name",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "value_above_maximum",
        )

    def test_number_minimum(self):
        definition = AttributeDefinition(
            key="criticality",
            name="Criticality",
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "min": 1,
            },
        )

        issue = validate_attribute_value(
            definition,
            0,
            "criticality",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "value_below_minimum",
        )

    def test_number_maximum(self):
        definition = AttributeDefinition(
            key="criticality",
            name="Criticality",
            data_type=AttributeDefinition.DataType.NUMBER,
            config={
                "max": 5,
            },
        )

        issue = validate_attribute_value(
            definition,
            6,
            "criticality",
        )

        self.assertIsNotNone(issue)
        self.assertEqual(
            issue.code,
            "value_above_maximum",
        )
