from model.models.object import Object
from model.services.validation.attributes import validate_attributes
from model.services.validation.result import (
    ValidationIssue,
    ValidationResult,
)


def validate_object(obj: Object) -> ValidationResult:
    issues: list[ValidationIssue] = []

    # ---------------------------------------------------------
    # Model consistency
    # ---------------------------------------------------------

    if obj.object_type.model_id != obj.model_id:
        issues.append(
            ValidationIssue(
                code="object_type_model_mismatch",
                field="object_type",
                message=(
                    f"ObjectType '{obj.object_type.name}' does not belong "
                    f"to the same Model as the Object."
                ),
                target_type="Object",
                target_id=obj.id,
            )
        )

    # ---------------------------------------------------------
    # Attribute validation
    # ---------------------------------------------------------

    definitions = obj.object_type.attribute_definitions.all()

    attribute_result = validate_attributes(
        attributes=obj.attributes or {},
        definitions=definitions,
    )

    for issue in attribute_result.issues:
        issue.target_type = "Object"
        issue.target_id = obj.id

    issues.extend(attribute_result.issues)

    return ValidationResult(issues=issues)
