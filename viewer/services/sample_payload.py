"""
A small, static sample ViewerPayload used only to exercise the viewer
foundation (dev/test harness view, Python tests). This is deliberately not a
Model Explorer or anything domain-aware — just hand-built sample data.
"""

from __future__ import annotations

from viewer.contracts import (
    EdgeStyle,
    HierarchicalLayoutConfig,
    LayoutConfig,
    NodeStyle,
    TypeMetadata,
    ViewerConfig,
    ViewerEdge,
    ViewerMetadata,
    ViewerNode,
    ViewerPayload,
    SCHEMA_VERSION,
)


def build_sample_payload() -> ViewerPayload:
    nodes = [
        ViewerNode(
            id="node-1",
            type_key="sample.root",
            label="Root",
            data={"description": "A root sample node"},
            style=NodeStyle(shape="box", background="#4C6EF5", border="#364FC7", size=30),
        ),
        ViewerNode(
            id="node-2",
            type_key="sample.child",
            label="Child A",
            data={"description": "First child sample node"},
            style=NodeStyle(shape="ellipse", background="#63E6BE", border="#0CA678"),
        ),
        ViewerNode(
            id="node-3",
            type_key="sample.child",
            label="Child B",
            data={"description": "Second child sample node"},
            style=NodeStyle(shape="ellipse", background="#63E6BE", border="#0CA678"),
        ),
        ViewerNode(
            id="node-4",
            type_key="sample.leaf",
            label="Leaf",
            data={"description": "A leaf sample node"},
            style=NodeStyle(shape="dot", background="#FFD43B", border="#F08C00", size=15),
        ),
    ]

    edges = [
        ViewerEdge(
            id="edge-1",
            relationship_type_key="sample.parent_of",
            source="node-1",
            target="node-2",
            label="parent of",
            style=EdgeStyle(colour="#495057", width=2, arrows="to"),
        ),
        ViewerEdge(
            id="edge-2",
            relationship_type_key="sample.parent_of",
            source="node-1",
            target="node-3",
            label="parent of",
            style=EdgeStyle(colour="#495057", width=2, arrows="to"),
        ),
        ViewerEdge(
            id="edge-3",
            relationship_type_key="sample.parent_of",
            source="node-2",
            target="node-4",
            label="parent of",
            style=EdgeStyle(colour="#495057", width=1, dashes=True, arrows="to"),
        ),
    ]

    return ViewerPayload(
        schema_version=SCHEMA_VERSION,
        nodes=nodes,
        edges=edges,
        metadata=ViewerMetadata(
            title="Viewer foundation sample",
            description="Static sample payload used to exercise the Weave Viewer foundation.",
            source="viewer.services.sample_payload",
        ),
        viewer_config=ViewerConfig(
            layout=LayoutConfig(
                mode="hierarchical",
                hierarchical=HierarchicalLayoutConfig(direction="UD", sort_method="directed"),
            ),
        ),
        node_types=[
            TypeMetadata(key="sample.root", label="Root"),
            TypeMetadata(key="sample.child", label="Child"),
            TypeMetadata(key="sample.leaf", label="Leaf"),
        ],
        edge_types=[
            TypeMetadata(key="sample.parent_of", label="Parent of"),
        ],
    )
