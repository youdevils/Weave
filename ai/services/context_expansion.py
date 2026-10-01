"""
Context expansion stays entirely OnyxJar-controlled: the AI can only name a
specific existing reference it believes it needs more context about
(AIStructuredResult.context_requests); OnyxJar alone decides whether that
reference is real and how much more to supply. No generic AI-controlled
retrieval, tool calling, or function-calling layer.

Key invariant: expansion seeds must use the same entity domain as the
reachability graph being traversed. reachable_within (model.services.
model_graph.reachability) operates purely on an *object* adjacency graph, so
a ContextRequest naming a Relationship is translated to that relationship's
two endpoint Object ids before it ever reaches the BFS -- a relationship id
is never passed into an object-oriented traversal. The requested
relationship reappears in the expanded context without further
special-casing: ai.services.context_builder only includes a relationship
once both of its endpoint objects are in the included object set.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ai.services.change_plan import EntityRef, UnresolvedIssue
from ai.services.result_schema import ContextRequest


@dataclass(frozen=True)
class ExpansionState:
    seed_object_ids: frozenset = frozenset()


def initial_expansion_state() -> ExpansionState:
    return ExpansionState()


def expand(state: ExpansionState, new_seed_object_ids) -> ExpansionState:
    return replace(
        state,
        seed_object_ids=state.seed_object_ids | frozenset(new_seed_object_ids),
    )


@dataclass(frozen=True)
class ExpansionResolution:
    seeds: list
    unresolved: list


def resolve_context_requests(requests: list[ContextRequest], *, dataset) -> ExpansionResolution:
    seeds: set[str] = set()
    unresolved: list[UnresolvedIssue] = []

    for request in requests:
        ref = request.reference

        if ref.kind != "existing":
            unresolved.append(
                UnresolvedIssue(
                    code="unresolvable_context_reference",
                    message=f"'{ref.id}' is not an existing reference OnyxJar can expand context around.",
                    target_ref=ref,
                )
            )
            continue

        obj = dataset.object(ref.id)
        if obj is not None:
            seeds.add(obj.id)
            continue

        relationship = dataset.relationship(ref.id)
        if relationship is not None:
            # Translate to the object domain reachable_within understands --
            # see the module docstring.
            seeds.add(relationship.source_id)
            seeds.add(relationship.target_id)
            continue

        unresolved.append(
            UnresolvedIssue(
                code="unresolvable_context_reference",
                message=f"No Object or Relationship with id '{ref.id}' exists.",
                target_ref=ref,
            )
        )

    return ExpansionResolution(seeds=list(seeds), unresolved=unresolved)
