import test from "node:test";
import assert from "node:assert/strict";

import { WeaveViewer, WeaveViewerError } from "../static/viewer/js/weave-viewer.js";
import { applyEdgeState, applyNodeState, translateNode, withAlpha, ITEM_STATES } from "../static/viewer/js/translate.js";

// ----------------------------------------------------------------------------
// Fakes: a vis DataSet with update() merge semantics and a Network with
// positions, connectivity and event emission.
// ----------------------------------------------------------------------------

class FakeDataSet {
  constructor(items = []) {
    this._items = new Map(items.map((item) => [item.id, item]));
    this.updateCalls = 0;
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

  // vis DataSet.update(): shallow-merge each item over the existing one.
  update(items) {
    this.updateCalls += 1;
    for (const item of Array.isArray(items) ? items : [items]) {
      this._items.set(item.id, { ...(this._items.get(item.id) ?? {}), ...item });
    }
  }
}

class FakeNetwork {
  constructor(container, data, options) {
    this.container = container;
    this.data = data;
    this.options = options;
    this.positions = {};
    this.positionReads = 0;
    this._listeners = new Map();
  }

  on(eventName, handler) {
    if (!this._listeners.has(eventName)) this._listeners.set(eventName, new Set());
    this._listeners.get(eventName).add(handler);
  }

  off(eventName, handler) {
    this._listeners.get(eventName)?.delete(handler);
  }

  emit(eventName, params) {
    for (const handler of this._listeners.get(eventName) ?? []) handler(params);
  }

  getPositions() {
    this.positionReads += 1;
    return this.positions;
  }

  getConnectedEdges(id) {
    return this.data.edges.getIds().filter((edgeId) => {
      const edge = this.data.edges.get(edgeId);
      return edge.from === id || edge.to === id;
    });
  }

  getConnectedNodes(id) {
    return this.getConnectedEdges(id).map((edgeId) => {
      const edge = this.data.edges.get(edgeId);
      return edge.from === id ? edge.to : edge.from;
    });
  }

