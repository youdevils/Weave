from types import SimpleNamespace

from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.services.coercion import coerce_attribute_value  # noqa: F401  (re-exported)
from model.services.field_paths import (  # noqa: F401  (re-exported)
    ATTRIBUTE_FIELD_PREFIX,
    attribute_field_name,
)
from model.services.proposal.proposal import ProposalService
from model.services.validation.fields import RELATIONSHIP_ENDPOINT_FIELDS

# =====================================================================
# Working-type resolution
#
# Mirrors object_type_editor.py's private _get_working_object_type
# (kept as a separate small copy here rather than imported, consistent
# with this module's existing per-concern duplication of small
# resolver helpers such as object_create_change/relationship_create_change).
# Resolves an ObjectType/RelationshipType from the effective,
# proposal-inclusive context collections built by common_context.py,
# so a Data page can be opened for a type that only exists as a
# proposal CREATE change.
# =====================================================================


def resolve_working_object_type(context, object_type_id):
    if not object_type_id:
        return None

    object_type_id = str(object_type_id)

    for candidate in context.get("object_types", []):
        if str(candidate.id) == object_type_id:
            return candidate

    return None


def resolve_working_relationship_type(context, relationship_type_id):
    if not relationship_type_id:
        return None

    relationship_type_id = str(relationship_type_id)

    for candidate in context.get("relationship_types", []):
        if str(candidate.id) == relationship_type_id:
            return candidate

    return None

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

    # -------------------------------------------------------------
    # Overlay pending UPDATEs onto canonical definitions (in-memory
    # only — never saved), mirroring the effective-value overlay
    # pattern already used for ObjectType/RelationshipType in
    # common_context.py. Without this, a pending edit to an
    # already-canonical attribute (e.g. configuring Choice values)
    # would never reach the Data layer.
    # -------------------------------------------------------------

    if proposal and definitions:

        update_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            target_id__in=[definition.id for definition in definitions],
            operation=ProposalChange.Operation.UPDATE,
        ).order_by(
            "created_at",
        )

        changes_by_target = {}

        for change in update_changes:
            changes_by_target.setdefault(str(change.target_id), []).append(change)

        editable_fields = {
            "name", "key", "data_type", "description", "required",
            "nullable", "default_value", "sort_order", "config", "is_active",
        }

        for definition in definitions:
            for change in changes_by_target.get(str(definition.id), []):
                after = change.after or {}
                field = after.get("field")
                if field in editable_fields and "value" in after:
                    setattr(definition, field, after["value"])

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
        AttributeDefinition.objects.filter(object_type_id=object_type.id),
        parent_type="ObjectType",
        parent_id=object_type.id,
    )


def build_relationship_attribute_definitions(
    relationship_type,
    proposal,
):
    return _build_attribute_definitions(
        proposal,
        AttributeDefinition.objects.filter(relationship_type_id=relationship_type.id),
        parent_type="RelationshipType",
        parent_id=relationship_type.id,
    )


# =====================================================================
# Object effective-value overlay
# =====================================================================


def apply_field_updates(
    values,
    changes,
):
    """
    Apply field-level UPDATE changes, in order, onto an effective-values
    dict (mutated and returned). "attributes.<key>" fields overlay into
    the nested `attributes` dict; other fields overlay only if they are
    already a top-level key of `values`. Shared by the per-record
    overlays below and by callers that have pre-fetched a proposal's
    changes in bulk (e.g. the model graph loader), so there is exactly
    one implementation of the overlay rules.
    """

    for change in changes:

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

    return apply_field_updates(
        _canonical_object_values(obj),
        _proposal_changes(
            proposal,
            target_type="Object",
            target_id=obj.id,
            operation=ProposalChange.Operation.UPDATE,
        ),
    )


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
            object_type_id=object_type.id,
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
# Object). Its top-level editable fields are is_active (handled via the
# lifecycle actions) and its endpoints, subject_id/object_id, which are
# addressed by bare field name and carry an Object id as a string —
# the same shape they have in a Relationship CREATE payload. Attribute
# values use "attributes.<key>" as for Object.
# =====================================================================


def _canonical_relationship_values(relationship):
    return {
        "is_active": relationship.is_active,
        "subject_id": str(relationship.subject_id),
        "object_id": str(relationship.object_id),
        "attributes": dict(relationship.attributes or {}),
    }


def relationship_effective_values(
    relationship,
    proposal,
):
    return apply_field_updates(
        _canonical_relationship_values(relationship),
        _proposal_changes(
            proposal,
            target_type="Relationship",
            target_id=relationship.id,
            operation=ProposalChange.Operation.UPDATE,
        ),
    )


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


