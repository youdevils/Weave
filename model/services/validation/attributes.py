from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal

from model.models.attribute_definition import AttributeDefinition
from model.services.validation.result import (
    ValidationIssue,
    ValidationResult,
)


def validate_attributes(
    attributes: Mapping,
    definitions,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    attribute_definitions = {definition.key: definition for definition in definitions}

    # ---------------------------------------------------------
    # Unknown attributes
    # ---------------------------------------------------------

    for key in attributes:
        if key not in attribute_definitions:
            issues.append(
                ValidationIssue(
                    code="unknown_attribute",
                    field=key,
                    message=(f"Attribute '{key}' is not defined for this type."),
                )
            )

    # ---------------------------------------------------------
    # Defined attributes
    # ---------------------------------------------------------

    for key, definition in attribute_definitions.items():

        if key not in attributes:
            if definition.required:
                issues.append(
                    ValidationIssue(
                        code="required_attribute",
                        field=key,
                        message=(f"Required attribute '{key}' is missing."),
                    )
                )

            continue

        issue = validate_attribute_value(
            definition=definition,
            value=attributes[key],
            field=key,
        )

        if issue is not None:
            issues.append(issue)

    return ValidationResult(issues=issues)


def validate_attribute_value(
    definition: AttributeDefinition,
    value,
    field: str | None = None,
) -> ValidationIssue | None:

    # ---------------------------------------------------------
    # Null handling
    # ---------------------------------------------------------

    if value is None:

        if definition.nullable:
            return None

        return ValidationIssue(
            code="null_not_allowed",
            field=field,
            message=(f"Attribute '{definition.key}' does not allow null values."),
        )

    # ---------------------------------------------------------
    # TEXT
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.TEXT:

        if not isinstance(value, str):
            return _type_issue(definition, field)

        config = definition.config or {}

        min_length = config.get("min_length")
        max_length = config.get("max_length")

        if min_length is not None and len(value) < min_length:
            return ValidationIssue(
                code="value_below_minimum",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must contain at least "
                    f"{min_length} characters."
                ),
            )

        if max_length is not None and len(value) > max_length:
            return ValidationIssue(
                code="value_above_maximum",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must contain no more "
                    f"than {max_length} characters."
                ),
            )

        return None

    # ---------------------------------------------------------
    # NUMBER
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.NUMBER:

        if not (
            isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
        ):
            return _type_issue(definition, field)

        config = definition.config or {}

        minimum = config.get("min")
        maximum = config.get("max")

        if minimum is not None and value < minimum:
            return ValidationIssue(
                code="value_below_minimum",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must be at least " f"{minimum}."
                ),
            )

        if maximum is not None and value > maximum:
            return ValidationIssue(
                code="value_above_maximum",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must be no greater "
                    f"than {maximum}."
                ),
            )

        return None

    # ---------------------------------------------------------
    # BOOLEAN
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.BOOLEAN:

        if not isinstance(value, bool):
            return _type_issue(definition, field)

        return None

    # ---------------------------------------------------------
    # DATE
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.DATE:

        if not isinstance(value, str):
            return _type_issue(definition, field)

        try:
            date.fromisoformat(value)
        except ValueError:
            return ValidationIssue(
                code="invalid_date",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must be a valid "
                    "ISO date in YYYY-MM-DD format."
                ),
            )

        return None

    # ---------------------------------------------------------
    # DATETIME
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.DATETIME:

        if not isinstance(value, str):
            return _type_issue(definition, field)

        try:
            datetime.fromisoformat(value)
        except ValueError:
            return ValidationIssue(
                code="invalid_datetime",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must be a valid "
                    "ISO-8601 datetime."
                ),
            )

        return None

    # ---------------------------------------------------------
    # CHOICE
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.CHOICE:

        if not isinstance(value, str):
            return _type_issue(definition, field)

        choices = (definition.config or {}).get("choices", [])

        if value not in choices:
            return ValidationIssue(
                code="invalid_choice",
                field=field,
                message=(
                    f"Attribute '{definition.key}' must be one of: "
                    f"{', '.join(choices)}."
                ),
            )

        return None

    # ---------------------------------------------------------
    # URL
    #
    # A URL is a semantic datatype stored as a plain string. Model
    # integrity only requires that it is a string: whether it is
    # well-formed, reachable or safe to link is not a model concern
    # (unsafe schemes are neutralised when rendered).
    # ---------------------------------------------------------

    if definition.data_type == AttributeDefinition.DataType.URL:

        if not isinstance(value, str):
            return _type_issue(definition, field)

        return None

    # ---------------------------------------------------------
    # Unsupported type
    # ---------------------------------------------------------

    return ValidationIssue(
        code="unsupported_attribute_type",
        field=field,
        message=(f"Attribute type '{definition.data_type}' is not supported."),
    )


def _type_issue(
    definition: AttributeDefinition,
    field: str | None,
) -> ValidationIssue:

    return ValidationIssue(
        code="invalid_attribute_type",
        field=field,
        message=(
            f"Attribute '{definition.key}' must be of type "
            f"{definition.get_data_type_display()}."
        ),
    )
