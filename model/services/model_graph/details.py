"""
Details-panel data for a selected Object or Relationship.

Read-only and viewer-agnostic. When a ``projection`` is supplied, items carry
``inView`` flags so the UI can tell what the current filters are hiding and
offer to bring hidden connections into view.
"""

from __future__ import annotations

from .dataset import (
    AttributeSpec,
    EffectiveDataset,
    EffectiveObject,
    EffectiveRelationship,
    is_populated,
)
from .projection import Projection


def _display(spec: AttributeSpec, value) -> str | None:
    if not is_populated(value):
        return None
    if spec.data_type == "boolean":
        return "Yes" if value is True or str(value).lower() == "true" else "No"
    return str(value)


def _attributes(specs, values: dict) -> list[dict]:
    """Every defined attribute in definition order, populated or not."""
    return [
        {
            "key": spec.key,
            "label": spec.name,
            "dataType": spec.data_type,
            "value": values.get(spec.key),
            "display": _display(spec, values.get(spec.key)),
        }
        for spec in specs
    ]


def _in_view(projection: Projection | None, object_id: str):
    return None if projection is None else projection.contains_object(object_id)


def _object_ref(dataset: EffectiveDataset, obj: EffectiveObject, projection) -> dict:
    return {
        "id": obj.id,
        "name": obj.name,
        "typeId": obj.type_id,
        "typeName": dataset.object_types[obj.type_id].name,
        "isProposed": obj.is_proposed,
        "inView": _in_view(projection, obj.id),
    }


def object_details(dataset: EffectiveDataset, object_id, projection: Projection | None = None) -> dict | None:
    obj = dataset.object(object_id)
    if obj is None:
        return None

    object_type = dataset.object_types[obj.type_id]
    groups: dict[str, list] = {}
    hidden_counterparts: dict[str, None] = {}

    for relationship in dataset.relationships_of(obj.id):
        outgoing = relationship.source_id == obj.id
        counterpart = dataset.objects[relationship.target_id if outgoing else relationship.source_id]
        relationship_type = dataset.relationship_types[relationship.type_id]

        item = {
            "relationshipId": relationship.id,
            "direction": "outgoing" if outgoing else "incoming",
            "isProposed": relationship.is_proposed,
            "inView": None if projection is None else projection.contains_relationship(relationship.id),
            "counterpart": _object_ref(dataset, counterpart, projection),
            "attributes": [
                a for a in _attributes(relationship_type.attributes, relationship.attributes) if a["display"]
            ],
        }
        groups.setdefault(relationship_type.id, []).append(item)

        if counterpart.id != obj.id and _in_view(projection, counterpart.id) is False:
            hidden_counterparts[counterpart.id] = None

    return {
        "kind": "object",
        "id": obj.id,
        "name": obj.name,
        "description": obj.description,
        "type": {"id": object_type.id, "key": object_type.key, "name": object_type.name},
        "isProposed": obj.is_proposed,
        "isCreated": obj.is_created,
        "inView": _in_view(projection, obj.id),
        "attributes": _attributes(object_type.attributes, obj.attributes),
        "relationships": [
            {
                "type": {"id": type_id, "name": dataset.relationship_types[type_id].name},
                "items": sorted(items, key=lambda i: (i["counterpart"]["name"].lower(), i["relationshipId"])),
            }
            for type_id, items in (
                (tid, groups[tid]) for tid in dataset.relationship_types if tid in groups
            )
        ],
        "connectionCount": dataset.degree(obj.id),
        "hiddenConnectionIds": list(hidden_counterparts),
    }


def _cardinality(rule) -> dict | None:
    if rule is None:
        return None
    return {
        "subject": {"minimum": rule.subject_minimum, "maximum": rule.subject_maximum},
        "object": {"minimum": rule.object_minimum, "maximum": rule.object_maximum},
    }


def relationship_details(
    dataset: EffectiveDataset, relationship_id, projection: Projection | None = None
) -> dict | None:
    relationship: EffectiveRelationship | None = dataset.relationship(relationship_id)
    if relationship is None:
        return None

    relationship_type = dataset.relationship_types[relationship.type_id]
    return {
        "kind": "relationship",
        "id": relationship.id,
        "type": {"id": relationship_type.id, "key": relationship_type.key, "name": relationship_type.name},
        "source": _object_ref(dataset, dataset.objects[relationship.source_id], projection),
        "target": _object_ref(dataset, dataset.objects[relationship.target_id], projection),
        "attributes": _attributes(relationship_type.attributes, relationship.attributes),
        "validFrom": relationship.valid_from,
        "validTo": relationship.valid_to,
        "cardinality": _cardinality(dataset.rule_for(relationship)),
        "isProposed": relationship.is_proposed,
        "isCreated": relationship.is_created,
        "inView": None if projection is None else projection.contains_relationship(relationship.id),
    }
