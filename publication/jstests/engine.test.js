import assert from "node:assert/strict";
import test from "node:test";

import { createLocalSource } from "../../model/static/model/js/explore/engine/local-source.js";
import { QueryError, sanitiseState } from "../../model/static/model/js/explore/engine/query.js";
import { createDataset } from "../../model/static/model/js/explore/engine/dataset.js";
import {
  casefold,
  compareStrings,
  isPopulated,
  normaliseId,
  pyStr,
  toFloat,
} from "../../model/static/model/js/explore/engine/text.js";

const A = "00000000-0000-0000-0000-00000000000a";
const B = "00000000-0000-0000-0000-00000000000b";
const T = "00000000-0000-0000-0000-0000000000f1";
const R = "00000000-0000-0000-0000-0000000000f2";
const REL = "00000000-0000-0000-0000-0000000000e1";

const style = { shape: "box", background: "#EDF2FF", border: "#4C6EF5", border_width: 1.5, font: {}, size: 25, image: null, extra: {} };

function bundle(overrides = {}) {
  return {
    formatVersion: 1,
    presentation: { canvasBackground: "#FFFFFF" },
    defaultView: { limit: 300 },
    graphTemplate: { schema_version: "1.0", nodes: [], edges: [], metadata: {}, viewer_config: {}, node_types: [], edge_types: [] },
    provenance: { objects: { [A]: { entries: [{ revision: { before: 1, after: 2 } }], truncated: false } }, relationships: {} },
    dataset: {
      objectTypes: [{ id: T, key: "thing", name: "Thing", attributes: [{ key: "n", name: "N", dataType: "number", choices: [] }], style }],
      relationshipTypes: [{ id: R, key: "links", name: "Links", attributes: [], rules: [], style: { colour: "#000" } }],
      objects: [
        { id: A, typeId: T, name: "Alpha", sortKey: "alpha", foldKey: "alpha", description: "", attributes: { n: 3 } },
        { id: B, typeId: T, name: "Beta", sortKey: "beta", foldKey: "beta", description: "", attributes: {} },
      ],
      relationships: [{ id: REL, typeId: R, sourceId: A, targetId: B, attributes: {}, validFrom: null, validTo: null }],
    },
    ...overrides,
  };
}

test("casefold follows Python for the characters toLowerCase gets wrong", () => {
  assert.equal(casefold("Straße"), "strasse");
  assert.equal(casefold("ΟΣ"), "οσ");
  assert.equal(casefold("ﬁne"), "fine");
});

test("compareStrings orders by code point, not UTF-16 code unit", () => {
  // U+FF5E sorts before U+1F600 by code point; by code unit the surrogate pair would win.
  assert.equal(compareStrings("～", "\u{1F600}"), -1);
  assert.equal(compareStrings("\u{1F600}", "～"), 1);
  assert.equal(compareStrings("a", "b"), -1);
  assert.equal(compareStrings("same", "same"), 0);
  assert.equal(compareStrings("ab", "abc"), -1);
});

test("pyStr, isPopulated, toFloat and normaliseId mirror the Python helpers", () => {
  assert.equal(pyStr(true), "True");
  assert.equal(pyStr(null), "None");
  assert.equal(pyStr(12), "12");
  assert.equal(isPopulated("  "), false);
  assert.equal(isPopulated(0), true);
  assert.equal(isPopulated(null), false);
  assert.equal(toFloat(" 5 "), 5);
  assert.equal(toFloat("1e3"), 1000);
  assert.equal(toFloat("abc"), null);
  assert.equal(toFloat("0x10"), null);
  assert.equal(normaliseId(`{${A.toUpperCase()}}`), A);
  assert.equal(normaliseId(`urn:uuid:${A}`), A);
  assert.equal(normaliseId(A.replaceAll("-", "")), A);
  assert.equal(normaliseId("nope"), null);
  assert.equal(normaliseId(null), null);
});

test("a malformed filter list is a QueryError, and the source reports it as a 400", async () => {
  const dataset = createDataset(bundle().dataset);
  assert.throws(() => sanitiseState({ attributeFilters: "x" }, dataset), QueryError);

  const source = createLocalSource(bundle());
  const response = await source.graph({ attributeFilters: "x" });
  assert.equal(response.ok, false);
  assert.equal(response.status, 400);
});

test("the opening view's limit is the default when the state carries none", async () => {
  const source = createLocalSource(bundle({ defaultView: { limit: 1 } }));

  const response = await source.graph({});

  assert.equal(response.data.summary.limit, 1);
  assert.equal(response.data.summary.truncated, true);
  assert.equal(response.data.payload.nodes.length, 1);
});

test("the local source answers every question without a network", async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = () => {
    throw new Error("the published explorer must never call the network");
  };
  try {
    const source = createLocalSource(bundle());

    const graph = await source.graph({});
    assert.equal(graph.ok, true);
    assert.deepEqual(graph.data.payload.nodes.map((n) => n.id), [A, B]);
    assert.equal(graph.data.canvasBackground, "#FFFFFF");
    assert.equal(source.graphSync({}).summary.totalObjects, 2);

    const search = await source.search({}, "alp");
    assert.equal(search.data.results[0].id, A);

    const details = await source.details({}, { kind: "object", id: A });
    assert.equal(details.data.details.name, "Alpha");
    assert.equal(details.data.details.provenance.entries.length, 1);

    const relationship = await source.details({}, { kind: "relationship", id: REL });
    assert.equal(relationship.data.details.source.id, A);
    assert.deepEqual(relationship.data.details.provenance, { entries: [], truncated: false });
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("a record that is not in the publication is a 404, not an error", async () => {
  const source = createLocalSource(bundle());

  const object = await source.details({}, { kind: "object", id: "00000000-0000-0000-0000-0000000000ff" });
  const relationship = await source.details({}, { kind: "relationship", id: "nope" });

  assert.equal(object.status, 404);
  assert.equal(relationship.status, 404);
  assert.match(object.data.error, /not part of this publication/);
});

test("hidden types drop objects and their relationships", async () => {
  const source = createLocalSource(bundle());

  const response = await source.graph({ hiddenObjectTypes: [T] });

  assert.equal(response.data.payload.nodes.length, 0);
  assert.equal(response.data.payload.edges.length, 0);
  assert.equal(response.data.summary.hiddenByObjectType, 2);
});
