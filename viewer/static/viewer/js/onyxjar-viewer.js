/**
 * WeaveViewer — a small, documented wrapper around vis-network.
 *
 * The rest of Weave should interact with this class rather than instantiate
 * `vis.Network` directly. It knows nothing about where a payload came from
 * (Model Explorer, Publishing Preview, a frozen published HTML artifact) —
 * it only knows how to render a Weave Viewer Payload (see contracts.py and
 * translate.js). It has no Django dependency and makes no network requests
 * of its own, so it can run unmodified inside a self-contained HTML file.
 *
 * Lifecycle: create() -> update() (zero or more times) -> destroy().
 * update() never destroys/recreates the underlying vis.Network instance —
 * it mutates the existing node/edge DataSets and re-applies options.
 */

import {
  applyEdgeState,
  applyNodeState,
  assertValidPayload,
  translateNode,
  translateEdge,
  translateViewerConfig,
} from "./translate.js";

export class WeaveViewerError extends Error {}

export class WeaveViewer {
  constructor(container, { vis = typeof window !== "undefined" ? window.vis : undefined } = {}) {
    if (!vis || !vis.Network || !vis.DataSet) {
      throw new WeaveViewerError("WeaveViewer requires a vis-network-compatible { Network, DataSet } implementation");
    }

    this._container = container;
    this._vis = vis;
    this._network = null;
    this._nodesDataSet = null;
    this._edgesDataSet = null;
    this._handlers = new Map(); // eventName -> Set<handler>

    // Base (state-free) translations, so an item's interaction state is always
    // derived from its own definition and is reversible.
    this._baseNodes = new Map();
    this._baseEdges = new Map();
    this._nodeStates = new Map(); // id -> "selected" | "related" | "dimmed"
    this._edgeStates = new Map();
  }

  _assertActive() {
    if (!this._network) {
      throw new WeaveViewerError("WeaveViewer has not been created (or has been destroyed)");
    }
  }

  create(payload) {
    if (this._network) {
      this.destroy();
    }

    assertValidPayload(payload);

    const nodes = payload.nodes.map(translateNode);
    const edges = payload.edges.map(translateEdge);

    this._baseNodes = new Map(nodes.map((node) => [node.id, node]));
    this._baseEdges = new Map(edges.map((edge) => [edge.id, edge]));
    this._nodeStates.clear();
    this._edgeStates.clear();

    this._nodesDataSet = new this._vis.DataSet(nodes);
    this._edgesDataSet = new this._vis.DataSet(edges);

    const options = translateViewerConfig(payload.viewer_config);
    this._network = new this._vis.Network(
      this._container,
      { nodes: this._nodesDataSet, edges: this._edgesDataSet },
      options,
    );
  }

  /**
   * Replace the rendered graph with a new payload without recreating the
   * network. Interaction states set with setItemStates() survive for items
   * that are still present.
   *
   * `preservePositions`: keep surviving nodes where they are instead of
   * letting them be laid out again, so narrowing or widening a graph does not
   * scramble what the user is looking at.
   */
  update(payload, { preservePositions = false } = {}) {
    this._assertActive();
    assertValidPayload(payload);

    const positions = preservePositions ? this._network.getPositions() : {};

    const nodes = payload.nodes.map(translateNode);
    const edges = payload.edges.map(translateEdge);

    this._baseNodes = new Map(nodes.map((node) => [node.id, node]));
    this._baseEdges = new Map(edges.map((edge) => [edge.id, edge]));
    pruneStates(this._nodeStates, this._baseNodes);
    pruneStates(this._edgeStates, this._baseEdges);

    this._replaceDataSetContents(
      this._nodesDataSet,
      nodes.map((node) => {
        const state = this._nodeStates.get(node.id);
        const stateful = state ? applyNodeState(node, state) : node;
        const position = positions[node.id];
        return position ? { ...stateful, x: position.x, y: position.y } : stateful;
      }),
    );
    this._replaceDataSetContents(
      this._edgesDataSet,
      edges.map((edge) => {
        const state = this._edgeStates.get(edge.id);
        return state ? applyEdgeState(edge, state) : edge;
      }),
    );

    this._network.setOptions(translateViewerConfig(payload.viewer_config));
  }

  _replaceDataSetContents(dataSet, translatedItems) {
    const newIds = new Set(translatedItems.map((item) => item.id));

    for (const existingId of dataSet.getIds()) {
      if (!newIds.has(existingId)) {
        dataSet.remove(existingId);
      }
    }

    for (const item of translatedItems) {
      // Remove-before-add (rather than DataSet.update()'s shallow merge)
      // guarantees the new entry is the complete translated representation,
      // with no leftover keys from a prior version.
      dataSet.remove(item.id);
      dataSet.add(item);
    }
  }

