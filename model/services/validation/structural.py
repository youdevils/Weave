from django.core.exceptions import ValidationError as DjangoValidationError

from model.models.attribute_definition import AttributeDefinition
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.result import ValidationIssue, ValidationResult


def _issues_from_django_error(
    exc: DjangoValidationError,
    target_type: str,
    target_id,
) -> list[ValidationIssue]:
    issues = []

    if hasattr(exc, "error_dict"):
        for field, field_errors in exc.error_dict.items():
            field_name = None if field == "__all__" else field
            for error in field_errors:
                issues.append(
                    ValidationIssue(
                        code="structural_invalid",
                        field=field_name,
                        message=error.message % (error.params or {}),
                        target_type=target_type,
                        target_id=target_id,
                    )
                )
    else:
        for error in exc.error_list:
            issues.append(
                ValidationIssue(
                    code="structural_invalid",
                    message=error.message % (error.params or {}),
                    target_type=target_type,
                    target_id=target_id,
                )
            )

    return issues


def validate_attribute_definition(
    definition: AttributeDefinition,
) -> ValidationResult:
    try:
        definition.full_clean()

    except DjangoValidationError as exc:
        return ValidationResult(
            issues=_issues_from_django_error(
                exc,
                target_type="AttributeDefinition",
                target_id=definition.id,
            )
        )

    return ValidationResult(issues=[])


def validate_relationship_type_rule(
    rule: RelationshipTypeRule,
) -> ValidationResult:
    try:
        rule.full_clean()

    except DjangoValidationError as exc:
        return ValidationResult(
            issues=_issues_from_django_error(
                exc,
                target_type="RelationshipTypeRule",
                target_id=rule.id,
            )
        )

    return ValidationResult(issues=[])
