import test from "node:test";
import assert from "node:assert/strict";

import {
  assertValidPayload,
  ViewerPayloadValidationError,
  translateNode,
  translateEdge,
  translateViewerConfig,
} from "../static/viewer/js/translate.js";

function validPayload(overrides = {}) {
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

test("assertValidPayload accepts a well-formed payload", () => {
  assert.doesNotThrow(() => assertValidPayload(validPayload()));
});

test("assertValidPayload rejects a missing schema_version", () => {
  const payload = validPayload({ schema_version: undefined });
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("assertValidPayload rejects duplicate node ids", () => {
  const payload = validPayload();
  payload.nodes.push({ id: "n1", type_key: "type.a", label: "Dup" });
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("assertValidPayload rejects duplicate edge ids", () => {
  const payload = validPayload();
  payload.edges.push({ id: "e1", relationship_type_key: "rel.a", source: "n1", target: "n2" });
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("assertValidPayload rejects an edge with a dangling source", () => {
  const payload = validPayload();
  payload.edges[0].source = "missing";
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("assertValidPayload rejects an edge with a dangling target", () => {
  const payload = validPayload();
  payload.edges[0].target = "missing";
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("assertValidPayload rejects non-array nodes", () => {
  const payload = validPayload({ nodes: "not-an-array" });
  assert.throws(() => assertValidPayload(payload), ViewerPayloadValidationError);
});

test("translateNode maps only known style fields that are present", () => {
  const node = {
    id: "n1",
    type_key: "type.a",
    label: "Node 1",
    data: { extra_semantic: true },
    style: { shape: "box", background: "#fff", border_width: 2 },
  };

  const translated = translateNode(node);

  assert.equal(translated.id, "n1");
  assert.equal(translated.label, "Node 1");
  assert.equal(translated.shape, "box");
  assert.equal(translated.color.background, "#fff");
  assert.equal(translated.borderWidth, 2);
  assert.equal(translated.color.border, undefined);
  assert.deepEqual(translated.onyxjarData.data, { extra_semantic: true });
});

test("translateNode omits absent optional style fields entirely", () => {
  const node = { id: "n1", type_key: "type.a", label: "Node 1", style: {} };

  const translated = translateNode(node);

  assert.ok(!("shape" in translated));
  assert.ok(!("color" in translated));
  assert.ok(!("borderWidth" in translated));
  assert.ok(!("size" in translated));
});

test("translateNode never spreads style.extra into the translated object", () => {
  const node = {
    id: "n1",
    type_key: "type.a",
    label: "Node 1",
    style: { shape: "box", extra: { futureField: "should-not-appear" } },
  };

  const translated = translateNode(node);

  assert.equal(translated.futureField, undefined);
  assert.ok(!JSON.stringify(translated).includes("should-not-appear"));
});

test("translateNode passes an image through for image-based nodes", () => {
  const node = {
    id: "n1",
    type_key: "type.a",
    label: "Node 1",
    style: { shape: "circularImage", image: "data:image/svg+xml;charset=utf-8,%3Csvg%2F%3E" },
  };

  const translated = translateNode(node);

  assert.equal(translated.shape, "circularImage");
  assert.equal(translated.image, "data:image/svg+xml;charset=utf-8,%3Csvg%2F%3E");
});

test("translateNode omits image when absent", () => {
  const translated = translateNode({ id: "n1", type_key: "type.a", label: "Node 1", style: { shape: "box" } });

  assert.ok(!("image" in translated));
});

test("translateNode leaves a normal-weight label and font untouched", () => {
  const node = {
    id: "n1",
    type_key: "type.a",
    label: "Plain <label>",
    style: { font: { color: "#212529", size: 14, face: "Arial, Helvetica, sans-serif" } },
  };

  const translated = translateNode(node);

  assert.equal(translated.label, "Plain <label>");
  assert.deepEqual(translated.font, { color: "#212529", size: 14, face: "Arial, Helvetica, sans-serif" });
});

test("translateNode renders bold as an html-multi label and never passes weight to vis-network", () => {
  const node = {
    id: "n1",
    type_key: "type.a",
    label: "Fish & <Chips>",
    style: { font: { color: "#212529", size: 14, weight: "bold" } },
  };

  const translated = translateNode(node);

  assert.equal(translated.label, "<b>Fish &amp; &lt;Chips&gt;</b>");
  assert.equal(translated.font.multi, "html");
  assert.equal(translated.font.color, "#212529");
  assert.equal(translated.font.size, 14);
  assert.ok(!("weight" in translated.font));
});

test("translateNode treats an explicit normal weight like no weight", () => {
  const translated = translateNode({
    id: "n1",
    type_key: "type.a",
    label: "Node 1",
    style: { font: { size: 12, weight: "normal" } },
  });

  assert.equal(translated.label, "Node 1");
  assert.deepEqual(translated.font, { size: 12 });
});

test("translateEdge is unaffected by font weight handling", () => {
  const edge = {
    id: "e1",
    relationship_type_key: "rel.a",
    source: "n1",
    target: "n2",
    label: "relates to",
    style: { font: { color: "#495057", size: 11, face: "Arial" }, dashes: [8, 6], arrows: "to, from" },
  };

  const translated = translateEdge(edge);

  assert.equal(translated.label, "relates to");
  assert.deepEqual(translated.font, { color: "#495057", size: 11, face: "Arial" });
  assert.deepEqual(translated.dashes, [8, 6]);
  assert.equal(translated.arrows, "to, from");
});

test("translateEdge maps source/target to from/to and only present style fields", () => {
  const edge = {
    id: "e1",
    relationship_type_key: "rel.a",
    source: "n1",
    target: "n2",
    label: "connects",
    style: { colour: "#123456", width: 3 },
  };

  const translated = translateEdge(edge);

  assert.equal(translated.from, "n1");
  assert.equal(translated.to, "n2");
  assert.equal(translated.label, "connects");
  assert.equal(translated.color, "#123456");
  assert.equal(translated.width, 3);
  assert.ok(!("dashes" in translated));
  assert.ok(!("arrows" in translated));
});

test("translateEdge never spreads style.extra into the translated object", () => {
  const edge = {
    id: "e1",
    relationship_type_key: "rel.a",
    source: "n1",
    target: "n2",
    style: { colour: "#000", extra: { futureField: "should-not-appear" } },
  };

  const translated = translateEdge(edge);

  assert.ok(!JSON.stringify(translated).includes("should-not-appear"));
});

test("translateViewerConfig maps typed layout/physics/interaction fields", () => {
  const options = translateViewerConfig({
    layout: { mode: "hierarchical", hierarchical: { direction: "LR", sort_method: "directed" } },
    physics: { enabled: false, solver: "repulsion", stabilisation: { enabled: false, fit: false } },
    interaction: { hover: true, zoom_enabled: false, multi_select: true },
  });

  assert.equal(options.layout.hierarchical.enabled, true);
  assert.equal(options.layout.hierarchical.direction, "LR");
  assert.equal(options.layout.hierarchical.sortMethod, "directed");
  assert.equal(options.physics.enabled, false);
  assert.equal(options.physics.solver, "repulsion");
  assert.equal(options.physics.stabilization.enabled, false);
  assert.equal(options.physics.stabilization.fit, false);
  assert.equal(options.interaction.hover, true);
  assert.equal(options.interaction.zoomView, false);
  assert.equal(options.interaction.multiselect, true);
});

test("translateViewerConfig never spreads config/physics/interaction extra into options", () => {
  const options = translateViewerConfig({
    extra: { futureTopLevel: "nope" },
    physics: { extra: { futurePhysics: "nope" } },
    interaction: { extra: { futureInteraction: "nope" } },
  });

  const serialised = JSON.stringify(options);
  assert.ok(!serialised.includes("nope"));
});

test("translateViewerConfig defaults produce a standard (non-hierarchical) layout", () => {
  const options = translateViewerConfig({});

  assert.equal(options.layout.hierarchical.enabled, false);
  assert.equal(options.physics.enabled, true);
});
