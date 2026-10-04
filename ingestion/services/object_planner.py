"""
Plan an Object import: one existing ObjectType, one row per Object.

Per row:
  1. identify the record  -- the object's OnyxJar Key (the normal column),
                             and/or, as advanced/optional cross-checks, its
                             Database ID and/or the explicitly chosen match
                             attribute, exactly, or no identity (a new record);
  2. accumulate           -- later rows overwrite earlier assignments to the
                             same target field (blank is a real assignment);
  3. after the last row   -- compare each existing record's *final* values with
                             its canonical ones: differences become UPDATEs
                             (canonical before -> final after), the rest NO-OP;
                             new records become one CREATE each, with a new
                             key derived from its name (never from a key cell
                             -- see _identify).

Nothing here judges whether a change is allowed.
"""

from ingestion.services import coercion
from ingestion.services.identity import AttributeIndex, KeyIndex
from ingestion.services.mapping import (
    BUILTIN_FIELD_PATHS,
    FIELD_DESCRIPTION,
    FIELD_IS_ACTIVE,
    FIELD_NAME,
    IDENTITY_ID,
    IDENTITY_KEY,
)
from ingestion.services.plan import (
    CREATE,
    PREVIEW_ITEMS_SHOWN,
    UPDATE,
    Accumulator,
    ImportPlan,
    PlanSummary,
    PlannedChange,
    PreviewItem,
    enforce_change_limit,
    identity_key,
    parse_uuid,
    problem,
    snippet,
    values_equal,
)
from model.models.object import Object
from model.services import keys as key_service
from model.services.field_paths import attribute_field_name


def plan_object_import(model, table, target, mapping) -> ImportPlan:

    type_id = target.type_id

    canonical = {
        row["id"]: row
        for row in Object.objects.filter(model=model, object_type_id=type_id).values(
            "id", "name", "key", "description", "is_active", "attributes"
        )
    }

    key_entry = mapping.get(IDENTITY_KEY)
    id_entry = mapping.get(IDENTITY_ID)
    match_entry = mapping.match_column
    value_entries = mapping.value_columns

    key_index = KeyIndex(model, type_id) if key_entry else None
    match_attribute = target.attribute(match_entry.attribute_key) if match_entry else None
    index = (
        AttributeIndex(model, type_id, match_attribute.key) if match_entry else None
    )

    other_type_ids = _ids_of_other_types(model, type_id, table, id_entry)

    summary = PlanSummary(kind="object", rows=table.row_count)
    problems = []
    accumulator = Accumulator()

    if key_entry is None and id_entry is None and match_entry is None:
        summary.warnings.append(
            "No identity column is mapped, so every row creates a new object. Importing "
            "the same file again will create them again."
        )

    for row_number, row in zip(table.row_numbers, table.rows):

        outcome = _identify(
            row_number, row, key_entry, key_index, id_entry, match_entry, match_attribute, index,
            canonical, other_type_ids,
        )

        if outcome.problem is not None:
            problems.append(outcome.problem)
            continue

        assignments, unconverted = _assignments(row, value_entries, target)

        summary.unconverted_cells += unconverted

        if outcome.existing_id is not None:
            key, kwargs = ("existing", outcome.existing_id), {"existing_id": outcome.existing_id}
        elif outcome.match_key is not None:
            key, kwargs = ("new", outcome.match_key), {}
        else:
            key, kwargs = ("anonymous", row_number), {"identified": False}

        entry = accumulator.target(key, **kwargs)
        entry.rows.append(row_number)

        for field_name, value in assignments.items():
            entry.assign[field_name] = value

    if problems:
        return ImportPlan(summary=summary, problems=problems)

    return _emit(model, target, mapping, value_entries, canonical, accumulator, summary)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class _Identified:
    __slots__ = ("existing_id", "match_key", "problem")

    def __init__(self, existing_id=None, match_key=None, problem=None):
        self.existing_id = existing_id
        self.match_key = match_key
        self.problem = problem


def _ids_of_other_types(model, type_id, table, id_entry):
    """Ids in the source that name an Object of this model but another type."""

    if id_entry is None:
        return set()

    ids = {parse_uuid(row[id_entry.column]) for row in table.rows if not coercion.is_blank(row[id_entry.column])}
    ids.discard(None)

    if not ids:
        return set()

    return set(
        Object.objects.filter(model=model, id__in=ids)
        .exclude(object_type_id=type_id)
        .values_list("id", flat=True)
    )