  /**
   * Declaratively set how items relate to the current focus:
   *   { nodes: { id: "selected" | "related" | "dimmed" }, edges: { ... } }
   * Items not listed return to their normal appearance; unknown ids are
   * ignored. States are derived from each item's base translation, never
   * from another state, so they cannot accumulate and are fully reversible.
   */
  setItemStates({ nodes = {}, edges = {} } = {}) {
    this._assertActive();

    this._applyStates(this._nodesDataSet, this._baseNodes, this._nodeStates, nodes, applyNodeState);
    this._applyStates(this._edgesDataSet, this._baseEdges, this._edgeStates, edges, applyEdgeState);
  }

  clearItemStates() {
    this.setItemStates({});
  }

  _applyStates(dataSet, bases, current, requested, derive) {
    const next = new Map();
    for (const [id, state] of Object.entries(requested)) {
      if (bases.has(id) && state) {
        next.set(id, state);
      }
    }

    // Only items whose state actually changes are touched.
    const affected = new Set([...current.keys(), ...next.keys()]);
    const updates = [];
    for (const id of affected) {
      if (current.get(id) !== next.get(id)) {
        updates.push(derive(bases.get(id), next.get(id)));
      }
    }

    current.clear();
    for (const [id, state] of next) {
      current.set(id, state);
    }

    if (updates.length > 0) {
      dataSet.update(updates);
    }
  }

  /** Ids of the nodes and edges directly connected to a node. */
  getConnected(nodeId) {
    this._assertActive();
    if (this._nodesDataSet.get(nodeId) == null) {
      return { nodes: [], edges: [] };
    }
    return {
      nodes: this._network.getConnectedNodes(nodeId),
      edges: this._network.getConnectedEdges(nodeId),
    };
  }

  destroy() {
    if (!this._network) {
      return;
    }

    for (const [eventName, handlers] of this._handlers.entries()) {
      for (const handler of handlers) {
        this._network.off(eventName, handler);
      }
    }
    this._handlers.clear();

    this._network.destroy();
    this._network = null;
    this._nodesDataSet = null;
    this._edgesDataSet = null;
    this._baseNodes.clear();
    this._baseEdges.clear();
    this._nodeStates.clear();
    this._edgeStates.clear();
  }

  fit(options) {
    this._assertActive();
    this._network.fit(options);
  }

  focusNode(nodeId, options) {
    this._assertActive();
    if (this._nodesDataSet.get(nodeId) == null) {
      return;
    }
    this._network.focus(nodeId, options);
  }

  focusEdge(edgeId, options) {
    this._assertActive();
    const edge = this._edgesDataSet.get(edgeId);
    if (edge == null) {
      return;
    }
    // vis-network has no native focusEdge: fit the view to the edge's
    // two endpoint nodes instead.
    this._network.fit({ nodes: [edge.from, edge.to], ...options });
  }

  selectNode(nodeId) {
    this._assertActive();
    if (this._nodesDataSet.get(nodeId) == null) {
      return;
    }
    this._network.selectNodes([nodeId]);
  }

  selectEdge(edgeId) {
    this._assertActive();
    if (this._edgesDataSet.get(edgeId) == null) {
      return;
    }
    this._network.selectEdges([edgeId]);
  }

  clearSelection() {
    this._assertActive();
    this._network.unselectAll();
  }

  getSelection() {
    this._assertActive();
    return this._network.getSelection();
  }

  getNode(nodeId) {
    this._assertActive();
    return this._nodesDataSet.get(nodeId);
  }

  getEdge(edgeId) {
    this._assertActive();
    return this._edgesDataSet.get(edgeId);
  }

  on(eventName, handler) {
    this._assertActive();
    this._network.on(eventName, handler);

    if (!this._handlers.has(eventName)) {
      this._handlers.set(eventName, new Set());
    }
    this._handlers.get(eventName).add(handler);
  }

  off(eventName, handler) {
    this._assertActive();
    this._network.off(eventName, handler);

    const handlers = this._handlers.get(eventName);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this._handlers.delete(eventName);
      }
    }
  }
}

function pruneStates(states, bases) {
  for (const id of [...states.keys()]) {
    if (!bases.has(id)) {
      states.delete(id);
    }
  }
}
