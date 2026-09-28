"""
Loads the effective dataset (canonical model + active proposal) for a Model.

This deliberately does not invent another proposal overlay. It reuses:

  * the working-type builders in ``model.views.common_context`` (ontology overlay,
    the same contained reuse ``ontology_graph.compiler`` documents);
  * ``model.views.data_context.apply_field_updates`` for Object/Relationship
    field and attribute overlays, and its attribute-definition builders.

The one addition is *bulk* access: all of the proposal's Object/Relationship
changes are fetched in a single query and indexed by target, so the number of
queries does not grow with the number of records (the per-record helpers issue
queries per record when a proposal is active).

Proposal semantics matched here:
  * UPDATE/CREATE overlays as elsewhere in the data views;
  * a proposed deactivation is an ``is_active`` UPDATE (excluded once applied);
  * an Object/Relationship DELETE change removes the record. The editors only
    ever deactivate, but submission also applies DELETE, so the effective view
    honours it to match what approval would produce.
"""

from __future__ import annotations

from collections import defaultdict

from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.views.common_context import (
    _build_working_object_types,
    _build_working_relationship_types,
    _working_object_type_lookup,
)
from model.views.data_context import (
    _canonical_object_values,
    _canonical_relationship_values,
    apply_field_updates,
    build_object_attribute_definitions,
    build_relationship_attribute_definitions,
)

from .dataset import (
    AttributeSpec,
    CardinalityRule,
    EffectiveDataset,
    EffectiveObject,
    EffectiveObjectType,
    EffectiveRelationship,
    EffectiveRelationshipType,
)

Operation = ProposalChange.Operation


class _ChangeIndex:
    """One query, indexed by (target_type, target_id)."""

    def __init__(self, proposal):
        self.updates = defaultdict(list)
        self.deleted = set()
        self.touched = set()
        self.creates = defaultdict(list)  # target_type -> [change]

        if not proposal:
            return

        changes = proposal.changes.filter(
            target_type__in=("Object", "Relationship"),
        ).order_by("created_at")

        for change in changes:
            if change.target_id is None:
                continue
            key = (change.target_type, str(change.target_id))
            self.touched.add(key)
            if change.operation == Operation.UPDATE:
                self.updates[key].append(change)
            elif change.operation == Operation.DELETE:
                self.deleted.add(key)
            elif change.operation == Operation.CREATE:
                self.creates[change.target_type].append(change)


def _attribute_specs(definitions) -> tuple[AttributeSpec, ...]:
    specs = []
    for definition in definitions:
        # The builders filter is_active before applying pending UPDATEs, so a
        # proposed deactivation is only visible on the returned object.
        if not getattr(definition, "is_active", True):
            continue
        config = getattr(definition, "config", None) or {}
        specs.append(
            AttributeSpec(
                key=definition.key,
                name=definition.name or definition.key,
                data_type=str(definition.data_type),
                choices=tuple(config.get("choices") or ()),
            )
        )
    return tuple(specs)


def _load_types(model, proposal, keep_inactive_types=False):
    working_object_types = _build_working_object_types(
        ObjectType.objects.filter(model=model).order_by("sort_order", "name"),
        proposal,
    )
    lookup = _working_object_type_lookup(working_object_types)
    working_relationship_types = _build_working_relationship_types(
        RelationshipType.objects.filter(model=model).order_by("sort_order", "name"),
        proposal,
        lookup,
    )

    object_types = [
        EffectiveObjectType(
            id=str(t.id),
            key=t.key,
            name=t.name,
            is_proposed=bool(t.is_proposed),
            attributes=_attribute_specs(build_object_attribute_definitions(t, proposal)),
        )
        for t in working_object_types
        if t.is_active or keep_inactive_types
    ]
    known_object_type_ids = {t.id for t in object_types}
    inactive = {str(t.id) for t in working_object_types if not t.is_active} if keep_inactive_types else set()

    relationship_types = [
        EffectiveRelationshipType(
            id=str(t.id),
            key=t.key,
            name=t.name,
            is_proposed=bool(t.is_proposed),
            attributes=_attribute_specs(build_relationship_attribute_definitions(t, proposal)),
            rules=tuple(
                CardinalityRule(
                    subject_type_id=str(rule.subject_type_id),
                    object_type_id=str(rule.object_type_id),
                    subject_minimum=rule.subject_minimum,
                    subject_maximum=rule.subject_maximum,
                    object_minimum=rule.object_minimum,
                    object_maximum=rule.object_maximum,
                )
                for rule in t.rules
                if not getattr(rule, "is_deleted", False)
            ),
        )
        for t in working_relationship_types
        if t.is_active or keep_inactive_types
    ]

    if keep_inactive_types:
        inactive |= {str(t.id) for t in working_relationship_types if not t.is_active}

    # ``inactive``: the ids of the inactive types kept only if they turn out to hold active records.
    return object_types, relationship_types, known_object_type_ids, inactive