def _identify(row_number, row, key_entry, key_index, id_entry, match_entry, match_attribute, index,
              canonical, other_type_ids):

    key_id = None

    # -- the OnyxJar Key (the normal identity column) ------------------------

    if key_entry is not None and not coercion.is_blank(row[key_entry.column]):

        cell = row[key_entry.column]
        matches = key_index.find(str(cell).strip())

        if not matches:
            return _Identified(problem=problem(
                "unresolved_identity",
                f"No object has key '{snippet(cell)}'. Keys are assigned by OnyxJar: leave "
                "the cell blank to create a new object.",
                row_number,
            ))

        key_id = matches[0]

    existing_id = key_id
    match_key = None
    match_value = None

    # -- the Database ID (an advanced/optional cross-check) -------------------

    if id_entry is not None and not coercion.is_blank(row[id_entry.column]):

        cell = row[id_entry.column]
        parsed = parse_uuid(cell)

        if parsed is None:
            return _Identified(problem=problem(
                "invalid_identity_id",
                f"'{snippet(cell)}' is not a valid Database ID.",
                row_number,
            ))

        if parsed in other_type_ids:
            return _Identified(problem=problem(
                "wrong_object_type",
                f"Object '{snippet(cell)}' belongs to a different object type.",
                row_number,
            ))

        if parsed not in canonical:
            return _Identified(problem=problem(
                "unresolved_identity",
                f"No object with id '{snippet(cell)}' exists in this model.",
                row_number,
            ))

        if key_id is not None and parsed != key_id:
            return _Identified(problem=problem(
                "identity_mismatch",
                f"The key and the Database ID on this row identify different objects.",
                row_number,
            ))

        existing_id = parsed

    # -- the match attribute (an advanced/optional cross-check) ---------------

    matches = None

    if match_entry is not None and not coercion.is_blank(row[match_entry.column]):

        cell = row[match_entry.column]

        # Normalised once: this exact value is both what is matched and what
        # a CREATE writes.
        coerced = coercion.coerce_attribute_cell(match_attribute.data_type, cell)
        match_key = identity_key(coerced.value)

        if not coerced.converted or match_key is None:
            return _Identified(problem=problem(
                "invalid_identity_value",
                f"'{snippet(cell)}' cannot be read as a {match_attribute.name} value.",
                row_number,
            ))

        match_value = coerced.value
        matches = index.find(match_value)

    # -- combine ------------------------------------------------------------

    if existing_id is not None:

        if matches is not None and existing_id not in matches:
            return _Identified(problem=problem(
                "identity_mismatch",
                f"Object '{existing_id}' does not have {match_attribute.name} "
                f"'{snippet(match_value)}'.",
                row_number,
            ))

        return _Identified(existing_id=existing_id)

    if matches is None:
        return _Identified()

    if len(matches) > 1:
        return _Identified(problem=problem(
            "ambiguous_identity",
            f"{len(matches)} objects have {match_attribute.name} '{snippet(match_value)}'.",
            row_number,
        ))

    if len(matches) == 1:
        return _Identified(existing_id=matches[0])

    return _Identified(match_key=match_key)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def _assignments(row, value_entries, target):
    """
    field path -> value for every mapped value column of one row, plus the
    number of cells that could not be read as their target type.
    """

    assigned = {}
    unconverted = 0

    for entry in value_entries:

        cell = row[entry.column]

        if entry.field == FIELD_NAME or entry.field == FIELD_DESCRIPTION:
            assigned[entry.field] = coercion.coerce_name_cell(cell)
            continue

        if entry.field == FIELD_IS_ACTIVE:
            coerced = coercion.coerce_is_active_cell(cell)
        else:
            attribute = target.attribute(entry.attribute_key)
            coerced = coercion.coerce_attribute_cell(attribute.data_type, cell)

        if not coerced.converted:
            unconverted += 1

        assigned[entry.field] = coerced.value

    return assigned, unconverted


def _canonical_value(row, entry):

    if entry.field in BUILTIN_FIELD_PATHS:
        return row[BUILTIN_FIELD_PATHS[entry.field]]

    return (row["attributes"] or {}).get(entry.attribute_key)


