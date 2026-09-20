"""
The import mapping: which source column feeds which canonical field.

    {"target": {"kind": "object", "type_id": "<uuid>"},
     "columns": [
        {"column": 0, "field": "attribute.app_id", "match": true},
        {"column": 1, "field": "field.name"},
        {"column": 2, "field": "attribute.owner"}]}

Relationship endpoints say how they are resolved:

        {"column": 3, "field": "endpoint.subject",
         "by": "attribute:app_id", "object_type_id": "<uuid>"}      (or "by": "id")

`ImportMapping.from_json` validates a payload against the canonical target and
returns an immutable, canonically ordered value that serialises back to the
same JSON. Columns are addressed by 0-based index, never by header text
(headers can be blank or repeated). Unlisted columns are simply unmapped.
"""

import uuid
from dataclasses import dataclass

from ingestion.services import limits
from ingestion.services.errors import MappingError
from ingestion.services.targets import OBJECT, RELATIONSHIP

IDENTITY_ID = "identity.id"
FIELD_NAME = "field.name"
FIELD_DESCRIPTION = "field.description"
FIELD_IS_ACTIVE = "field.is_active"
ENDPOINT_SUBJECT = "endpoint.subject"
ENDPOINT_OBJECT = "endpoint.object"
ATTRIBUTE_PREFIX = "attribute."

OBJECT_FIELDS = (IDENTITY_ID, FIELD_NAME, FIELD_DESCRIPTION, FIELD_IS_ACTIVE)
RELATIONSHIP_FIELDS = (IDENTITY_ID, ENDPOINT_SUBJECT, ENDPOINT_OBJECT, FIELD_IS_ACTIVE)

BUILTIN_FIELD_PATHS = {
    FIELD_NAME: "name",
    FIELD_DESCRIPTION: "description",
    FIELD_IS_ACTIVE: "is_active",
}

BY_ID = "id"
BY_ATTRIBUTE_PREFIX = "attribute:"


@dataclass(frozen=True)
class MappedColumn:
    column: int
    field: str
    match: bool = False
    by: str | None = None
    object_type_id: uuid.UUID | None = None

    @property
    def is_attribute(self) -> bool:
        return self.field.startswith(ATTRIBUTE_PREFIX)

    @property
    def attribute_key(self) -> str:
        return self.field[len(ATTRIBUTE_PREFIX):]

    @property
    def is_endpoint(self) -> bool:
        return self.field in (ENDPOINT_SUBJECT, ENDPOINT_OBJECT)

    @property
    def by_attribute_key(self):
        if self.by and self.by.startswith(BY_ATTRIBUTE_PREFIX):
            return self.by[len(BY_ATTRIBUTE_PREFIX):]

        return None

    def to_dict(self):
        data = {"column": self.column, "field": self.field}

        if self.match:
            data["match"] = True

        if self.by:
            data["by"] = self.by

        if self.object_type_id:
            data["object_type_id"] = str(self.object_type_id)

        return data


@dataclass(frozen=True)
class ImportMapping:
    kind: str
    type_id: uuid.UUID
    columns: tuple

    def to_json(self) -> dict:
        return {
            "target": {"kind": self.kind, "type_id": str(self.type_id)},
            "columns": [column.to_dict() for column in self.columns],
        }

    def get(self, field):
        for column in self.columns:
            if column.field == field:
                return column

        return None

    @property
    def match_column(self):
        for column in self.columns:
            if column.match:
                return column

        return None

    @property
    def value_columns(self):
        """Columns that assign a value (built-in fields and attributes), in column order."""

        return tuple(
            column
            for column in self.columns
            if column.field in BUILTIN_FIELD_PATHS or column.is_attribute
        )

    @classmethod
    def from_json(cls, payload, target, *, column_count, endpoint_types=None):
        """
        Validate `payload` against the canonical `target` (a TargetSpec) and the
        width of the source table. Raises MappingError listing every problem.
        `endpoint_types` maps object-type id -> TargetSpec for endpoint
        resolution in relationship imports.
        """

        errors = []

        if not isinstance(payload, dict):
            raise MappingError("The mapping is malformed.")

        declared = payload.get("target")

        if (
            not isinstance(declared, dict)
            or declared.get("kind") != target.kind
            or str(declared.get("type_id")) != str(target.type_id)
        ):
            raise MappingError("The mapping does not match the selected target.")

        raw_columns = payload.get("columns")

        if not isinstance(raw_columns, list):
            raise MappingError("The mapping is malformed.")

        if len(raw_columns) > limits.max_columns():
            raise MappingError("The mapping has too many columns.")

        allowed = OBJECT_FIELDS if target.kind == OBJECT else RELATIONSHIP_FIELDS
        endpoint_types = endpoint_types or {}

        parsed = []
        seen_columns = set()
        seen_fields = set()

        for position, raw in enumerate(raw_columns, start=1):

            entry = _parse_entry(raw, position, target, allowed, column_count, endpoint_types, errors)

            if entry is None:
                continue

            if entry.column in seen_columns:
                errors.append(f"Source column {entry.column + 1} is mapped more than once.")
                continue

            if entry.field in seen_fields:
                errors.append(f"{_label(entry.field)} is mapped more than once.")
                continue

            seen_columns.add(entry.column)
            seen_fields.add(entry.field)
            parsed.append(entry)

        if not raw_columns:
            errors.append("Map at least one column.")

        _check_requirements(target, parsed, errors)

        if errors:
            raise MappingError(errors)

        return cls(
            kind=target.kind,
            type_id=target.type_id,
            columns=tuple(sorted(parsed, key=lambda column: column.column)),
        )


