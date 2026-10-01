"""
Deterministic, bounded assembly of a ContextPacket from canonical model
state. No ranking/embeddings/semantic search -- cycle 1 reuses the
Explorer's own existing included-first/-degree/name/id ranking
(model.services.model_graph.query.project) to pick a deterministic,
structurally-significant slice with no seed objects; later cycles expand a
bounded neighbourhood around AI-identified, OnyxJar-resolved seeds (see
ai.services.context_expansion).
"""

from __future__ import annotations

from django.conf import settings

from model.services.model_graph.details import object_details, relationship_details
from model.services.model_graph.loader import load_effective_dataset
from model.services.model_graph.projection import project
from model.services.model_graph.query import ExplorerQuery
from model.services.model_graph.reachability import reachable_within
from model.services.ontology_graph.compiler import compile_ontology_graph
from publication.services.bundle import canonical_json

from ai.services.context_expansion import ExpansionState, initial_expansion_state
from ai.services.context_schema import ContextPacket


def _issue_to_dict(issue) -> dict:
    """Tolerant conversion: accepts model.services.validation.result.ValidationIssue
    (code/message/field/target_type/target_id) or
    ai.services.change_plan.UnresolvedIssue (code/message/target_ref)."""

    if hasattr(issue, "model_dump"):
        return issue.model_dump(mode="json")

    return {
        "code": getattr(issue, "code", ""),
        "message": getattr(issue, "message", ""),
        "field": getattr(issue, "field", None),
        "target_type": getattr(issue, "target_type", None),
        "target_id": str(getattr(issue, "target_id", "")) or None,
    }


def _ranked_object_ids(dataset, object_ids) -> list[str]:
    def _name(object_id):
        obj = dataset.object(object_id)
        return obj.name.lower() if obj else ""

    return sorted(
        object_ids,
        key=lambda oid: (-dataset.degree(oid), _name(oid), oid),
    )


def _build_adjacency(dataset) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {}
    for relationship in dataset.relationships.values():
        adjacency.setdefault(relationship.source_id, []).append(relationship.target_id)
        if relationship.target_id != relationship.source_id:
            adjacency.setdefault(relationship.target_id, []).append(relationship.source_id)
    return adjacency


def _initial_object_ids(dataset) -> tuple[set[str], bool]:
    query = ExplorerQuery(limit=settings.AI_CONTEXT_MAX_OBJECTS)
    projection = project(dataset, query)
    return set(projection.object_ids), projection.summary.truncated


def _expanded_object_ids(dataset, seed_object_ids) -> tuple[set[str], bool]:
    adjacency = _build_adjacency(dataset)
    reached = reachable_within(seed_object_ids, adjacency, settings.AI_CONTEXT_MAX_HOPS)
    if len(reached) <= settings.AI_CONTEXT_MAX_OBJECTS:
        return reached, False
    ranked = _ranked_object_ids(dataset, reached)
    return set(ranked[: settings.AI_CONTEXT_MAX_OBJECTS]), True


def _payload_for(dataset, object_ids) -> tuple[list[dict], list[dict], int]:
    objects_payload = [d for d in (object_details(dataset, oid) for oid in object_ids) if d is not None]

    relationship_ids = {
        r.id
        for r in dataset.relationships.values()
        if r.source_id in object_ids and r.target_id in object_ids
    }
    relationships_payload = [
        d for d in (relationship_details(dataset, rid) for rid in relationship_ids) if d is not None
    ]

    size = len(canonical_json({"objects": objects_payload, "relationships": relationships_payload}).encode("utf-8"))
    return objects_payload, relationships_payload, size


def _bounded_payload(dataset, object_ids) -> tuple[list[dict], list[dict], bool]:
    """Builds objects/relationships payloads for `object_ids`, trimming the
    least-connected objects first (same ranking project() already uses) if
    the serialised result exceeds AI_CONTEXT_MAX_BYTES."""

    ranked_ids = _ranked_object_ids(dataset, object_ids)
    kept = ranked_ids
    truncated = False

    while kept:
        objects_payload, relationships_payload, size = _payload_for(dataset, set(kept))
        if size <= settings.AI_CONTEXT_MAX_BYTES or len(kept) == 1:
            return objects_payload, relationships_payload, truncated or size > settings.AI_CONTEXT_MAX_BYTES
        truncated = True
        drop = max(1, len(kept) // 10)
        kept = kept[: len(kept) - drop]

    return [], [], truncated


def build_context_packet(
    *,
    model,
    intent,
    assets=(),
    previous_issues=(),
    expansion_state: ExpansionState | None = None,
) -> ContextPacket:
    expansion_state = expansion_state or initial_expansion_state()

    dataset = load_effective_dataset(model, proposal=None)
    ontology_payload = compile_ontology_graph(model, proposal=None).to_dict()

    if expansion_state.seed_object_ids:
        object_ids, limit_hit = _expanded_object_ids(dataset, expansion_state.seed_object_ids)
    else:
        object_ids, limit_hit = _initial_object_ids(dataset)

    objects_payload, relationships_payload, byte_limit_hit = _bounded_payload(dataset, object_ids)

    packet = ContextPacket(
        intent=intent.text,
        model_id=str(model.id),
        model_name=model.name,
        model_purpose=model.purpose,
        model_scope=model.scope,
        model_exclusions=model.exclusions,
        model_revision=model.revision,
        ontology=ontology_payload,
        objects=objects_payload,
        relationships=relationships_payload,
        assets=list(assets),
        previous_attempt_issues=[_issue_to_dict(issue) for issue in previous_issues],
        truncated=bool(limit_hit or byte_limit_hit),
        byte_size=0,
    )

    return packet.model_copy(
        update={"byte_size": len(canonical_json(packet.model_dump(mode="json")).encode("utf-8"))}
    )
