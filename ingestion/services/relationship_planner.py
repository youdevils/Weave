"""
Plan a Relationship import: one existing RelationshipType, one directed
relationship per row.

A relationship is identified by, in order:
  * its Weave Relationship ID, if that column is mapped and filled; supplied
    endpoints are then only a cross-check and are never written on an UPDATE;
  * otherwise its endpoints: (source object, target object) *in that
    direction* -- A -> B and B -> A are different relationships.

Endpoints must already exist (they are resolved by Weave Object ID or an
explicitly chosen attribute, exactly). Whether the resulting relationship is
allowed by the relationship type is not decided here.
"""

from collections import defaultdict

from ingestion.services import coercion
from ingestion.services.identity import EndpointResolver
from ingestion.services.mapping import (
    BUILTIN_FIELD_PATHS,
    ENDPOINT_OBJECT,
    ENDPOINT_SUBJECT,
    FIELD_IS_ACTIVE,
    IDENTITY_ID,
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
    parse_uuid,
    problem,
    snippet,
    values_equal,
)
from model.models.object import Object
from model.models.relationship import Relationship
from model.services.field_paths import attribute_field_name


def plan_relationship_import(model, table, target, mapping, object_type_specs) -> ImportPlan:

    type_id = target.type_id

    canonical = {}
    by_pair = defaultdict(list)

    for row in Relationship.objects.filter(model=model, relationship_type_id=type_id).values(
        "id", "subject_id", "object_id", "is_active", "attributes"
    ):
        canonical[row["id"]] = row
        by_pair[(row["subject_id"], row["object_id"])].append(row["id"])

    id_entry = mapping.get(IDENTITY_ID)
    subject_entry = mapping.get(ENDPOINT_SUBJECT)
    object_entry = mapping.get(ENDPOINT_OBJECT)
    value_entries = mapping.value_columns

    resolvers = {}

    for entry, label in ((subject_entry, "source object"), (object_entry, "target object")):
        if entry is not None:
            resolvers[entry.field] = EndpointResolver(
                model,
                entry,
                label,
                object_type_specs,
                [row[entry.column] for row in table.rows],
            )

    other_type_ids = _ids_of_other_types(model, type_id, table, id_entry)

    summary = PlanSummary(kind="relationship", rows=table.row_count)
    problems = []
    accumulator = Accumulator()

    for row_number, row in zip(table.row_numbers, table.rows):

        resolved = _resolve_row(
            row_number, row, id_entry, subject_entry, object_entry, resolvers,
            canonical, by_pair, other_type_ids,
        )

        if isinstance(resolved, list):
            problems.extend(resolved)
            continue

        existing_id, endpoints = resolved

        assignments, unconverted = _assignments(row, value_entries, target)

        summary.unconverted_cells += unconverted

        if existing_id is not None:
            key, kwargs = ("existing", existing_id), {"existing_id": existing_id}
        else:
            # A new relationship is identified by its directed endpoint pair,
            # so two rows for the same new pair are one CREATE, never two.
            key, kwargs = ("new", endpoints), {"extra": {"endpoints": endpoints}}

        entry = accumulator.target(key, **kwargs)
        entry.rows.append(row_number)

        for field_name, value in assignments.items():
            entry.assign[field_name] = value

    if problems:
        return ImportPlan(summary=summary, problems=problems)

    return _emit(model, target, value_entries, canonical, accumulator, summary)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _ids_of_other_types(model, type_id, table, id_entry):
    """Relationship ids in the source that exist in this model under another type."""

    if id_entry is None:
        return set()

    ids = {parse_uuid(row[id_entry.column]) for row in table.rows if not coercion.is_blank(row[id_entry.column])}
    ids.discard(None)

    if not ids:
        return set()

    return set(
        Relationship.objects.filter(model=model, id__in=ids)
        .exclude(relationship_type_id=type_id)
        .values_list("id", flat=True)
    )


