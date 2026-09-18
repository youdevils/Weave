"""
Compiles a Model's effective ontology (Object Types + Relationship Type
Rules) into a viewer-agnostic ViewerPayload.

This is deliberately an *ontology* compiler, not a data compiler: it only
ever looks at ObjectType / RelationshipType / RelationshipTypeRule, never at
Object / Relationship instances.

"Effective ontology" reuses the same canonical + active-proposal overlay
used elsewhere on the Model Overview page (object/relationship type counts,
proposal-aware editors, etc). Rather than re-deriving that overlay logic
here, this module deliberately reuses the existing, tested helpers in
model.views.common_context. This is a contained reuse for this iteration,
not an endorsement of services depending on views long-term — those
helpers are not refactored or promoted as part of this change.
"""

from __future__ import annotations

from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal
from model.models.relationship_type import RelationshipType
from model.views.common_context import (
    _build_working_object_types,
    _build_working_relationship_types,
    _working_object_type_lookup,
)
from viewer.contracts import (
    EdgeStyle,
    NodeStyle,
    SCHEMA_VERSION,
    TypeMetadata,
    LayoutConfig,
    PhysicsConfig,
    StabilisationConfig,
    ViewerConfig,
    ViewerEdge,
    ViewerMetadata,
    ViewerNode,
    ViewerPayload,
)

# ------------------------------------------------------------------------------------
# Restrained, opinionated visual language — reuses the accent colours already
# established by viewer.services.sample_payload rather than inventing a new palette.
# ------------------------------------------------------------------------------------

NODE_TYPE_KEY = "object_type"
EDGE_TYPE_KEY = "relationship_type"

_CANONICAL_NODE_STYLE = {"shape": "box", "background": "#EDF2FF", "border": "#4C6EF5", "border_width": 1.5}
_PROPOSED_NODE_STYLE = {"shape": "box", "background": "#FFF3BF", "border": "#F08C00", "border_width": 1.5}
_NODE_FONT = {"color": "#212529", "size": 14}

_CANONICAL_EDGE_COLOUR = "#495057"
_PROPOSED_EDGE_COLOUR = "#F08C00"
_EDGE_FONT = {"color": "#495057", "size": 11}


def _node_style(is_proposed: bool) -> NodeStyle:
    base = _PROPOSED_NODE_STYLE if is_proposed else _CANONICAL_NODE_STYLE
    return NodeStyle(
        shape=base["shape"],
        background=base["background"],
        border=base["border"],
        border_width=base["border_width"],
        font=dict(_NODE_FONT),
    )


def _edge_style(is_proposed: bool) -> EdgeStyle:
    return EdgeStyle(
        colour=_PROPOSED_EDGE_COLOUR if is_proposed else _CANONICAL_EDGE_COLOUR,
        width=1.5,
        dashes=True if is_proposed else None,
        arrows="to",
        font=dict(_EDGE_FONT),
    )


def compile_ontology_graph(
    model: Model,
    proposal: Proposal | None = None,
) -> ViewerPayload:
    """Compile the effective ontology (canonical + active proposal overlay) of a Model."""

    canonical_object_types = ObjectType.objects.filter(model=model).order_by("sort_order", "name")
    canonical_relationship_types = RelationshipType.objects.filter(model=model).order_by("sort_order", "name")

    working_object_types = _build_working_object_types(canonical_object_types, proposal)
    object_type_lookup = _working_object_type_lookup(working_object_types)
    working_relationship_types = _build_working_relationship_types(
        canonical_relationship_types,
        proposal,
        object_type_lookup,
    )

    active_object_types = [object_type for object_type in working_object_types if object_type.is_active]
    active_node_ids = {str(object_type.id) for object_type in active_object_types}

    nodes = [
        ViewerNode(
            id=str(object_type.id),
            type_key=NODE_TYPE_KEY,
            label=object_type.name,
            data={
                "key": object_type.key,
                "description": object_type.description,
                "sort_order": object_type.sort_order,
                "is_proposed": object_type.is_proposed,
                "is_created": object_type.is_created,
            },
            style=_node_style(object_type.is_proposed),
        )
        for object_type in active_object_types
    ]

    edges: list[ViewerEdge] = []

    for relationship_type in working_relationship_types:

        if not relationship_type.is_active:
            continue

        for rule in relationship_type.rules:

            source_id = str(rule.subject_type_id)
            target_id = str(rule.object_type_id)

            if source_id not in active_node_ids or target_id not in active_node_ids:
                continue

            edges.append(
                ViewerEdge(
                    id=str(rule.id),
                    relationship_type_key=EDGE_TYPE_KEY,
                    source=source_id,
                    target=target_id,
                    label=relationship_type.name,
                    data={
                        "relationship_type_id": str(relationship_type.id),
                        "subject_minimum": rule.subject_minimum,
                        "subject_maximum": rule.subject_maximum,
                        "object_minimum": rule.object_minimum,
                        "object_maximum": rule.object_maximum,
                        "is_proposed": rule.is_proposed,
                        "is_created": rule.is_created,
                    },
                    style=_edge_style(rule.is_proposed),
                )
            )

    return ViewerPayload(
        schema_version=SCHEMA_VERSION,
        nodes=nodes,
        edges=edges,
        metadata=ViewerMetadata(
            title=f"{model.name} ontology",
            description="Object Types and Relationship Type Rules for this model.",
            source="model.services.ontology_graph.compiler",
        ),
        viewer_config=ViewerConfig(
            layout=LayoutConfig(mode="standard"),
            physics=PhysicsConfig(
                enabled=True,
                solver="forceAtlas2Based",
                stabilisation=StabilisationConfig(enabled=True, fit=True),
            ),
        ),
        node_types=[TypeMetadata(key=NODE_TYPE_KEY, label="Object Type")],
        edge_types=[TypeMetadata(key=EDGE_TYPE_KEY, label="Relationship Type")],
    )