  fit() {}
  focus() {}
  setOptions() {}
  destroy() {}
}

const fakeVis = () => ({ Network: FakeNetwork, DataSet: FakeDataSet });

const NODE_STYLE = {
  background: "#EDF2FF",
  border: "#4C6EF5",
  border_width: 1.5,
  font: { color: "#212529", size: 14 },
};

function styledPayload() {
  return {
    schema_version: "1.0",
    nodes: [
      { id: "n1", type_key: "t", label: "One", style: NODE_STYLE },
      { id: "n2", type_key: "t", label: "Two", style: NODE_STYLE },
      { id: "n3", type_key: "t", label: "Three", style: { border_width: 1.5 } },
    ],
    edges: [
      { id: "e1", relationship_type_key: "r", source: "n1", target: "n2", label: "a", style: { colour: "#495057", width: 1.5, font: { color: "#495057", size: 11 } } },
      { id: "e2", relationship_type_key: "r", source: "n2", target: "n3", label: "b", style: { colour: "#495057", width: 1.5 } },
    ],
    viewer_config: {},
  };
}

function createViewer() {
  const viewer = new WeaveViewer({}, { vis: fakeVis() });
  viewer.create(styledPayload());
  return viewer;
}

// ----------------------------------------------------------------------------
// Pure state derivation
// ----------------------------------------------------------------------------

const baseNode = {
  id: "n1",
  label: "One",
  shape: "square",
  color: { background: "#EDF2FF", border: "#4C6EF5" },
  borderWidth: 1.5,
  font: { color: "#212529", size: 14, face: "Arial" },
  size: 25,
};

const baseEdge = {
  id: "e1",
  from: "n1",
  to: "n2",
  color: "#495057",
  width: 1.5,
  label: "rel",
  font: { color: "#495057", size: 11 },
};

test("ITEM_STATES lists the supported vocabulary", () => {
  assert.deepEqual([...ITEM_STATES], ["selected", "related", "dimmed"]);
});

test("withAlpha converts hex colours and leaves anything else alone", () => {
  assert.equal(withAlpha("#FF8000", 0.5), "rgba(255, 128, 0, 0.5)");
  assert.equal(withAlpha("#f80", 0.5), "rgba(255, 136, 0, 0.5)");
  assert.equal(withAlpha("red", 0.5), "red");
  assert.equal(withAlpha("rgba(1,2,3,1)", 0.5), "rgba(1,2,3,1)");
  assert.equal(withAlpha(undefined, 0.5), undefined);
});

test("applyNodeState default explicitly resets every key a state can set", () => {
  const item = applyNodeState(baseNode, undefined);

  assert.equal(item.opacity, 1);
  assert.equal(item.shadow, false);
  assert.equal(item.borderWidth, 1.5);
});

test("applyNodeState selected thickens the border and adds emphasis", () => {
  const item = applyNodeState(baseNode, "selected");

  assert.equal(item.borderWidth, 3.5);
  assert.equal(item.shadow.enabled, true);
  assert.equal(item.opacity, 1);
});

test("applyNodeState related is a lighter emphasis than selected", () => {
  assert.equal(applyNodeState(baseNode, "related").borderWidth, 2.5);
});

test("applyNodeState dimmed lowers opacity and fades the label only", () => {
  const item = applyNodeState(baseNode, "dimmed");

  assert.ok(item.opacity < 0.5);
  assert.match(item.font.color, /^rgba\(33, 37, 41, /);
  assert.equal(item.font.size, 14);
  assert.equal(item.font.face, "Arial");
});

test("applyNodeState never touches shape, colours or size and never mutates the base", () => {
  const snapshot = JSON.parse(JSON.stringify(baseNode));

  for (const state of [undefined, ...ITEM_STATES]) {
    const item = applyNodeState(baseNode, state);
    assert.equal(item.shape, "square");
    assert.deepEqual(item.color, baseNode.color);
    assert.equal(item.size, 25);
  }
  assert.deepEqual(baseNode, snapshot);
});

test("applyNodeState handles a node with no explicit border width or font", () => {
  const item = applyNodeState({ id: "n", label: "x" }, "dimmed");

  assert.equal(item.borderWidth, 1);
  assert.ok(!("font" in item));
});

test("applyEdgeState default restores the plain colour and width", () => {
  const item = applyEdgeState(baseEdge, undefined);

  assert.equal(item.color, "#495057");
  assert.equal(item.width, 1.5);
});

test("applyEdgeState selected and related thicken the line", () => {
  assert.equal(applyEdgeState(baseEdge, "selected").width, 3.5);
  assert.equal(applyEdgeState(baseEdge, "related").width, 2.5);
});

test("applyEdgeState dimmed fades the line and its label", () => {
  const item = applyEdgeState(baseEdge, "dimmed");

  assert.equal(item.color.color, "#495057");
  assert.ok(item.color.opacity < 0.5);
  assert.equal(item.color.inherit, false);
  assert.match(item.font.color, /^rgba\(/);
});

test("applyEdgeState resets a missing colour to null so an earlier state cannot linger", () => {
  assert.equal(applyEdgeState({ id: "e", from: "a", to: "b" }, undefined).color, null);
});

// ----------------------------------------------------------------------------
// WeaveViewer: setItemStates / clearItemStates
// ----------------------------------------------------------------------------

test("setItemStates styles only the listed items and leaves the rest untouched", () => {
  const viewer = createViewer();

  viewer.setItemStates({ nodes: { n1: "selected", n2: "related" }, edges: { e1: "related" } });

  assert.equal(viewer.getNode("n1").borderWidth, 3.5);
  assert.equal(viewer.getNode("n2").borderWidth, 2.5);
  assert.equal(viewer.getNode("n3").opacity, undefined);
  assert.equal(viewer.getEdge("e1").width, 2.5);
  assert.equal(viewer.getEdge("e2").width, 1.5);
});

test("states never change an item's semantic colours", () => {
  const viewer = createViewer();
  const before = viewer.getNode("n1").color;

  viewer.setItemStates({ nodes: { n1: "selected", n2: "dimmed" } });

  assert.deepEqual(viewer.getNode("n1").color, before);
  assert.deepEqual(viewer.getNode("n2").color, before);
});

test("dimmed lowers opacity and fades the label", () => {
  const viewer = createViewer();

  viewer.setItemStates({ nodes: { n2: "dimmed" }, edges: { e2: "dimmed" } });

  assert.ok(viewer.getNode("n2").opacity < 0.5);
  assert.match(viewer.getNode("n2").font.color, /^rgba\(/);
  assert.ok(viewer.getEdge("e2").color.opacity < 0.5);
});

test("clearItemStates restores every item exactly", () => {
  const viewer = createViewer();

  viewer.setItemStates({ nodes: { n1: "selected", n2: "dimmed" }, edges: { e1: "dimmed", e2: "related" } });
  viewer.clearItemStates();

  assert.equal(viewer.getNode("n1").borderWidth, 1.5);
  assert.equal(viewer.getNode("n1").opacity, 1);
  assert.equal(viewer.getNode("n1").shadow, false);
  assert.equal(viewer.getNode("n2").opacity, 1);
  assert.equal(viewer.getNode("n2").font.color, "#212529");
  assert.equal(viewer.getEdge("e1").color, "#495057");
  assert.equal(viewer.getEdge("e2").width, 1.5);
});

test("states are declarative: a new call replaces the previous one", () => {
  const viewer = createViewer();

  viewer.setItemStates({ nodes: { n1: "selected" } });
  viewer.setItemStates({ nodes: { n2: "selected" } });

  assert.equal(viewer.getNode("n1").borderWidth, 1.5);
  assert.equal(viewer.getNode("n2").borderWidth, 3.5);
});

test("states do not accumulate when re-applied", () => {
  const viewer = createViewer();

  for (let i = 0; i < 4; i += 1) {
    viewer.setItemStates({ nodes: { n1: "selected" } });
    viewer.setItemStates({ nodes: { n1: "related" } });
  }

  assert.equal(viewer.getNode("n1").borderWidth, 2.5);
});

test("setItemStates ignores unknown ids and unchanged items", () => {
  const viewer = createViewer();

  assert.doesNotThrow(() => viewer.setItemStates({ nodes: { nope: "selected" }, edges: { nope: "dimmed" } }));
  assert.equal(viewer._nodesDataSet.updateCalls, 0);

  viewer.setItemStates({ nodes: { n1: "selected" } });
  viewer.setItemStates({ nodes: { n1: "selected" } });
  assert.equal(viewer._nodesDataSet.updateCalls, 1);
});

test("setItemStates throws before create()", () => {
  assert.throws(() => new WeaveViewer({}, { vis: fakeVis() }).setItemStates({}), WeaveViewerError);
});

test("item states survive update() for remaining items and are dropped for removed ones", () => {
  const viewer = createViewer();
  viewer.setItemStates({ nodes: { n1: "selected", n2: "dimmed" }, edges: { e1: "related" } });

  const next = styledPayload();
  next.nodes = next.nodes.filter((node) => node.id !== "n2");
  next.edges = [];
  viewer.update(next);

  assert.equal(viewer.getNode("n1").borderWidth, 3.5);
  assert.equal(viewer.getNode("n2"), null);
  assert.equal(viewer._nodeStates.has("n2"), false);
  assert.equal(viewer._edgeStates.size, 0);
});

test("update() with no states adds plain translated nodes (no state keys)", () => {
  const viewer = createViewer();

  viewer.update(styledPayload());

  assert.ok(!("opacity" in viewer.getNode("n1")));
  assert.ok(!("shadow" in viewer.getNode("n1")));
});

test("destroy() clears item states", () => {
  const viewer = createViewer();
  viewer.setItemStates({ nodes: { n1: "selected" } });

  viewer.destroy();

  assert.equal(viewer._nodeStates.size, 0);
});

// ----------------------------------------------------------------------------
// WeaveViewer: getConnected, preservePositions, raw events
// ----------------------------------------------------------------------------

test("getConnected returns the neighbouring nodes and edges of a node", () => {
  const viewer = createViewer();

  assert.deepEqual(viewer.getConnected("n2"), { nodes: ["n1", "n3"], edges: ["e1", "e2"] });
  assert.deepEqual(viewer.getConnected("n3"), { nodes: ["n2"], edges: ["e2"] });
});

test("getConnected is empty for an unknown node", () => {
  assert.deepEqual(createViewer().getConnected("nope"), { nodes: [], edges: [] });
});

test("update({ preservePositions }) keeps surviving nodes where they were", () => {
  const viewer = createViewer();
  viewer._network.positions = { n1: { x: 10, y: 20 }, n2: { x: -5, y: 7 } };

  const next = styledPayload();
  next.nodes.push({ id: "n4", type_key: "t", label: "New", style: {} });
  viewer.update(next, { preservePositions: true });

  assert.equal(viewer.getNode("n1").x, 10);
  assert.equal(viewer.getNode("n1").y, 20);
  assert.equal(viewer.getNode("n2").x, -5);
  assert.ok(!("x" in viewer.getNode("n4")), "a new node gets no position");
});

test("update() neither reads nor applies positions unless asked", () => {
  const viewer = createViewer();
  viewer._network.positions = { n1: { x: 10, y: 20 } };

  viewer.update(styledPayload());

  assert.equal(viewer._network.positionReads, 0);
  assert.ok(!("x" in viewer.getNode("n1")));
});

test("preserved positions combine with item states", () => {
  const viewer = createViewer();
  viewer.setItemStates({ nodes: { n1: "selected" } });
  viewer._network.positions = { n1: { x: 1, y: 2 } };

  viewer.update(styledPayload(), { preservePositions: true });

  assert.equal(viewer.getNode("n1").x, 1);
  assert.equal(viewer.getNode("n1").borderWidth, 3.5);
});

test("raw vis events still reach handlers registered through on()", () => {
  const viewer = createViewer();
  const seen = [];
  viewer.on("click", (params) => seen.push(params));

  viewer._network.emit("click", { nodes: ["n1"], edges: [] });

  assert.deepEqual(seen, [{ nodes: ["n1"], edges: [] }]);
});

// ----------------------------------------------------------------------------
// Selection must not recolour a node
// ----------------------------------------------------------------------------

test("a selected or hovered node keeps its own colours (no vis-network default blue)", () => {
  const node = translateNode({
    id: "n1",
    type_key: "t",
    label: "One",
    style: { background: "#FFF3BF", border: "#F08C00" },
  });

  assert.deepEqual(node.color.highlight, { background: "#FFF3BF", border: "#F08C00" });
  assert.deepEqual(node.color.hover, { background: "#FFF3BF", border: "#F08C00" });
});

test("highlight/hover colours are only emitted for the colour keys that exist", () => {
  const node = translateNode({ id: "n1", type_key: "t", label: "One", style: { border: "#111111" } });

  assert.deepEqual(node.color.highlight, { border: "#111111" });
});

test("a node without colours gets no colour object at all", () => {
  assert.ok(!("color" in translateNode({ id: "n1", type_key: "t", label: "One", style: {} })));
});
