from types import SimpleNamespace

from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship

# =====================================================================
# Shared helpers
#
# Mirrors the effective-value overlay pattern already established in
# model/views/common_context.py for the ontology (ObjectType /
# RelationshipType), applied here to Object / Relationship data
# records. Object/Relationship attribute values live nested inside a
# single `attributes` JSON blob rather than as top-level model fields,
# so attribute-level changes are addressed with a dot-namespaced field
# key ("attributes.<key>") instead of a bare field name.
# =====================================================================

ATTRIBUTE_FIELD_PREFIX = "attributes."


def attribute_field_name(key):
    return f"{ATTRIBUTE_FIELD_PREFIX}{key}"


def _proposal_changes(
    proposal,
    target_type,
    target_id=None,
    operation=None,
):
    if not proposal:
        return []

    filters = {
        "target_type": target_type,
    }

    if target_id is not None:
        filters["target_id"] = target_id

    if operation is not None:
        filters["operation"] = operation

    return list(
        proposal.changes.filter(
            **filters,
        ).order_by(
            "created_at",
        )
    )


def coerce_attribute_value(
    data_type,
    raw_value,
):
    """
    Coerce a raw form value into a Python value suitable for storage in
    an Object/Relationship's `attributes` JSON blob, following the same
    per-data-type conventions as
    object_type_editor.py's _coerce_default_value.
    """

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()

    if raw_value in (None, ""):
        return None

    if data_type == AttributeDefinition.DataType.NUMBER:

        try:

            if "." in str(raw_value):
                return float(raw_value)

            return int(raw_value)

        except (TypeError, ValueError):
            raise ValueError("Value must be a number.")

    if data_type == AttributeDefinition.DataType.BOOLEAN:

        value = str(raw_value).strip().lower()

        if value in {"true", "1", "yes", "on"}:
            return True

        if value in {"false", "0", "no", "off"}:
            return False

        raise ValueError("Value must be true or false.")

    return raw_value


# =====================================================================
# AttributeDefinition resolution (values, not ontology editing)
# =====================================================================


def _data_type_label(data_type):
    return dict(AttributeDefinition.DataType.choices).get(data_type, data_type)


def _build_attribute_definitions(
    proposal,
    canonical_queryset,
    parent_type,
    parent_id,
):
    """
    Shared implementation behind build_object_attribute_definitions and
    build_relationship_attribute_definitions: effective, active
    AttributeDefinitions for a parent ObjectType/RelationshipType,
    combining canonical definitions with proposal-only CREATE
    definitions from the same working proposal, so a freshly proposed
    (not yet canonical) attribute is immediately available on the
    record editor. Each returned object exposes .key/.name/.data_type/
    .nullable/.config/.get_data_type_display(), matching the surface
    model.services.validation.attributes.validate_attribute_value
    reads, whether it's a real AttributeDefinition or a synthesised one.
    """

    definitions = list(
        canonical_queryset.filter(
            is_active=True,
        ).order_by(
            "sort_order",
            "name",
        )
    )

    canonical_ids = {str(definition.id) for definition in definitions}

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type=parent_type,
            parent_id=parent_id,
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            after = change.after or {}

            if not after.get("is_active", True):
                continue

            data_type = after.get(
                "data_type",
                AttributeDefinition.DataType.TEXT,
            )

            definitions.append(
                SimpleNamespace(
                    id=change.target_id,
                    key=after.get("key", ""),
                    name=after.get("name", ""),
                    data_type=data_type,
                    description=after.get("description", ""),
                    required=after.get("required", False),
                    nullable=after.get("nullable", False),
                    default_value=after.get("default_value"),
                    sort_order=after.get("sort_order", 0),
                    config=after.get("config") or {},
                    get_data_type_display=lambda dt=data_type: _data_type_label(dt),
                )
            )

    definitions.sort(
        key=lambda definition: (
            definition.sort_order,
            definition.name,
        )
    )

    return definitions


def build_object_attribute_definitions(
    object_type,
    proposal,
):
    return _build_attribute_definitions(
        proposal,
        AttributeDefinition.objects.filter(object_type=object_type),
        parent_type="ObjectType",
        parent_id=object_type.id,
    )


def build_relationship_attribute_definitions(
    relationship_type,
    proposal,
):
    return _build_attribute_definitions(
        proposal,
        AttributeDefinition.objects.filter(relationship_type=relationship_type),
        parent_type="RelationshipType",
        parent_id=relationship_type.id,
    )


# =====================================================================
# Object effective-value overlay
# =====================================================================


def _canonical_object_values(obj):
    return {
        "name": obj.name,
        "description": obj.description,
        "is_active": obj.is_active,
        "attributes": dict(obj.attributes or {}),
    }


def object_effective_values(
    obj,
    proposal,
):
    """
    Return canonical Object values with any field-level changes from
    the user's working proposal applied. Top-level fields (name,
    description, is_active) overlay directly; attribute values overlay
    into the nested `attributes` dict via the "attributes.<key>"
    addressing convention.
    """

    values = _canonical_object_values(obj)

    for change in _proposal_changes(
        proposal,
        target_type="Object",
        target_id=obj.id,
        operation=ProposalChange.Operation.UPDATE,
    ):

        after = change.after or {}
        field = after.get("field")

        if not field or "value" not in after:
            continue

        if field.startswith(ATTRIBUTE_FIELD_PREFIX):
            key = field[len(ATTRIBUTE_FIELD_PREFIX):]
            values["attributes"][key] = after["value"]
        elif field in values:
            values[field] = after["value"]

    return values


def object_is_proposed(
    obj,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="Object",
        target_id=obj.id,
    ).exists()


