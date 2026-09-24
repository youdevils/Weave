import test from "node:test";
import assert from "node:assert/strict";

import { OnyxJarViewer, OnyxJarViewerError } from "../static/viewer/js/onyxjar-viewer.js";

class FakeDataSet {
  constructor(items = []) {
    this._items = new Map(items.map((item) => [item.id, item]));
  }

  get(id) {
    return this._items.has(id) ? this._items.get(id) : null;
  }

  getIds() {
    return Array.from(this._items.keys());
  }

  add(item) {
    this._items.set(item.id, item);
  }

  remove(id) {
    this._items.delete(id);
  }
}

class FakeNetwork {
  constructor(container, data, options) {
    this.container = container;
    this.data = data;
    this.options = options;
    this.destroyed = false;
    this.calls = { fit: [], focus: [], selectNodes: [], selectEdges: [], unselectAll: 0, setOptions: [] };
    this._listeners = new Map();
  }

  on(eventName, handler) {
    if (!this._listeners.has(eventName)) this._listeners.set(eventName, new Set());
    this._listeners.get(eventName).add(handler);
  }

  off(eventName, handler) {
    this._listeners.get(eventName)?.delete(handler);
  }

  listenerCount(eventName) {
    return this._listeners.get(eventName)?.size ?? 0;
  }

  fit(options) {
    this.calls.fit.push(options);
  }

  focus(nodeId, options) {
    this.calls.focus.push([nodeId, options]);
  }

  selectNodes(ids) {
    this.calls.selectNodes.push(ids);
  }

  selectEdges(ids) {
    this.calls.selectEdges.push(ids);
  }

  unselectAll() {
    this.calls.unselectAll += 1;
  }

  getSelection() {
    return { nodes: ["n1"], edges: [] };
  }

  setOptions(options) {
    this.calls.setOptions.push(options);
  }

  destroy() {
    this.destroyed = true;
  }
}

function fakeVis() {
  return { Network: FakeNetwork, DataSet: FakeDataSet };
}

function payload(overrides = {}) {
  return {
    schema_version: "1.0",
    nodes: [
      { id: "n1", type_key: "type.a", label: "Node 1", data: {}, style: {} },
      { id: "n2", type_key: "type.b", label: "Node 2", data: {}, style: {} },
    ],
    edges: [
      { id: "e1", relationship_type_key: "rel.a", source: "n1", target: "n2", data: {}, style: {} },
    ],
    viewer_config: {},
    ...overrides,
  };
}

test("constructor throws OnyxJarViewerError without a vis-compatible implementation", () => {
  assert.throws(() => new OnyxJarViewer({}, { vis: {} }), OnyxJarViewerError);
});

test("lifecycle methods throw before create()", () => {
  const viewer = new OnyxJarViewer({}, { vis: fakeVis() });

  assert.throws(() => viewer.fit(), OnyxJarViewerError);
  assert.throws(() => viewer.update(payload()), OnyxJarViewerError);
  assert.throws(() => viewer.getSelection(), OnyxJarViewerError);
});

test("create() instantiates exactly one Network with translated data", () => {
  const vis = fakeVis();
  const container = { id: "container" };
  const viewer = new OnyxJarViewer(container, { vis });

  viewer.create(payload());

  assert.equal(viewer._network.container, container);
  assert.equal(viewer._network.data.nodes.getIds().length, 2);
  assert.equal(viewer._network.data.edges.getIds().length, 1);
});

test("create() with an invalid payload throws and never touches Network", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  assert.throws(() => viewer.create(payload({ edges: [{ id: "e1", relationship_type_key: "r", source: "n1", target: "missing" }] })));
  assert.equal(viewer._network, null);
});

test("create() called twice destroys the prior instance first (idempotent)", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  const firstNetwork = viewer._network;

  viewer.create(payload());

  assert.equal(firstNetwork.destroyed, true);
  assert.notEqual(viewer._network, firstNetwork);
});

test("update() does not create a new Network instance", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  const network = viewer._network;

  viewer.update(payload());

  assert.equal(viewer._network, network);
  assert.equal(network.destroyed, false);
});

