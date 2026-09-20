"""
Applying a publication scope to the canonical dataset.

Pure: no ORM, no request, no appearance. The published dataset it returns is
the single definition of "what is in the file"; the preview and the publish
step both call it, so they can never disagree.

Order of operations (exclusions always win, so nothing excluded can be pulled
back in by a starting object or a connection):

  1. drop objects of excluded object types, and objects failing an attribute
     filter of their own type;
  2. drop relationships of excluded relationship types, or whose endpoints
     were dropped;
  3. if starting objects are set, keep only what is reachable from them within
     ``depth`` hops over the remaining relationships (either direction), plus
     the relationships among the kept objects.

Whatever comes out is canonical by construction and never carries a proposal
marker, even if the input did. Attribute values are also reduced to what the
published Explorer can actually show: only populated values of attributes the
type currently defines (so data of a removed or deactivated attribute is never
embedded), with whole-number floats written as integers so every consumer
renders them identically.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace

from model.services.model_graph.dataset import EffectiveDataset, is_populated

from .config import PublicationScope


def _passes_filters(obj, filters_by_type) -> bool:
    return all(f.matches(obj.attributes.get(f.key)) for f in filters_by_type.get(obj.type_id, ()))


def _normalised_number(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def clean_attributes(specs, values) -> dict:
    """The published form of a record's attribute values (see the module docstring)."""
    values = values if isinstance(values, dict) else {}
    return {
        spec.key: _normalised_number(values[spec.key])
        for spec in specs
        if is_populated(values.get(spec.key))
    }


def _reachable(roots, adjacency, depth):
    """Objects within ``depth`` hops of ``roots`` (unlimited when ``depth`` is None)."""
    seen = set(roots)
    frontier = deque((root, 0) for root in roots)
    while frontier:
        current, distance = frontier.popleft()
        if depth is not None and distance >= depth:
            continue
        for neighbour in adjacency.get(current, ()):
            if neighbour not in seen:
                seen.add(neighbour)
                frontier.append((neighbour, distance + 1))
    return seen


def apply_scope(dataset: EffectiveDataset, scope: PublicationScope) -> EffectiveDataset:
    excluded_object_types = set(scope.excluded_object_types)
    excluded_relationship_types = set(scope.excluded_relationship_types)

    filters_by_type: dict[str, list] = {}
    for attribute_filter in scope.attribute_filters:
        filters_by_type.setdefault(attribute_filter.type_id, []).append(attribute_filter)

    kept = {
        obj.id
        for obj in dataset.objects.values()
        if obj.type_id not in excluded_object_types and _passes_filters(obj, filters_by_type)
    }

    relationships = [
        r
        for r in dataset.relationships.values()
        if r.type_id not in excluded_relationship_types and r.source_id in kept and r.target_id in kept
    ]

    roots = [root for root in scope.roots if root in kept]
    if scope.roots:
        adjacency: dict[str, list] = {}
        for r in relationships:
            adjacency.setdefault(r.source_id, []).append(r.target_id)
            adjacency.setdefault(r.target_id, []).append(r.source_id)
        kept = _reachable(roots, adjacency, scope.depth)
        relationships = [r for r in relationships if r.source_id in kept and r.target_id in kept]

    surviving_object_types = {
        type_id: t for type_id, t in dataset.object_types.items() if type_id not in excluded_object_types
    }
    surviving_relationship_types = {
        type_id: replace(
            t,
            is_proposed=False,
            # Rules naming an excluded object type would only leak that type's id.
            rules=tuple(
                rule
                for rule in t.rules
                if rule.subject_type_id in surviving_object_types and rule.object_type_id in surviving_object_types
            ),
        )
        for type_id, t in dataset.relationship_types.items()
        if type_id not in excluded_relationship_types
    }

    return EffectiveDataset(
        object_types=[replace(t, is_proposed=False) for t in surviving_object_types.values()],
        relationship_types=list(surviving_relationship_types.values()),
        objects=[
            replace(
                o,
                is_proposed=False,
                is_created=False,
                attributes=clean_attributes(dataset.object_types[o.type_id].attributes, o.attributes),
            )
            for o in dataset.objects.values()
            if o.id in kept
        ],
        relationships=[
            replace(
                r,
                is_proposed=False,
                is_created=False,
                attributes=clean_attributes(dataset.relationship_types[r.type_id].attributes, r.attributes),
            )
            for r in relationships
        ],
    )