def resolve_object_names(ids, proposal=None):
    """
    Batch-resolve Object names for display, used to label a
    proposal-only Relationship CREATE's subject_id/object_id (stored
    as raw string UUIDs in the change payload). Falls back to scanning
    the proposal's own Object CREATE changes for any id that isn't
    canonical yet, so a Relationship endpoint that is itself only a
    proposal-only Object never displays as "Unknown".
    """

    ids = {str(value) for value in ids if value}

    if not ids:
        return {}

    names = {
        str(object_id): name
        for object_id, name in Object.objects.filter(
            id__in=ids,
        ).values_list("id", "name")
    }

    missing_ids = ids - set(names)

    if missing_ids and proposal:

        for change in proposal.changes.filter(
            target_type="Object",
            operation=ProposalChange.Operation.CREATE,
            target_id__in=missing_ids,
        ):
            after = change.after or {}
            names[str(change.target_id)] = after.get("name") or "Untitled"

    return names


def resolve_relationship_endpoint(object_id, proposal):
    """
    Resolve a Relationship endpoint by id alone: canonical Object
    first, else a proposal-only Object CREATE change in the same
    proposal. Used only for display (.name) and building the
    data_object_edit URL (.object_type_id) — full nested ObjectType
    resolution isn't needed here.
    """

    if not object_id:
        return None

    obj = Object.objects.filter(id=object_id).select_related("object_type").first()

    if obj is not None:
        return obj

    create_change = object_create_change(object_id, proposal)

    if create_change is None:
        return None

    after = create_change.after or {}

    return SimpleNamespace(
        id=create_change.target_id,
        name=after.get("name", ""),
        object_type_id=create_change.parent_id,
    )


def _effective_endpoint(canonical, effective_id, proposal):
    """
    The canonical endpoint, unless a pending UPDATE re-points it — only
    then is the proposed Object looked up.
    """

    if effective_id == str(canonical.id):
        return canonical

    return resolve_relationship_endpoint(effective_id, proposal) or canonical


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

        subject = _effective_endpoint(relationship.subject, effective["subject_id"], proposal)
        obj = _effective_endpoint(relationship.object, effective["object_id"], proposal)

        items.append(
            SimpleNamespace(
                id=relationship.id,
                relationship_type_id=relationship.relationship_type_id,
                subject_id=subject.id,
                subject_name=subject.name,
                subject_object_type_id=subject.object_type_id,
                object_id=obj.id,
                object_name=obj.name,
                object_object_type_id=obj.object_type_id,
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
            relationship_type_id=relationship_type.id,
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

    names = resolve_object_names(subject_object_ids, proposal)

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


# =====================================================================
# Discard cascade — Object -> Relationship
#
# A Relationship addresses its endpoints via after["subject_id"]/
# after["object_id"] in its own CREATE payload, not via parent_type/
# parent_id (that addresses the RelationshipType) — so this cascade
# has a different shape than the parent/child cascade used elsewhere
# for ObjectType->{AttributeDefinition,Object} and
# RelationshipType->{AttributeDefinition,RelationshipTypeRule,Relationship}.
# =====================================================================


def discard_relationships_referencing_object(proposal, object_id):
    """
    Discard any proposal-only (CREATE) Relationship whose subject_id
    or object_id references the given Object id, so discarding a
    proposal-only Object doesn't leave a dangling Relationship
    pointing at it. A pending endpoint UPDATE that re-points an
    existing Relationship at that Object is discarded too (just that
    field change — the Relationship itself stays).
    """

    if not proposal:
        return

    object_id = str(object_id)

    target_ids = set()
    endpoint_updates = set()

    for change in proposal.changes.filter(
        target_type="Relationship",
        operation__in=(
            ProposalChange.Operation.CREATE,
            ProposalChange.Operation.UPDATE,
        ),
    ):
        after = change.after or {}

        if change.operation == ProposalChange.Operation.UPDATE:
            if (
                after.get("field") in RELATIONSHIP_ENDPOINT_FIELDS
                and str(after.get("value")) == object_id
            ):
                endpoint_updates.add((change.target_id, after["field"]))
            continue

        if str(after.get("subject_id")) == object_id or str(after.get("object_id")) == object_id:
            target_ids.add(change.target_id)

    for target_id in target_ids:
        ProposalService.discard_change(
            proposal=proposal,
            target_type="Relationship",
            target_id=target_id,
        )

    for target_id, field in endpoint_updates:
        if target_id in target_ids:
            continue

        ProposalService.discard_change(
            proposal=proposal,
            target_type="Relationship",
            target_id=target_id,
            field=field,
        )
