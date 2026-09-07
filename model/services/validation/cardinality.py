from collections import defaultdict

from model.models.model import Model
from model.models.object import Object
from model.models.relationship import Relationship
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.result import (
    ValidationIssue,
    ValidationResult,
)


def validate_cardinality(
    model: Model,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    # ---------------------------------------------------------
    # Relationship type rules
    # ---------------------------------------------------------

    rules = RelationshipTypeRule.objects.filter(
        relationship_type__model=model,
    ).select_related(
        "relationship_type",
        "subject_type",
        "object_type",
    )

    for rule in rules:

        # -----------------------------------------------------
        # Find active relationships matching this rule
        # -----------------------------------------------------

        relationships = Relationship.objects.filter(
            model=model,
            is_active=True,
            relationship_type_id=rule.relationship_type_id,
            subject__object_type_id=rule.subject_type_id,
            object__object_type_id=rule.object_type_id,
        )

        # -----------------------------------------------------
        # Count relationships
        #
        # object_counts:
        #   number of target objects for each subject
        #
        # subject_counts:
        #   number of source subjects for each object
        # -----------------------------------------------------

        object_counts: dict = defaultdict(int)
        subject_counts: dict = defaultdict(int)

        for relationship in relationships:
            object_counts[relationship.subject_id] += 1
            subject_counts[relationship.object_id] += 1

        # -----------------------------------------------------
        # Object cardinality
        #
        # For each subject:
        #   object_minimum / maximum determine how many
        #   objects it may or must have.
        # -----------------------------------------------------

        subjects = Object.objects.filter(
            model=model,
            is_active=True,
            object_type_id=rule.subject_type_id,
        )

        for subject in subjects:
            count = object_counts[subject.id]

            if rule.object_required and count == 0:
                issues.append(
                    ValidationIssue(
                        code="object_required",
                        field="object",
                        message=(
                            f"Object '{subject.name}' must have at least "
                            f"one '{rule.relationship_type.name}' "
                            f"relationship to a "
                            f"'{rule.object_type.name}'."
                        ),
                    )
                )

            if count < rule.object_minimum:
                issues.append(
                    ValidationIssue(
                        code="object_cardinality_minimum",
                        field="object",
                        message=(
                            f"Object '{subject.name}' has {count} "
                            f"'{rule.relationship_type.name}' "
                            f"relationship(s), but the minimum is "
                            f"{rule.object_minimum}."
                        ),
                    )
                )

            if rule.object_maximum is not None and count > rule.object_maximum:
                issues.append(
                    ValidationIssue(
                        code="object_cardinality_maximum",
                        field="object",
                        message=(
                            f"Object '{subject.name}' has {count} "
                            f"'{rule.relationship_type.name}' "
                            f"relationship(s), but the maximum is "
                            f"{rule.object_maximum}."
                        ),
                    )
                )

        # -----------------------------------------------------
        # Subject cardinality
        #
        # For each object:
        #   subject_minimum / maximum determine how many
        #   subjects it may or must have.
        # -----------------------------------------------------

        objects = Object.objects.filter(
            model=model,
            is_active=True,
            object_type_id=rule.object_type_id,
        )

        for object_ in objects:
            count = subject_counts[object_.id]

            if rule.subject_required and count == 0:
                issues.append(
                    ValidationIssue(
                        code="subject_required",
                        field="subject",
                        message=(
                            f"Object '{object_.name}' must have at least "
                            f"one '{rule.relationship_type.name}' "
                            f"relationship from a "
                            f"'{rule.subject_type.name}'."
                        ),
                    )
                )

            if count < rule.subject_minimum:
                issues.append(
                    ValidationIssue(
                        code="subject_cardinality_minimum",
                        field="subject",
                        message=(
                            f"Object '{object_.name}' has {count} "
                            f"'{rule.relationship_type.name}' "
                            f"relationship(s) from "
                            f"'{rule.subject_type.name}', but the minimum "
                            f"is {rule.subject_minimum}."
                        ),
                    )
                )

            if rule.subject_maximum is not None and count > rule.subject_maximum:
                issues.append(
                    ValidationIssue(
                        code="subject_cardinality_maximum",
                        field="subject",
                        message=(
                            f"Object '{object_.name}' has {count} "
                            f"'{rule.relationship_type.name}' "
                            f"relationship(s) from "
                            f"'{rule.subject_type.name}', but the maximum "
                            f"is {rule.subject_maximum}."
                        ),
                    )
                )

    return ValidationResult(issues=issues)
