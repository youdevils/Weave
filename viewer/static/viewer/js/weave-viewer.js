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

import { assertValidPayload, translateNode, translateEdge, translateViewerConfig } from "./translate.js";

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

    this._nodesDataSet = new this._vis.DataSet(nodes);
    this._edgesDataSet = new this._vis.DataSet(edges);

    const options = translateViewerConfig(payload.viewer_config);
    this._network = new this._vis.Network(
      this._container,
      { nodes: this._nodesDataSet, edges: this._edgesDataSet },
      options,
    );
  }

  update(payload) {
    this._assertActive();
    assertValidPayload(payload);

    this._replaceDataSetContents(this._nodesDataSet, payload.nodes, translateNode);
    this._replaceDataSetContents(this._edgesDataSet, payload.edges, translateEdge);

    this._network.setOptions(translateViewerConfig(payload.viewer_config));
  }

  _replaceDataSetContents(dataSet, items, translate) {
    const newIds = new Set(items.map((item) => item.id));

    for (const existingId of dataSet.getIds()) {
      if (!newIds.has(existingId)) {
        dataSet.remove(existingId);
      }
    }

    for (const item of items) {
      // Remove-before-add (rather than DataSet.update()'s shallow merge)
      // guarantees the new entry is the complete translated representation,
      // with no leftover keys from a prior version.
      dataSet.remove(item.id);
      dataSet.add(translate(item));
    }
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
