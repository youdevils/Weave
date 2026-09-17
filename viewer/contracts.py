"""
The generic Weave Viewer Payload contract.

This module is the stable boundary between "something that understands a
domain" (a future Model Graph Compiler, Publication Compiler, etc.) and the
viewer runtime. It must never import from `model`, `publication`, or any
other domain app, and must never reference Django ORM concepts. Anything a
future consumer needs to render must travel through `data`/`style`/`extra`
rather than by extending this module with domain-specific fields.

`style`/`viewer_config` values are already-resolved presentation data — this
module does not decide what anything should look like, it only describes the
shape that a resolved payload takes.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

VALID_LAYOUT_MODES = {"standard", "hierarchical"}
VALID_HIERARCHICAL_DIRECTIONS = {"UD", "DU", "LR", "RL"}
VALID_HIERARCHICAL_SORT_METHODS = {"hubsize", "directed"}


class ViewerPayloadError(Exception):
    """Raised when a ViewerPayload fails validation and the caller wants a hard failure."""


# ------------------------------------------------------------------------------------
# Presentation (already-resolved — the viewer only renders these values)
# ------------------------------------------------------------------------------------


@dataclass
class NodeStyle:
    shape: str | None = None
    background: str | None = None
    border: str | None = None
    border_width: float | None = None
    font: dict[str, Any] = field(default_factory=dict)
    size: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class EdgeStyle:
    colour: str | None = None
    width: float | None = None
    dashes: bool | list[int] | None = None
    arrows: str | dict[str, Any] | None = None
    font: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class TypeMetadata:
    """Optional descriptive metadata for a node/edge type_key.

    This is deliberately opaque to any particular domain — it is never a
    reference to an ObjectType/RelationshipType row, just a label/description
    a compiler may choose to attach for a given type_key.
    """

    key: str
    label: str | None = None
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ------------------------------------------------------------------------------------
# Graph
# ------------------------------------------------------------------------------------


@dataclass
class ViewerNode:
    id: str
    type_key: str
    label: str
    data: dict[str, Any] = field(default_factory=dict)
    style: NodeStyle = field(default_factory=NodeStyle)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ViewerEdge:
    id: str
    relationship_type_key: str
    source: str
    target: str
    label: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    style: EdgeStyle = field(default_factory=EdgeStyle)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ------------------------------------------------------------------------------------
# Viewer configuration (layout / physics / interaction)
# ------------------------------------------------------------------------------------


@dataclass
class HierarchicalLayoutConfig:
    direction: str = "UD"
    sort_method: str = "hubsize"
    level_separation: int | None = None
    node_spacing: int | None = None
    tree_spacing: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class LayoutConfig:
    mode: str = "standard"  # "standard" | "hierarchical"
    hierarchical: HierarchicalLayoutConfig = field(default_factory=HierarchicalLayoutConfig)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class StabilisationConfig:
    enabled: bool = True
    iterations: int | None = None
    fit: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class PhysicsConfig:
    enabled: bool = True
    solver: str | None = None  # "barnesHut" | "forceAtlas2Based" | "repulsion" | ...
    stabilisation: StabilisationConfig = field(default_factory=StabilisationConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class InteractionConfig:
    """Typed foundational interaction toggles.

    Deliberately not a raw passthrough dict of arbitrary vis-network
    interaction keys — only the settings we already know future consumers
    need are modeled explicitly; `extra` exists for forward compatibility
    only and is not rendered by the current translator.
    """

    hover: bool = False
    zoom_enabled: bool = True
    drag_view_enabled: bool = True
    drag_nodes_enabled: bool = True
    multi_select: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ViewerConfig:
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    interaction: InteractionConfig = field(default_factory=InteractionConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ViewerMetadata:
    title: str | None = None
    description: str | None = None
    source: str | None = None  # opaque origin tag, e.g. "model-explorer" — not a Publishing concept
    generated_at: str | None = None  # ISO 8601 string
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# ------------------------------------------------------------------------------------
# Payload
# ------------------------------------------------------------------------------------


@dataclass
class ViewerPayload:
    schema_version: str
    nodes: list[ViewerNode] = field(default_factory=list)
    edges: list[ViewerEdge] = field(default_factory=list)
    metadata: ViewerMetadata = field(default_factory=ViewerMetadata)
    viewer_config: ViewerConfig = field(default_factory=ViewerConfig)
    node_types: list[TypeMetadata] = field(default_factory=list)
    edge_types: list[TypeMetadata] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ViewerPayload:
        data = dict(data or {})

        metadata_data = dict(data.get("metadata") or {})
        viewer_config_data = dict(data.get("viewer_config") or {})
        layout_data = dict(viewer_config_data.get("layout") or {})
        hierarchical_data = dict(layout_data.get("hierarchical") or {})
        physics_data = dict(viewer_config_data.get("physics") or {})
        stabilisation_data = dict(physics_data.get("stabilisation") or {})
        interaction_data = dict(viewer_config_data.get("interaction") or {})

        nodes = [
            ViewerNode(
                id=node["id"],
                type_key=node["type_key"],
                label=node["label"],
                data=dict(node.get("data") or {}),
                style=NodeStyle(
                    shape=(node.get("style") or {}).get("shape"),
                    background=(node.get("style") or {}).get("background"),
                    border=(node.get("style") or {}).get("border"),
                    border_width=(node.get("style") or {}).get("border_width"),
                    font=dict((node.get("style") or {}).get("font") or {}),
                    size=(node.get("style") or {}).get("size"),
                    extra=dict((node.get("style") or {}).get("extra") or {}),
                ),
            )
            for node in data.get("nodes", [])
        ]

        edges = [
            ViewerEdge(
                id=edge["id"],
                relationship_type_key=edge["relationship_type_key"],
                source=edge["source"],
                target=edge["target"],
                label=edge.get("label"),
                data=dict(edge.get("data") or {}),
                style=EdgeStyle(
                    colour=(edge.get("style") or {}).get("colour"),
                    width=(edge.get("style") or {}).get("width"),
                    dashes=(edge.get("style") or {}).get("dashes"),
                    arrows=(edge.get("style") or {}).get("arrows"),
                    font=dict((edge.get("style") or {}).get("font") or {}),
                    extra=dict((edge.get("style") or {}).get("extra") or {}),
                ),
            )
            for edge in data.get("edges", [])
        ]

        node_types = [
            TypeMetadata(
                key=t["key"],
                label=t.get("label"),
                description=t.get("description"),
                extra=dict(t.get("extra") or {}),
            )
            for t in data.get("node_types", [])
        ]

        edge_types = [
            TypeMetadata(
                key=t["key"],
                label=t.get("label"),
                description=t.get("description"),
                extra=dict(t.get("extra") or {}),
            )
            for t in data.get("edge_types", [])
        ]

        return cls(
            schema_version=data["schema_version"],
            nodes=nodes,
            edges=edges,
            metadata=ViewerMetadata(
                title=metadata_data.get("title"),
                description=metadata_data.get("description"),
                source=metadata_data.get("source"),
                generated_at=metadata_data.get("generated_at"),
                extra=dict(metadata_data.get("extra") or {}),
            ),
            viewer_config=ViewerConfig(
                layout=LayoutConfig(
                    mode=layout_data.get("mode", "standard"),
                    hierarchical=HierarchicalLayoutConfig(
                        direction=hierarchical_data.get("direction", "UD"),
                        sort_method=hierarchical_data.get("sort_method", "hubsize"),
                        level_separation=hierarchical_data.get("level_separation"),
                        node_spacing=hierarchical_data.get("node_spacing"),
                        tree_spacing=hierarchical_data.get("tree_spacing"),
                    ),
                ),
                physics=PhysicsConfig(
                    enabled=physics_data.get("enabled", True),
                    solver=physics_data.get("solver"),
                    stabilisation=StabilisationConfig(
                        enabled=stabilisation_data.get("enabled", True),
                        iterations=stabilisation_data.get("iterations"),
                        fit=stabilisation_data.get("fit", True),
                    ),
                    extra=dict(physics_data.get("extra") or {}),
                ),
                interaction=InteractionConfig(
                    hover=interaction_data.get("hover", False),
                    zoom_enabled=interaction_data.get("zoom_enabled", True),
                    drag_view_enabled=interaction_data.get("drag_view_enabled", True),
                    drag_nodes_enabled=interaction_data.get("drag_nodes_enabled", True),
                    multi_select=interaction_data.get("multi_select", False),
                    extra=dict(interaction_data.get("extra") or {}),
                ),
                extra=dict(viewer_config_data.get("extra") or {}),
            ),
            node_types=node_types,
            edge_types=edge_types,
        )


# ------------------------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------------------------


def validate_payload(payload: ViewerPayload) -> list[str]:
    """Pure validation — returns a list of human-readable problems, empty means valid."""

    errors: list[str] = []

    if payload.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"unsupported schema_version: {payload.schema_version!r}")

    node_ids = [n.id for n in payload.nodes]
    if any(not node_id for node_id in node_ids):
        errors.append("node with empty id")
    if len(node_ids) != len(set(node_ids)):
        errors.append("duplicate node ids")

    node_id_set = set(node_ids)

    edge_ids = [e.id for e in payload.edges]
    if any(not edge_id for edge_id in edge_ids):
        errors.append("edge with empty id")
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("duplicate edge ids")

    for edge in payload.edges:
        if edge.source not in node_id_set:
            errors.append(f"edge {edge.id!r} source {edge.source!r} does not reference an existing node")
        if edge.target not in node_id_set:
            errors.append(f"edge {edge.id!r} target {edge.target!r} does not reference an existing node")

    layout = payload.viewer_config.layout
    if layout.mode not in VALID_LAYOUT_MODES:
        errors.append(f"unknown layout mode: {layout.mode!r}")

    if layout.hierarchical.direction not in VALID_HIERARCHICAL_DIRECTIONS:
        errors.append(f"unknown hierarchical direction: {layout.hierarchical.direction!r}")

    if layout.hierarchical.sort_method not in VALID_HIERARCHICAL_SORT_METHODS:
        errors.append(f"unknown hierarchical sort_method: {layout.hierarchical.sort_method!r}")

    return errors


def ensure_valid_payload(payload: ViewerPayload) -> None:
    errors = validate_payload(payload)
    if errors:
        raise ViewerPayloadError("; ".join(errors))