def object_create_change(
    object_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="Object",
            target_id=object_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def build_working_objects(
    queryset,
    proposal,
):
    """
    Canonical Object rows with the proposal overlay applied, wrapped as
    view-objects, matching the shape of
    common_context._build_working_object_types.
    """

    items = []

    for obj in queryset:

        effective = object_effective_values(
            obj,
            proposal,
        )

        items.append(
            SimpleNamespace(
                id=obj.id,
                object_type_id=obj.object_type_id,
                name=effective["name"],
                description=effective["description"],
                is_active=effective["is_active"],
                attributes=effective["attributes"],
                is_proposed=object_is_proposed(
                    obj,
                    proposal,
                ),
                is_created=False,
            )
        )

    return items


def build_proposed_only_objects(
    object_type,
    proposal,
):
    """
    Objects that exist only as a proposal CREATE change (no canonical
    row yet), synthesised as view-objects for display alongside the
    canonical table.
    """

    items = []

    if not proposal:
        return items

    canonical_ids = set(
        Object.objects.filter(
            object_type=object_type,
        ).values_list(
            "id",
            flat=True,
        )
    )

    create_changes = proposal.changes.filter(
        target_type="Object",
        operation=ProposalChange.Operation.CREATE,
        parent_type="ObjectType",
        parent_id=object_type.id,
    ).order_by(
        "created_at",
    )

    for change in create_changes:

        if not change.target_id:
            continue

        if change.target_id in canonical_ids:
            continue

        after = change.after or {}

        items.append(
            SimpleNamespace(
                id=change.target_id,
                object_type_id=object_type.id,
                name=after.get("name", ""),
                description=after.get("description", ""),
                is_active=after.get("is_active", True),
                attributes=dict(after.get("attributes") or {}),
                is_proposed=True,
                is_created=True,
            )
        )

    return items


# =====================================================================
# Relationship effective-value overlay
#
# Relationship has no name/description fields of its own (unlike
# Object) — its only top-level editable field is is_active, handled
# via the lifecycle actions rather than generic field editing, so the
# only field-level UPDATE addressing used here is "attributes.<key>".
# =====================================================================


def _canonical_relationship_values(relationship):
    return {
        "is_active": relationship.is_active,
        "attributes": dict(relationship.attributes or {}),
    }


def relationship_effective_values(
    relationship,
    proposal,
):
    values = _canonical_relationship_values(relationship)

    for change in _proposal_changes(
        proposal,
        target_type="Relationship",
        target_id=relationship.id,
        operation=ProposalChange.Operation.UPDATE,
    ):

        after = change.after or {}
        field = after.get("field")

        if not field or "value" not in after:
            continue

        if field.startswith(ATTRIBUTE_FIELD_PREFIX):
            key = field[len(ATTRIBUTE_FIELD_PREFIX):]
            values["attributes"][key] = after["value"]
        elif field in values:
            values[field] = after["value"]

    return values


def relationship_is_proposed(
    relationship,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="Relationship",
        target_id=relationship.id,
    ).exists()


def relationship_create_change(
    relationship_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="Relationship",
            target_id=relationship_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def resolve_object_names(ids):
    """
    Batch-resolve Object names for display, used to label a
    proposal-only Relationship CREATE's subject_id/object_id (stored
    as raw string UUIDs in the change payload).
    """

    ids = {str(value) for value in ids if value}

    if not ids:
        return {}

    return {
        str(object_id): name
        for object_id, name in Object.objects.filter(
            id__in=ids,
        ).values_list("id", "name")
    }


def build_working_relationships(
    queryset,
    proposal,
):
    items = []

    for relationship in queryset:

        effective = relationship_effective_values(
            relationship,
            proposal,
        )

        items.append(
            SimpleNamespace(
                id=relationship.id,
                relationship_type_id=relationship.relationship_type_id,
                subject_id=relationship.subject_id,
                subject_name=relationship.subject.name,
                subject_object_type_id=relationship.subject.object_type_id,
                object_id=relationship.object_id,
                object_name=relationship.object.name,
                object_object_type_id=relationship.object.object_type_id,
                is_active=effective["is_active"],
                attributes=effective["attributes"],
                is_proposed=relationship_is_proposed(
                    relationship,
                    proposal,
                ),
                is_created=False,
            )
        )

    return items


def build_proposed_only_relationships(
    relationship_type,
    proposal,
):
    items = []

    if not proposal:
        return items

    canonical_ids = set(
        Relationship.objects.filter(
            relationship_type=relationship_type,
        ).values_list(
            "id",
            flat=True,
        )
    )

    create_changes = proposal.changes.filter(
        target_type="Relationship",
        operation=ProposalChange.Operation.CREATE,
        parent_type="RelationshipType",
        parent_id=relationship_type.id,
    ).order_by(
        "created_at",
    )

    subject_object_ids = []

    for change in create_changes:
        after = change.after or {}
        subject_object_ids.append(after.get("subject_id"))
        subject_object_ids.append(after.get("object_id"))

    names = resolve_object_names(subject_object_ids)

    for change in create_changes:

        if not change.target_id:
            continue

        if change.target_id in canonical_ids:
            continue

        after = change.after or {}

        subject_id = after.get("subject_id")
        object_id = after.get("object_id")

        items.append(
            SimpleNamespace(
                id=change.target_id,
                relationship_type_id=relationship_type.id,
                subject_id=subject_id,
                subject_name=names.get(str(subject_id), "Unknown"),
                object_id=object_id,
                object_name=names.get(str(object_id), "Unknown"),
                is_active=after.get("is_active", True),
                attributes=dict(after.get("attributes") or {}),
                is_proposed=True,
                is_created=True,
            )
        )

    return items