def _resolve_row(row_number, row, id_entry, subject_entry, object_entry, resolvers,
                 canonical, by_pair, other_type_ids):
    """
    (existing_relationship_id | None, (subject_id, object_id) | None) for a row,
    or a list of blocking problems.
    """

    problems = []

    subject_id = object_id = None

    if subject_entry is not None:

        subject_id, failure = resolvers[ENDPOINT_SUBJECT].resolve(row[subject_entry.column])

        if failure:
            problems.append(problem(failure[0], failure[1], row_number))

        object_id, failure = resolvers[ENDPOINT_OBJECT].resolve(row[object_entry.column])

        if failure:
            problems.append(problem(failure[0], failure[1], row_number))

    if id_entry is not None and not coercion.is_blank(row[id_entry.column]):

        cell = row[id_entry.column]
        relationship_id = parse_uuid(cell)

        if relationship_id is None:
            problems.append(problem(
                "invalid_identity_id",
                f"'{snippet(cell)}' is not a valid Weave Relationship ID.",
                row_number,
            ))

        elif relationship_id in other_type_ids:
            problems.append(problem(
                "wrong_relationship_type",
                f"Relationship '{snippet(cell)}' belongs to a different relationship type.",
                row_number,
            ))

        elif relationship_id not in canonical:
            problems.append(problem(
                "unresolved_identity",
                f"No relationship with id '{snippet(cell)}' exists in this model.",
                row_number,
            ))

        elif subject_id is not None and object_id is not None:

            known = canonical[relationship_id]

            # Endpoints given alongside an id only cross-check it.
            if (known["subject_id"], known["object_id"]) != (subject_id, object_id):
                problems.append(problem(
                    "identity_mismatch",
                    f"Relationship '{snippet(cell)}' does not connect the source and "
                    "target objects given on this row.",
                    row_number,
                ))

        if problems:
            return problems

        return relationship_id, None

    if problems:
        return problems

    if subject_entry is None:
        # Cannot happen for a validated mapping; kept as a safe, explicit failure.
        return [problem("missing_identity", "This row has no relationship id or endpoints.", row_number)]

    matches = by_pair.get((subject_id, object_id), [])

    if len(matches) > 1:
        return [problem(
            "ambiguous_relationship",
            f"{len(matches)} relationships already connect these two objects in this "
            "direction. Use the Weave Relationship ID to say which one.",
            row_number,
        )]

    if len(matches) == 1:
        return matches[0], None

    return None, (subject_id, object_id)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


def _assignments(row, value_entries, target):

    assigned = {}
    unconverted = 0

    for entry in value_entries:

        cell = row[entry.column]

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


def _emit(model, target, value_entries, canonical, accumulator, summary):

    changes = []
    pending_items = []

    for entry in accumulator.targets.values():

        if len(entry.rows) > 1:
            summary.duplicate_identities += 1
            summary.duplicate_rows += len(entry.rows)

        if entry.existing_id is not None:

            row = canonical[entry.existing_id]
            fields = []

            for column in value_entries:

                if column.field not in entry.assign:
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
                        target_type="Relationship",
                        target_id=entry.existing_id,
                        parent_type="RelationshipType",
                        parent_id=target.type_id,
                        before={"field": path, "value": before},
                        after={"field": path, "value": after},
                    )
                )

            if len(pending_items) < PREVIEW_ITEMS_SHOWN:
                pending_items.append((
                    UPDATE,
                    (row["subject_id"], row["object_id"]),
                    entry,
                    [{"field": path, "before": before, "after": after} for path, before, after in fields],
                ))

            continue

        subject_id, object_id = entry.extra["endpoints"]

        payload = {
            "subject_id": str(subject_id),
            "object_id": str(object_id),
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

        summary.creates += 1

        changes.append(
            PlannedChange(
                operation=CREATE,
                target_type="Relationship",
                target_id=entry.new_id,
                parent_type="RelationshipType",
                parent_id=target.type_id,
                before=None,
                after=payload,
            )
        )

        if len(pending_items) < PREVIEW_ITEMS_SHOWN:

            fields = [{"field": "is_active", "before": None, "after": payload["is_active"]}]

            for key, value in payload["attributes"].items():
                fields.append({"field": attribute_field_name(key), "before": None, "after": value})

            pending_items.append((CREATE, (subject_id, object_id), entry, fields))

    items = _label_items(model, pending_items)

    return enforce_change_limit(ImportPlan(summary=summary, changes=changes, items=items))


def _label_items(model, pending_items):
    """Name the endpoints of the few previewed relationships (one query)."""

    ids = {endpoint for _, pair, _, _ in pending_items for endpoint in pair}

    names = dict(Object.objects.filter(model=model, id__in=ids).values_list("id", "name"))

    return [
        PreviewItem(
            operation=operation,
            label=f"{names.get(pair[0], '?')} → {names.get(pair[1], '?')}",
            row=entry.rows[0],
            rows=len(entry.rows),
            fields=fields,
        )
        for operation, pair, entry, fields in pending_items
    ]