def _path(entry):

    if entry.field in BUILTIN_FIELD_PATHS:
        return BUILTIN_FIELD_PATHS[entry.field]

    return attribute_field_name(entry.attribute_key)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def _emit(model, target, mapping, value_entries, canonical, accumulator, summary):

    changes = []
    items = []

    # Seeded once from the DB, then grown as each new row's key is
    # allocated, so two new rows in the same import never collide with
    # each other even though neither is in the database yet.
    used_keys = key_service.existing_keys_for(
        "Object", model, parent_type="ObjectType", parent_id=target.type_id,
    )

    for entry in accumulator.targets.values():

        if entry.identified and len(entry.rows) > 1:
            summary.duplicate_identities += 1
            summary.duplicate_rows += len(entry.rows)

        if entry.existing_id is not None:

            row = canonical[entry.existing_id]
            fields = []

            for column in value_entries:

                # The match attribute located this record; it is never changed
                # by the import that used it to find it.
                if column.match or column.field not in entry.assign:
                    continue

                before = _canonical_value(row, column)
                after = entry.assign[column.field]

                if not values_equal(before, after):
                    fields.append((_path(column), before, after))

            if not fields:
                summary.no_ops += 1
                continue

            summary.updates += 1
            summary.field_changes += len(fields)

            for path, before, after in fields:
                changes.append(
                    PlannedChange(
                        operation=UPDATE,
                        target_type="Object",
                        target_id=entry.existing_id,
                        parent_type="ObjectType",
                        parent_id=target.type_id,
                        before={"field": path, "value": before},
                        after={"field": path, "value": after},
                    )
                )

            _preview(items, UPDATE, f"{row['name']} ({row['key']})", entry, [
                {"field": path, "before": before, "after": after} for path, before, after in fields
            ])

            continue

        payload = _create_payload(value_entries, entry, used_keys)

        summary.creates += 1

        changes.append(
            PlannedChange(
                operation=CREATE,
                target_type="Object",
                target_id=entry.new_id,
                parent_type="ObjectType",
                parent_id=target.type_id,
                before=None,
                after=payload,
            )
        )

        label = f"{payload['name'] or '(no name)'} ({payload['key']})"
        _preview(items, CREATE, label, entry, _create_fields(payload))

    return enforce_change_limit(ImportPlan(summary=summary, changes=changes, items=items))


def _create_payload(value_entries, entry, used_keys):
    """
    The CREATE payload, shaped exactly as the record editor writes it. A blank
    attribute or is_active is left out (unset), so the model default applies.

    The key is always derived from the name here -- never from an identity
    cell (a key cell only ever identifies an *existing* object; see
    _identify) -- using the same slug/fallback/suffix rule every other
    creation path uses (model.services.keys), against `used_keys` (seeded
    from the DB once by the caller, then grown here as each new row
    allocates its own) so two new rows in the same import never collide
    with each other, without a DB round trip per row.
    """

    name = entry.assign.get(FIELD_NAME, "")
    key = key_service.make_unique_key(name, used_keys, fallback="object")
    used_keys.add(key)

    payload = {
        "name": name,
        "key": key,
        "description": entry.assign.get(FIELD_DESCRIPTION, ""),
        "is_active": True,
        "attributes": {},
    }

    is_active = entry.assign.get(FIELD_IS_ACTIVE)

    if is_active is not None:
        payload["is_active"] = is_active

    for column in value_entries:

        if not column.is_attribute:
            continue

        value = entry.assign.get(column.field)

        if value is not None:
            payload["attributes"][column.attribute_key] = value

    return payload


def _create_fields(payload):

    fields = [
        {"field": "name", "before": None, "after": payload["name"]},
        {"field": "description", "before": None, "after": payload["description"]},
        {"field": "is_active", "before": None, "after": payload["is_active"]},
    ]

    for key, value in payload["attributes"].items():
        fields.append({"field": attribute_field_name(key), "before": None, "after": value})

    return fields


def _preview(items, operation, label, entry, fields):

    if len(items) < PREVIEW_ITEMS_SHOWN:
        items.append(
            PreviewItem(
                operation=operation,
                label=label,
                row=entry.rows[0],
                rows=len(entry.rows),
                fields=fields,
            )
        )
