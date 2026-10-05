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
from publication.services.bundle import canonical_json

from ai.services.context_expansion import ExpansionState, initial_expansion_state
from ai.services.context_schema import ContextPacket
from ai.services.ontology_context import compile_ontology_context


def _issue_to_dict(issue) -> dict:
    """Tolerant conversion: accepts model.services.validation.result.ValidationIssue
    (code/message/field/target_type/target_id) or
    ai.services.change_plan.UnresolvedIssue (code/message/target_ref).

    Deliberately never includes target_id: it is always a canonical database
    UUID (model.services.validation.result.ValidationIssue.target_id), which
    must never cross into AI-facing context -- the semantic-key architecture
    (ai.services.change_plan's TARGET_DOMAIN/EntityRef) exists precisely to
    keep existing-entity references key/ref-based for the AI. message/field/
    target_type already fully describe the defect on their own (every
    ValidationIssue.message in this codebase is self-contained, human-
    readable prose naming the entity by name, not by id) -- there is no
    non-UUID substitute to add here because nothing besides the human
    Proposal-review UI ever needed target_id in the first place."""

    if hasattr(issue, "model_dump"):
        return issue.model_dump(mode="json")

    return {
        "code": getattr(issue, "code", ""),
        "message": getattr(issue, "message", ""),
        "field": getattr(issue, "field", None),
        "target_type": getattr(issue, "target_type", None),
    }


