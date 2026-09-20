from model.models.relationship import Relationship
from model.services.validation.attributes import validate_attributes
from model.services.validation.fields import validate_relationship_builtin_fields
from model.services.validation.result import (
    ValidationIssue,
    ValidationResult,
)


def validate_relationship(
    relationship: Relationship,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    # ---------------------------------------------------------
    # Model consistency
    # ---------------------------------------------------------

    if relationship.relationship_type.model_id != relationship.model_id:
        issues.append(
            ValidationIssue(
                code="relationship_type_model_mismatch",
                field="relationship_type",
                message=(
                    f"RelationshipType "
                    f"'{relationship.relationship_type.name}' does not "
                    "belong to the same Model as the Relationship."
                ),
                target_type="Relationship",
                target_id=relationship.id,
            )
        )

    if relationship.subject.model_id != relationship.model_id:
        issues.append(
            ValidationIssue(
                code="subject_model_mismatch",
                field="subject",
                message=(
                    f"Subject Object '{relationship.subject.name}' does not "
                    "belong to the same Model as the Relationship."
                ),
                target_type="Relationship",
                target_id=relationship.id,
            )
        )

    if relationship.object.model_id != relationship.model_id:
        issues.append(
            ValidationIssue(
                code="object_model_mismatch",
                field="object",
                message=(
                    f"Object '{relationship.object.name}' does not belong "
                    "to the same Model as the Relationship."
                ),
                target_type="Relationship",
                target_id=relationship.id,
            )
        )

    # ---------------------------------------------------------
    # Relationship type model consistency
    # ---------------------------------------------------------

    # Only check relationship rules when the relationship type belongs
    # to the same model. Otherwise this can produce misleading errors
    # about a rule that belongs to another model.
    if relationship.relationship_type.model_id == relationship.model_id:

        matching_rule = relationship.relationship_type.rules.filter(
            subject_type_id=relationship.subject.object_type_id,
            object_type_id=relationship.object.object_type_id,
        ).exists()

        if not matching_rule:
            issues.append(
                ValidationIssue(
                    code="invalid_relationship_types",
                    field="relationship_type",
                    message=(
                        f"RelationshipType "
                        f"'{relationship.relationship_type.name}' does not "
                        f"permit '{relationship.subject.object_type.name}' "
                        f"as the subject and "
                        f"'{relationship.object.object_type.name}' "
                        "as the object."
                    ),
                    target_type="Relationship",
                    target_id=relationship.id,
                )
            )

    # ---------------------------------------------------------
    # Built-in fields
    # ---------------------------------------------------------

    for issue in validate_relationship_builtin_fields(is_active=relationship.is_active):
        issue.target_type = "Relationship"
        issue.target_id = relationship.id
        issues.append(issue)

    # ---------------------------------------------------------
    # Relationship attributes
    # ---------------------------------------------------------

    definitions = relationship.relationship_type.relationship_definitions.all()

    attribute_result = validate_attributes(
        attributes=relationship.attributes or {},
        definitions=definitions,
    )

    for issue in attribute_result.issues:
        issue.target_type = "Relationship"
        issue.target_id = relationship.id

    issues.extend(attribute_result.issues)

    return ValidationResult(issues=issues)