test("update() fully replaces a node's rendered representation (no stale properties)", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload({
    nodes: [{ id: "n1", type_key: "type.a", label: "Node 1", style: { border_width: 5 } }],
    edges: [],
  }));

  assert.equal(viewer.getNode("n1").borderWidth, 5);

  viewer.update(payload({
    nodes: [{ id: "n1", type_key: "type.a", label: "Node 1", style: {} }],
    edges: [],
  }));

  const updatedNode = viewer.getNode("n1");
  assert.ok(!("borderWidth" in updatedNode), "stale borderWidth must not survive an update that omits it");
});

test("update() removes nodes/edges that are no longer present in the new payload", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  assert.equal(viewer.getNode("n2") !== null, true);

  viewer.update(payload({
    nodes: [{ id: "n1", type_key: "type.a", label: "Node 1", style: {} }],
    edges: [],
  }));

  assert.equal(viewer.getNode("n2"), null);
  assert.equal(viewer.getEdge("e1"), null);
});

test("update() re-applies translated viewer_config via setOptions", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  viewer.update(payload({ viewer_config: { physics: { enabled: false } } }));

  const lastOptions = viewer._network.calls.setOptions.at(-1);
  assert.equal(lastOptions.physics.enabled, false);
});

test("destroy() unregisters every tracked handler and is safe to call twice", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  const handler = () => {};
  viewer.on("selectNode", handler);

  const network = viewer._network;
  assert.equal(network.listenerCount("selectNode"), 1);

  viewer.destroy();

  assert.equal(network.listenerCount("selectNode"), 0);
  assert.equal(network.destroyed, true);

  assert.doesNotThrow(() => viewer.destroy());
});

test("methods throw OnyxJarViewerError after destroy()", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });

  viewer.create(payload());
  viewer.destroy();

  assert.throws(() => viewer.fit(), OnyxJarViewerError);
  assert.throws(() => viewer.selectNode("n1"), OnyxJarViewerError);
});

test("selectNode/selectEdge/clearSelection/getSelection delegate to the network", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });
  viewer.create(payload());

  viewer.selectNode("n1");
  viewer.selectEdge("e1");
  viewer.clearSelection();

  assert.deepEqual(viewer._network.calls.selectNodes, [["n1"]]);
  assert.deepEqual(viewer._network.calls.selectEdges, [["e1"]]);
  assert.equal(viewer._network.calls.unselectAll, 1);
  assert.deepEqual(viewer.getSelection(), { nodes: ["n1"], edges: [] });
});

test("selectNode/selectEdge no-op for unknown ids rather than throwing", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });
  viewer.create(payload());

  assert.doesNotThrow(() => viewer.selectNode("does-not-exist"));
  assert.doesNotThrow(() => viewer.selectEdge("does-not-exist"));
  assert.equal(viewer._network.calls.selectNodes.length, 0);
  assert.equal(viewer._network.calls.selectEdges.length, 0);
});

test("focusNode delegates to network.focus", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });
  viewer.create(payload());

  viewer.focusNode("n1", { scale: 1.5 });

  assert.deepEqual(viewer._network.calls.focus, [["n1", { scale: 1.5 }]]);
});

test("focusEdge fits to the edge's endpoint nodes (no native vis-network focusEdge)", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });
  viewer.create(payload());

  viewer.focusEdge("e1");

  const lastFit = viewer._network.calls.fit.at(-1);
  assert.deepEqual(lastFit.nodes, ["n1", "n2"]);
});

test("on()/off() delegate to the network and update internal bookkeeping", () => {
  const vis = fakeVis();
  const viewer = new OnyxJarViewer({}, { vis });
  viewer.create(payload());

  const handler = () => {};
  viewer.on("hoverNode", handler);
  assert.equal(viewer._network.listenerCount("hoverNode"), 1);

  viewer.off("hoverNode", handler);
  assert.equal(viewer._network.listenerCount("hoverNode"), 0);
});
