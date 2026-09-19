"""
Pure projection: which part of the effective dataset belongs in the current
graph. No ORM, no viewer, no DOM, so a future list/table view can consume the
same ``Projection`` instead of a second data model.

Semantics:
  * hiding an Object Type hides its objects, and so any relationship that
    depended on them;
  * hiding a Relationship Type hides those relationships only, never their
    endpoint objects;
  * an attribute filter constrains objects of its own type only;
  * ``include`` ids are brought into view explicitly and override hiding and
    attribute filters (search results and "show connected" use this);
  * the projection is bounded: over ``limit`` objects, included ids are kept
    first, then the best connected, and ``truncated`` says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dataset import EffectiveDataset, EffectiveObject
from .query import ExplorerQuery


@dataclass(frozen=True)
class ProjectionSummary:
    total_objects: int
    total_relationships: int
    matching_objects: int  # before the size cap
    shown_objects: int
    shown_relationships: int
    hidden_by_object_type: int
    hidden_by_attribute_filter: int
    included_objects: int
    truncated: bool
    limit: int

    def to_dict(self) -> dict:
        return {
            "totalObjects": self.total_objects,
            "totalRelationships": self.total_relationships,
            "matchingObjects": self.matching_objects,
            "shownObjects": self.shown_objects,
            "shownRelationships": self.shown_relationships,
            "hiddenByObjectType": self.hidden_by_object_type,
            "hiddenByAttributeFilter": self.hidden_by_attribute_filter,
            "includedObjects": self.included_objects,
            "truncated": self.truncated,
            "limit": self.limit,
        }


@dataclass(frozen=True)
class Projection:
    object_ids: tuple
    relationship_ids: tuple
    included_ids: frozenset  # explicitly included objects that are in the projection
    summary: ProjectionSummary

    def contains_object(self, object_id) -> bool:
        return str(object_id) in self._object_set

    def contains_relationship(self, relationship_id) -> bool:
        return str(relationship_id) in self._relationship_set

    def __post_init__(self):
        object.__setattr__(self, "_object_set", frozenset(self.object_ids))
        object.__setattr__(self, "_relationship_set", frozenset(self.relationship_ids))


def _passes_filters(obj: EffectiveObject, query: ExplorerQuery) -> bool:
    return all(f.matches(obj.attributes.get(f.key)) for f in query.filters_for_type(obj.type_id))


def project(dataset: EffectiveDataset, query: ExplorerQuery) -> Projection:
    hidden_by_type = 0
    hidden_by_filter = 0
    matching: dict[str, EffectiveObject] = {}

    for obj in dataset.objects.values():
        included = obj.id in query.include
        if obj.type_id in query.hidden_object_types:
            if not included:
                hidden_by_type += 1
                continue
        elif not _passes_filters(obj, query) and not included:
            hidden_by_filter += 1
            continue
        matching[obj.id] = obj

    visible = matching
    truncated = len(matching) > query.limit
    if truncated:
        ranked = sorted(
            matching.values(),
            key=lambda o: (o.id not in query.include, -dataset.degree(o.id), o.name.lower(), o.id),
        )
        visible = {o.id: o for o in ranked[: query.limit]}

    relationship_ids = tuple(
        r.id
        for r in dataset.relationships.values()
        if r.type_id not in query.hidden_relationship_types
        and r.source_id in visible
        and r.target_id in visible
    )

    # Keep the dataset's stable (name, id) order rather than rank order.
    object_ids = tuple(oid for oid in dataset.objects if oid in visible)

    return Projection(
        object_ids=object_ids,
        relationship_ids=relationship_ids,
        included_ids=frozenset(oid for oid in query.include if oid in visible),
        summary=ProjectionSummary(
            total_objects=len(dataset.objects),
            total_relationships=len(dataset.relationships),
            matching_objects=len(matching),
            shown_objects=len(object_ids),
            shown_relationships=len(relationship_ids),
            hidden_by_object_type=hidden_by_type,
            hidden_by_attribute_filter=hidden_by_filter,
            included_objects=len([oid for oid in query.include if oid in dataset.objects]),
            truncated=truncated,
            limit=query.limit,
        ),
    )