def _load_objects(model, changes, known_object_type_ids):
    objects = []
    canonical_ids = set()

    # Not filtered on is_active in SQL: a proposed reactivation must be honoured.
    for obj in Object.objects.filter(model=model).only(
        "id", "object_type_id", "name", "description", "attributes", "is_active"
    ):
        key = ("Object", str(obj.id))
        canonical_ids.add(key[1])
        if key in changes.deleted:
            continue
        values = apply_field_updates(_canonical_object_values(obj), changes.updates.get(key, []))
        if not values["is_active"]:
            continue
        objects.append(
            EffectiveObject(
                id=key[1],
                type_id=str(obj.object_type_id),
                name=values["name"],
                description=values["description"] or "",
                attributes=values["attributes"],
                is_proposed=key in changes.touched,
            )
        )

    for change in changes.creates.get("Object", []):
        object_id = str(change.target_id)
        key = ("Object", object_id)
        if object_id in canonical_ids or key in changes.deleted:
            continue
        after = change.after or {}
        values = apply_field_updates(
            {
                "name": after.get("name") or "Untitled",
                "description": after.get("description") or "",
                "is_active": after.get("is_active", True),
                "attributes": dict(after.get("attributes") or {}),
            },
            changes.updates.get(key, []),
        )
        if not values["is_active"] or change.parent_id is None:
            continue
        objects.append(
            EffectiveObject(
                id=object_id,
                type_id=str(change.parent_id),
                name=values["name"],
                description=values["description"],
                attributes=values["attributes"],
                is_proposed=True,
                is_created=True,
            )
        )

    return [o for o in objects if o.type_id in known_object_type_ids]


def _load_relationships(model, changes):
    relationships = []
    canonical_ids = set()

    for relationship in Relationship.objects.filter(model=model).only(
        "id",
        "relationship_type_id",
        "subject_id",
        "object_id",
        "attributes",
        "is_active",
        "valid_from",
        "valid_to",
    ):
        key = ("Relationship", str(relationship.id))
        canonical_ids.add(key[1])
        if key in changes.deleted:
            continue
        values = apply_field_updates(
            _canonical_relationship_values(relationship), changes.updates.get(key, [])
        )
        if not values["is_active"]:
            continue
        relationships.append(
            EffectiveRelationship(
                id=key[1],
                type_id=str(relationship.relationship_type_id),
                # Effective endpoints: a pending UPDATE may re-point either one.
                source_id=values["subject_id"],
                target_id=values["object_id"],
                attributes=values["attributes"],
                valid_from=relationship.valid_from.isoformat() if relationship.valid_from else None,
                valid_to=relationship.valid_to.isoformat() if relationship.valid_to else None,
                is_proposed=key in changes.touched,
            )
        )

    for change in changes.creates.get("Relationship", []):
        relationship_id = str(change.target_id)
        key = ("Relationship", relationship_id)
        if relationship_id in canonical_ids or key in changes.deleted:
            continue
        after = change.after or {}
        values = apply_field_updates(
            {
                "is_active": after.get("is_active", True),
                "attributes": dict(after.get("attributes") or {}),
            },
            changes.updates.get(key, []),
        )
        if not values["is_active"] or change.parent_id is None:
            continue
        # Endpoints are raw string ids in the payload; the dataset drops the
        # relationship if either endpoint is not an effective object.
        relationships.append(
            EffectiveRelationship(
                id=relationship_id,
                type_id=str(change.parent_id),
                source_id=str(after.get("subject_id") or ""),
                target_id=str(after.get("object_id") or ""),
                attributes=values["attributes"],
                is_proposed=True,
                is_created=True,
            )
        )

    return relationships


def load_effective_dataset(model, proposal=None, *, keep_inactive_types=False) -> EffectiveDataset:
    """
    Effective (canonical + proposal) active Objects and Relationships of a Model.

    By default an inactive (retired) type is left out together with everything
    of that type. With ``keep_inactive_types`` the *active* records of an
    inactive type are kept along with the type itself, so they can still be
    published; an inactive type left with no active records is still omitted
    (there is nothing to describe or publish), while an active type is always
    kept, even when it has none.
    """
    object_types, relationship_types, known_object_type_ids, inactive = _load_types(
        model, proposal, keep_inactive_types
    )
    changes = _ChangeIndex(proposal)

    dataset = EffectiveDataset(
        object_types=object_types,
        relationship_types=relationship_types,
        objects=_load_objects(model, changes, known_object_type_ids),
        relationships=_load_relationships(model, changes),
    )
    if not inactive:
        return dataset

    # Judged on what survived the dataset's own invariants (known type, both endpoints present).
    used = {o.type_id for o in dataset.objects.values()} | {r.type_id for r in dataset.relationships.values()}
    unused = inactive - used
    if not unused:
        return dataset
    return EffectiveDataset(
        object_types=[t for t in dataset.object_types.values() if t.id not in unused],
        relationship_types=[t for t in dataset.relationship_types.values() if t.id not in unused],
        objects=list(dataset.objects.values()),
        relationships=list(dataset.relationships.values()),
    )