def _ranked_object_ids(dataset, object_ids, priority_ids=frozenset()) -> list[str]:
    def _name(object_id):
        obj = dataset.object(object_id)
        return obj.name.lower() if obj else ""

    return sorted(
        object_ids,
        key=lambda oid: (oid not in priority_ids, -dataset.degree(oid), _name(oid), oid),
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


def _reachable_object_ids(dataset, seed_object_ids) -> set[str]:
    """Hop-bounded only -- no longer separately trimmed to AI_CONTEXT_MAX_OBJECTS;
    build_context_packet's union-level trim handles the object-count ceiling
    once, uniformly, over the combined (base + expanded) set."""

    adjacency = _build_adjacency(dataset)
    return reachable_within(seed_object_ids, adjacency, settings.AI_CONTEXT_MAX_HOPS)


def _ref_for_object(dataset, object_id) -> str | None:
    obj = dataset.object(object_id)
    object_type = dataset.object_types.get(obj.type_id) if obj else None
    return f"{object_type.key}:{obj.key}" if obj and object_type else None


def _add_object_ref(ref_dict: dict, dataset) -> dict:
    """
    Enriches an _object_ref-shaped dict (id/name/typeId/typeName/
    isProposed/inView -- see model.services.model_graph.details) with the
    AI-facing `ref`/`typeKey` composite -- post-processing only, so
    model.services.model_graph.details stays completely untouched (it is
    also used by the live Explorer UI and by Publication's committed
    golden-fixture parity suite, neither of which should ever see an
    AI-specific field).
    """

    return {
        **ref_dict,
        "ref": _ref_for_object(dataset, ref_dict["id"]),
        "typeKey": dataset.object_types[ref_dict["typeId"]].key,
    }


def _enrich_object_payload(detail: dict, dataset) -> dict:
    return {
        **detail,
        "ref": _ref_for_object(dataset, detail["id"]),
        "relationships": [
            {
                **group,
                "items": [
                    {**item, "counterpart": _add_object_ref(item["counterpart"], dataset)}
                    for item in group["items"]
                ],
            }
            for group in detail["relationships"]
        ],
    }


def _enrich_relationship_payload(detail: dict, dataset) -> dict:
    # No top-level "ref" added here -- Relationship has no key or natural
    # uniqueness constraint that could back a safe synthetic one, so it
    # stays addressed by its real id (see ai.services.change_plan's domain
    # table: "relationship" is the one deliberate exception).
    return {
        **detail,
        "source": _add_object_ref(detail["source"], dataset),
        "target": _add_object_ref(detail["target"], dataset),
    }


def _payload_for(dataset, object_ids) -> tuple[list[dict], list[dict], int]:
    objects_payload = [
        _enrich_object_payload(d, dataset)
        for d in (object_details(dataset, oid) for oid in object_ids)
        if d is not None
    ]

    relationship_ids = {
        r.id
        for r in dataset.relationships.values()
        if r.source_id in object_ids and r.target_id in object_ids
    }
    relationships_payload = [
        _enrich_relationship_payload(d, dataset)
        for d in (relationship_details(dataset, rid) for rid in relationship_ids)
        if d is not None
    ]

    size = len(canonical_json({"objects": objects_payload, "relationships": relationships_payload}).encode("utf-8"))
    return objects_payload, relationships_payload, size


def _bounded_payload(dataset, object_ids, *, max_bytes) -> tuple[list[dict], list[dict], bool]:
    """Builds objects/relationships payloads for `object_ids`, trimming the
    least-connected objects first (same ranking project() already uses) if
    the serialised result exceeds `max_bytes` -- the byte budget left over
    for this section after the rest of the packet's fixed overhead
    (ontology, model metadata, intent, assets, previous-attempt issues) is
    accounted for. Deliberately plain degree/name ranking here, independent
    of any base-vs-expansion priority (see build_context_packet) -- the two
    ceilings (object count, byte size) are kept decoupled."""

    if max_bytes <= 0:
        return [], [], True

    ranked_ids = _ranked_object_ids(dataset, object_ids)
    kept = ranked_ids
    truncated = False

    while kept:
        objects_payload, relationships_payload, size = _payload_for(dataset, set(kept))
        if size <= max_bytes or len(kept) == 1:
            return objects_payload, relationships_payload, truncated or size > max_bytes
        truncated = True
        drop = max(1, len(kept) // 10)
        kept = kept[: len(kept) - drop]

    return [], [], truncated


def _skeleton_size(**packet_kwargs) -> int:
    """Serialised size of the packet with objects/relationships empty --
    the fixed overhead (ontology, model metadata, intent, assets,
    previous-attempt issues) that objects/relationships must share
    AI_CONTEXT_MAX_BYTES with."""

    skeleton = ContextPacket(**packet_kwargs, objects=[], relationships=[], byte_size=0)
    return len(canonical_json(skeleton.model_dump(mode="json")).encode("utf-8"))


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
    ontology_payload = compile_ontology_context(dataset)

    # Additive: the deterministic base slice is never discarded by an
    # expansion cycle, only ever added to -- see the module docstring and
    # _ranked_object_ids' priority_ids. Recomputing the base fresh each call
    # is safe and gives an identical result every time, since canonical
    # state doesn't change mid-operation (ai.services.orchestrator).
    base_ids, base_truncated = _initial_object_ids(dataset)

    if expansion_state.seed_object_ids:
        combined_ids = base_ids | _reachable_object_ids(dataset, expansion_state.seed_object_ids)
    else:
        combined_ids = set(base_ids)

    if len(combined_ids) > settings.AI_CONTEXT_MAX_OBJECTS:
        ranked = _ranked_object_ids(dataset, combined_ids, priority_ids=base_ids)
        object_ids = set(ranked[: settings.AI_CONTEXT_MAX_OBJECTS])
        object_limit_hit = True
    else:
        object_ids = combined_ids
        object_limit_hit = base_truncated

    previous_issues_payload = [_issue_to_dict(issue) for issue in previous_issues]
    assets_payload = list(assets)

    fixed_kwargs = dict(
        intent=intent.text,
        model_id=str(model.id),
        model_name=model.name,
        model_purpose=model.purpose,
        model_scope=model.scope,
        model_exclusions=model.exclusions,
        model_revision=model.revision,
        ontology=ontology_payload,
        assets=assets_payload,
        previous_attempt_issues=previous_issues_payload,
    )

    # AI_CONTEXT_MAX_BYTES bounds the WHOLE serialised packet, not just the
    # objects/relationships subsection -- give objects/relationships only
    # whatever budget remains after the rest of the packet's fixed overhead.
    overhead = _skeleton_size(**fixed_kwargs)
    overhead_exceeds_ceiling = overhead > settings.AI_CONTEXT_MAX_BYTES
    available_bytes = max(0, settings.AI_CONTEXT_MAX_BYTES - overhead)

    objects_payload, relationships_payload, byte_limit_hit = _bounded_payload(
        dataset, object_ids, max_bytes=available_bytes
    )

    model_is_empty = (
        not ontology_payload.get("object_types")
        and not ontology_payload.get("relationship_types")
        and not objects_payload
        and not relationships_payload
    )

    packet = ContextPacket(
        **fixed_kwargs,
        model_is_empty=model_is_empty,
        objects=objects_payload,
        relationships=relationships_payload,
        truncated=bool(object_limit_hit or byte_limit_hit or overhead_exceeds_ceiling),
        byte_size=0,
    )

    return packet.model_copy(
        update={"byte_size": len(canonical_json(packet.model_dump(mode="json")).encode("utf-8"))}
    )
