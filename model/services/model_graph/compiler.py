"""
Model Graph Compiler: turns a *projection* of the effective dataset into a
viewer-agnostic ViewerPayload.

It answers "what data belongs in the current graph?" and nothing else. What
the user is investigating (search, selection, filters) is the query/controller
concern; how the payload is drawn is the viewer's.

Visual identity is not decided here. Every node/edge takes its type's resolved
appearance from AppearanceService through the shared viewer adapter, so an
Object Type looks exactly the same here as in the ontology Overview. Only the
restrained proposal cue (amber) is applied on top, for records the active
proposal touches.
"""

from __future__ import annotations

from model.services.appearance import AppearanceService
from model.services.appearance.viewer_adapter import edge_style, node_style
from viewer.contracts import (
    SCHEMA_VERSION,
    LayoutConfig,
    PhysicsConfig,
    StabilisationConfig,
    TypeMetadata,
    ViewerConfig,
    ViewerEdge,
    ViewerMetadata,
    ViewerNode,
    ViewerPayload,
)

from .dataset import EffectiveDataset, is_populated
from .projection import Projection


def _populated_attributes(specs, values: dict) -> dict:
    return {spec.key: values[spec.key] for spec in specs if is_populated(values.get(spec.key))}


def compile_model_graph(model, dataset: EffectiveDataset, projection: Projection) -> ViewerPayload:
    appearance = AppearanceService.resolver(model)

    nodes = []
    for object_id in projection.object_ids:
        obj = dataset.objects[object_id]
        object_type = dataset.object_types[obj.type_id]
        nodes.append(
            ViewerNode(
                id=obj.id,
                type_key=object_type.key,
                label=obj.name,
                data={
                    "object_type_id": object_type.id,
                    "object_type_name": object_type.name,
                    "is_proposed": obj.is_proposed,
                    "is_created": obj.is_created,
                    "attributes": _populated_attributes(object_type.attributes, obj.attributes),
                },
                style=node_style(appearance.object_type(object_type.id), is_proposed=obj.is_proposed),
            )
        )

    edges = []
    for relationship_id in projection.relationship_ids:
        relationship = dataset.relationships[relationship_id]
        relationship_type = dataset.relationship_types[relationship.type_id]
        edges.append(
            ViewerEdge(
                id=relationship.id,
                relationship_type_key=relationship_type.key,
                # Direction is the relationship's: subject -> object.
                source=relationship.source_id,
                target=relationship.target_id,
                label=relationship_type.name,
                data={
                    "relationship_type_id": relationship_type.id,
                    "is_proposed": relationship.is_proposed,
                    "is_created": relationship.is_created,
                    "attributes": _populated_attributes(relationship_type.attributes, relationship.attributes),
                },
                style=edge_style(
                    appearance.relationship_type(relationship_type.id),
                    is_proposed=relationship.is_proposed,
                ),
            )
        )

    return ViewerPayload(
        schema_version=SCHEMA_VERSION,
        nodes=nodes,
        edges=edges,
        metadata=ViewerMetadata(
            title=f"{model.name} explorer",
            description="Objects and Relationships of this model.",
            source="model.services.model_graph.compiler",
        ),
        viewer_config=ViewerConfig(
            layout=LayoutConfig(mode="standard"),
            physics=PhysicsConfig(
                enabled=True,
                solver="forceAtlas2Based",
                stabilisation=StabilisationConfig(enabled=True, fit=True),
            ),
            # Host-page concern; the viewer does not interpret ``extra``.
            extra={"canvas_background": appearance.theme.canvas_background},
        ),
        node_types=[TypeMetadata(key=t.key, label=t.name) for t in dataset.object_types.values()],
        edge_types=[TypeMetadata(key=t.key, label=t.name) for t in dataset.relationship_types.values()],
    )
