"""
Filter facets: what the user can filter by, with counts.

Built from the *unfiltered* effective dataset, so the controls always describe
the whole model (a hidden type does not vanish from the panel that hides it).
"""

from __future__ import annotations

from collections import Counter

from model.services.appearance.viewer_adapter import node_style

from .dataset import EffectiveDataset, is_populated
from .query import OPERATOR_BY_DATA_TYPE


def _attribute_facet(spec, objects) -> dict:
    facet = {
        "key": spec.key,
        "name": spec.name,
        "dataType": spec.data_type,
        "op": OPERATOR_BY_DATA_TYPE.get(spec.data_type),
        "values": [],
    }

    if spec.data_type == "choice":
        counts = Counter(str(o.attributes.get(spec.key)) for o in objects if is_populated(o.attributes.get(spec.key)))
        facet["values"] = [{"value": choice, "count": counts.get(choice, 0)} for choice in spec.choices]
    elif spec.data_type == "boolean":
        counts = Counter(str(o.attributes.get(spec.key)).lower() for o in objects if is_populated(o.attributes.get(spec.key)))
        facet["values"] = [
            {"value": "true", "label": "Yes", "count": counts.get("true", 0)},
            {"value": "false", "label": "No", "count": counts.get("false", 0)},
        ]

    return facet


def _object_swatch(appearance, type_id):
    if appearance is None:
        return None
    resolved = appearance.object_type(type_id)
    # The icon image comes from the same adapter the graph uses, so the legend
    # glyph (and its colour) can never drift from what a node actually shows.
    style = node_style(resolved)
    return {
        "background": resolved.background,
        "border": resolved.border,
        "shape": resolved.shape,
        "icon": resolved.icon,
        "image": style.image,
    }


def _relationship_swatch(appearance, type_id):
    if appearance is None:
        return None
    resolved = appearance.relationship_type(type_id)
    return {"colour": resolved.colour, "lineStyle": resolved.line_style}


def build_facets(dataset: EffectiveDataset, appearance=None) -> dict:
    """
    ``appearance`` is an optional ``AppearanceResolver``. When given, each type
    carries a ``swatch`` of its resolved look so the filter controls show the
    same visual identity as the graph (never a separate definition of it).
    """
    objects_by_type: dict[str, list] = {t: [] for t in dataset.object_types}
    for obj in dataset.objects.values():
        objects_by_type[obj.type_id].append(obj)

    relationship_counts = Counter(r.type_id for r in dataset.relationships.values())

    return {
        "objectTypes": [
            {
                "id": object_type.id,
                "key": object_type.key,
                "name": object_type.name,
                "isProposed": object_type.is_proposed,
                "count": len(objects_by_type[object_type.id]),
                "swatch": _object_swatch(appearance, object_type.id),
                "attributes": [
                    _attribute_facet(spec, objects_by_type[object_type.id])
                    for spec in object_type.attributes
                    if spec.data_type in OPERATOR_BY_DATA_TYPE
                ],
            }
            for object_type in dataset.object_types.values()
        ],
        "relationshipTypes": [
            {
                "id": relationship_type.id,
                "key": relationship_type.key,
                "name": relationship_type.name,
                "isProposed": relationship_type.is_proposed,
                "count": relationship_counts.get(relationship_type.id, 0),
                "swatch": _relationship_swatch(appearance, relationship_type.id),
            }
            for relationship_type in dataset.relationship_types.values()
        ],
    }
