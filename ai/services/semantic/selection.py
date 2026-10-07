"""
Deterministic assembly of the canonical context an AI-authored ChangeSet
(Create's Planning) reasons over: the catalogue plus, bounded, the model's
records. Reconcile no longer hands canonical records to a planner at all --
its identity and closure decisions are OnyxJar's (ai.services.reconcile).

Everything is bounded by AI_CONTEXT_MAX_OBJECTS / AI_CONTEXT_MAX_BYTES;
anything trimmed is listed in `truncated_types` (OnyxJar's duplicate checks
in ai.services.resolution are the deterministic backstop for whatever the AI
could not see).
"""

from __future__ import annotations

import json

from django.conf import settings
from pydantic import BaseModel, Field

from ai.services.semantic.catalogue import OntologyCatalogue, build_catalogue
from ai.services.semantic.index import IObject, SemanticModelIndex
from ai.services.semantic.records import ObjectRecord, RelationshipRecord, object_record, relationship_record


class SemanticContext(BaseModel):
    catalogue: OntologyCatalogue
    objects: list[ObjectRecord] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    # Types whose records were not all supplied -- absence from `objects` is
    # not proof of absence from the model for these.
    truncated_types: list[str] = Field(default_factory=list)


def _size(payload: BaseModel) -> int:
    return len(json.dumps(payload.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8"))


def _records(index, object_ids) -> tuple[list[ObjectRecord], list[RelationshipRecord]]:
    objects = [index.objects[oid] for oid in object_ids]
    objects.sort(key=lambda o: (index.object_types[o.type_id].key, o.name.lower(), o.key))
    relationships = [
        r for r in index.relationships.values() if r.subject_id in object_ids and r.object_id in object_ids
    ]
    relationships.sort(key=lambda r: (index.relationship_types[r.type_id].key, r.subject_id, r.object_id, r.id))
    return [object_record(index, o) for o in objects], [relationship_record(index, r) for r in relationships]


def _bounded(index, catalogue, by_type: dict[str, list[IObject]]) -> SemanticContext:
    """Fits the records into AI_CONTEXT_MAX_OBJECTS / AI_CONTEXT_MAX_BYTES,
    trimming the largest types first and naming every trimmed type."""

    limit = settings.AI_CONTEXT_MAX_OBJECTS
    truncated = set()
    selected = {oid for objects in by_type.values() for oid in (o.id for o in objects)}

    def build():
        objects, relationships = _records(index, selected)
        return SemanticContext(catalogue=catalogue, objects=objects, relationships=relationships, truncated_types=sorted(truncated))

    def trim_once() -> bool:
        trimmable = sorted(
            ((type_id, [o for o in by_type[type_id] if o.id in selected]) for type_id in by_type),
            key=lambda item: -len(item[1]),
        )
        if not trimmable or not trimmable[0][1]:
            return False
        type_id, candidates = trimmable[0]
        drop = max(1, len(candidates) // 4)
        for obj in candidates[-drop:]:
            selected.discard(obj.id)
        truncated.add(index.object_types[type_id].key)
        return True

    while len(selected) > limit and trim_once():
        pass
    context = build()
    while _size(context) > settings.AI_CONTEXT_MAX_BYTES and trim_once():
        context = build()
    return context


def select_full_context(index: SemanticModelIndex) -> SemanticContext:
    """Every type and (bounded) every record -- Create's context, where the
    model is a fresh bootstrap and usually empty."""

    by_type = {type_id: index.objects_of_type(type_id) for type_id in index.object_types}
    return _bounded(index, build_catalogue(index), by_type)