def _label(field):
    return field.replace("attribute.", "Attribute ").replace("field.", "").replace(".", " ")


def _parse_entry(raw, position, target, allowed, column_count, endpoint_types, errors):

    if not isinstance(raw, dict):
        errors.append(f"Mapping entry {position} is malformed.")
        return None

    column = raw.get("column")
    field = raw.get("field")

    if not isinstance(column, int) or isinstance(column, bool) or not 0 <= column < column_count:
        errors.append(f"Mapping entry {position} refers to a column the file does not have.")
        return None

    if not isinstance(field, str):
        errors.append(f"Mapping entry {position} has no target field.")
        return None

    match = raw.get("match", False)

    if not isinstance(match, bool):
        errors.append(f"Mapping entry {position} has an invalid match flag.")
        return None

    is_attribute = field.startswith(ATTRIBUTE_PREFIX)

    if is_attribute:
        attribute = target.attribute(field[len(ATTRIBUTE_PREFIX):])

        if attribute is None:
            errors.append(
                f"'{field[len(ATTRIBUTE_PREFIX):]}' is not an active attribute of {target.name}."
            )
            return None

        if match:
            if target.kind != OBJECT:
                errors.append("Only object imports can match on an attribute.")
                return None

            if not attribute.identity_eligible:
                errors.append(
                    f"{attribute.name} is a {attribute.data_type} attribute and cannot be "
                    "used to identify objects."
                )
                return None

    elif field not in allowed:
        errors.append(f"'{field}' cannot be imported into {target.name}.")
        return None

    elif match:
        errors.append("Only an attribute can be used as the match field.")
        return None

    by = raw.get("by")
    object_type_id = None

    if field in (ENDPOINT_SUBJECT, ENDPOINT_OBJECT):

        object_type_id, by = _parse_endpoint(raw, position, by, endpoint_types, errors)

        if by is None:
            return None

    elif by is not None or raw.get("object_type_id") is not None:
        errors.append(f"Mapping entry {position} does not take a resolver.")
        return None

    return MappedColumn(
        column=column,
        field=field,
        match=match,
        by=by,
        object_type_id=object_type_id,
    )


def _parse_endpoint(raw, position, by, endpoint_types, errors):

    if by == BY_ID:

        if raw.get("object_type_id") is not None:
            errors.append(f"Mapping entry {position}: an id lookup takes no object type.")
            return None, None

        return None, BY_ID

    if not isinstance(by, str) or not by.startswith(BY_ATTRIBUTE_PREFIX):
        errors.append(f"Mapping entry {position}: choose how the endpoint is identified.")
        return None, None

    try:
        object_type_id = uuid.UUID(str(raw.get("object_type_id")))
    except (ValueError, TypeError, AttributeError):
        errors.append(f"Mapping entry {position}: choose the object type to look the endpoint up in.")
        return None, None

    spec = endpoint_types.get(object_type_id)

    if spec is None:
        errors.append(f"Mapping entry {position}: that object type was not found in this model.")
        return None, None

    attribute = spec.attribute(by[len(BY_ATTRIBUTE_PREFIX):])

    if attribute is None or not attribute.identity_eligible:
        errors.append(
            f"Mapping entry {position}: that attribute cannot be used to identify {spec.name} objects."
        )
        return None, None

    return object_type_id, by


def _check_requirements(target, parsed, errors):

    fields = {entry.field for entry in parsed}

    if sum(1 for entry in parsed if entry.match) > 1:
        errors.append("Only one attribute can be the match field.")

    if target.kind != RELATIONSHIP:
        return

    endpoints = {ENDPOINT_SUBJECT, ENDPOINT_OBJECT} & fields

    if IDENTITY_ID in fields:
        # The relationship id identifies the row. Endpoints are then only a
        # cross-check, and a cross-check needs both.
        if len(endpoints) == 1:
            errors.append(
                "Map both the source and target endpoints, or neither, alongside the "
                "relationship id."
            )

    elif endpoints != {ENDPOINT_SUBJECT, ENDPOINT_OBJECT}:
        errors.append(
            "Map both the source and target endpoints (or a relationship id) to identify each relationship."
        )
