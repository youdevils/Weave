"""
Validation of the built-in (non-attribute) fields of Objects and Relationships.

`validate_attributes` covers the `attributes` blob; these rules cover what
lives outside it: an Object's name / description / is_active and a
Relationship's is_active. They are checked in two places, by the same code:

  * `validate_object` / `validate_relationship`, against stored state; and
  * the proposal apply step, against a change's *proposed* value before it is
    written, so a bad value is reported as an issue instead of surfacing as a
    database error part-way through applying a proposal.

Every writer of these fields (the record editors, Data Import, AI ingestion)
relies on this one implementation.
"""

from model.models.object import Object
from model.services.validation.result import ValidationIssue

NAME_MAX_LENGTH = Object._meta.get_field("name").max_length

OBJECT_BUILTIN_FIELDS = ("name", "description", "is_active")
RELATIONSHIP_BUILTIN_FIELDS = ("is_active",)

# A Relationship's endpoints, addressed by a field-level UPDATE exactly as
# they are keyed in a Relationship CREATE payload. Whether the referenced
# Object exists (and belongs to the model) needs the database, so it is
# checked by the proposal apply step; whether the resulting subject/object
# type pair is permitted is checked by validate_relationship.
RELATIONSHIP_ENDPOINT_FIELDS = ("subject_id", "object_id")


def validate_object_field(field, value) -> ValidationIssue | None:

    if field == "name":

        if not isinstance(value, str):
            return ValidationIssue(
                code="invalid_name",
                field="name",
                message="Name must be text.",
            )

        if not value.strip():
            return ValidationIssue(
                code="name_required",
                field="name",
                message="Name is required.",
            )

        if len(value) > NAME_MAX_LENGTH:
            return ValidationIssue(
                code="name_too_long",
                field="name",
                message=f"Name cannot exceed {NAME_MAX_LENGTH} characters.",
            )

        return None

    if field == "description":

        if not isinstance(value, str):
            return ValidationIssue(
                code="invalid_description",
                field="description",
                message="Description must be text.",
            )

        return None

    if field == "is_active":
        return _is_active_issue(value)

    return None


def validate_relationship_field(field, value) -> ValidationIssue | None:

    if field == "is_active":
        return _is_active_issue(value)

    return None


def validate_object_builtin_fields(*, name, description, is_active) -> list[ValidationIssue]:

    values = {
        "name": name,
        "description": description,
        "is_active": is_active,
    }

    issues = [validate_object_field(field, value) for field, value in values.items()]

    return [issue for issue in issues if issue is not None]


def validate_relationship_builtin_fields(*, is_active) -> list[ValidationIssue]:

    issue = validate_relationship_field("is_active", is_active)

    return [issue] if issue is not None else []


def _is_active_issue(value) -> ValidationIssue | None:

    if isinstance(value, bool):
        return None

    return ValidationIssue(
        code="invalid_is_active",
        field="is_active",
        message="Active must be true or false.",
    )
