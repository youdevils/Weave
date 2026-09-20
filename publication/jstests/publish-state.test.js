import assert from "node:assert/strict";
import test from "node:test";

import { describeAttributeFilter } from "../../model/static/model/js/explore/explorer-state.js";
import {
  addAttributeFilter,
  addRoot,
  adoptServerDocuments,
  clearOpeningView,
  clearScope,
  describeScope,
  filenameFromDisposition,
  hasOpeningView,
  hasScope,
  openingExplorerState,
  removeAttributeFilter,
  removeRoot,
  removeScopeChip,
  scopeAsExplorerState,
  setDepth,
  setMetadata,
  setOpeningView,
  setThemeColour,
  toggleObjectType,
  toggleRelationshipType,
} from "../static/publication/js/publish/publish-state.js";

const config = () => ({
  title: "T",
  description: "",
  filename: "t.html",
  scope: {
    version: 1,
    object_types: { excluded: [] },
    relationship_types: { excluded: [] },
    attribute_filters: [],
    traversal: { roots: [], depth: 1 },
  },
  presentation: { version: 1, theme_colour: "#4C6EF5" },
  default_view: {
    version: 1,
    state: { hiddenObjectTypes: [], hiddenRelationshipTypes: [], attributeFilters: [], include: [] },
    selection: null,
    limit: 300,
  },
});

const facets = {
  objectTypes: [{ id: "t1", name: "Person", attributes: [{ key: "role", name: "Role", values: [] }] }],
  relationshipTypes: [{ id: "r1", name: "Member of" }],
};
const roleFilter = { type_id: "t1", key: "role", op: "in", value: ["Lead"] };

test("toggling types excludes and re-includes them without mutating the input", () => {
  const before = config();
  const excluded = toggleObjectType(before, "t1");

  assert.deepEqual(excluded.scope.object_types.excluded, ["t1"]);
  assert.deepEqual(before.scope.object_types.excluded, []);
  assert.deepEqual(toggleObjectType(excluded, "t1").scope.object_types.excluded, []);
  assert.deepEqual(toggleRelationshipType(before, "r1").scope.relationship_types.excluded, ["r1"]);
});

test("one attribute filter per type and attribute; adding again replaces it", () => {
  let next = addAttributeFilter(config(), roleFilter);
  next = addAttributeFilter(next, { ...roleFilter, value: ["Engineer"] });

  assert.equal(next.scope.attribute_filters.length, 1);
  assert.deepEqual(next.scope.attribute_filters[0].value, ["Engineer"]);
  assert.equal(removeAttributeFilter(next, 0).scope.attribute_filters.length, 0);
});

test("starting points are unique and removable; depth may be null for unlimited", () => {
  let next = addRoot(config(), "o1");
  next = addRoot(next, "o1");
  next = addRoot(next, "o2");

  assert.deepEqual(next.scope.traversal.roots, ["o1", "o2"]);
  assert.deepEqual(removeRoot(next, "o1").scope.traversal.roots, ["o2"]);
  assert.equal(setDepth(next, null).scope.traversal.depth, null);
  assert.equal(setDepth(next, 3).scope.traversal.depth, 3);
});

test("clearScope removes what narrows the publication and keeps everything else", () => {
  let next = toggleObjectType(config(), "t1");
  next = addAttributeFilter(next, roleFilter);
  next = addRoot(next, "o1");
  next = setMetadata(next, "title", "Kept");
  next = setThemeColour(next, "#00AA00");
  assert.equal(hasScope(next), true);

  const cleared = clearScope(next);

  assert.equal(hasScope(cleared), false);
  assert.equal(cleared.title, "Kept");
  assert.equal(cleared.presentation.theme_colour, "#00AA00");
  assert.equal(cleared.scope.traversal.depth, 1);
});

test("the scope maps onto the shared Explorer filter state", () => {
  let next = toggleObjectType(config(), "t1");
  next = toggleRelationshipType(next, "r1");
  next = addAttributeFilter(next, roleFilter);

  assert.deepEqual(scopeAsExplorerState(next), {
    hiddenObjectTypes: ["t1"],
    hiddenRelationshipTypes: ["r1"],
    attributeFilters: [roleFilter],
    include: [],
    selection: null,
  });
});

test("chips describe the scope and each one can be removed", () => {
  let next = toggleObjectType(config(), "t1");
  next = toggleRelationshipType(next, "r1");
  next = addAttributeFilter(next, roleFilter);
  next = addRoot(next, "o1");

  const chips = describeScope(next, facets, { o1: { name: "Alice" } }, describeAttributeFilter);

  assert.deepEqual(
    chips.map((c) => c.label),
    ["Excluding Person", "Excluding Member of", "Only Person: Role is Lead", "Start: Alice"],
  );
  assert.deepEqual(chips.map((c) => c.kind), ["excludedObjectType", "excludedRelationshipType", "attributeFilter", "root"]);

  let remaining = next;
  for (const chip of chips) remaining = removeScopeChip(remaining, chip);
  assert.equal(hasScope(remaining), false);
});

test("chips fall back to generic names for things that are not in the facets", () => {
  const next = addRoot(toggleObjectType(config(), "gone"), "unknown");

  const labels = describeScope(next, facets, {}, describeAttributeFilter).map((c) => c.label);

  assert.deepEqual(labels, ["Excluding type", "Start: object"]);
});

test("the opening view is captured from, and restored to, an Explorer state", () => {
  const explorer = {
    hiddenObjectTypes: ["t1"],
    hiddenRelationshipTypes: [],
    attributeFilters: [roleFilter],
    include: ["o9"],
    selection: { kind: "object", id: "o9" },
  };

  const next = setOpeningView(config(), explorer);

  assert.equal(hasOpeningView(next), true);
  assert.equal(next.default_view.limit, 300);
  assert.deepEqual(openingExplorerState(next), explorer);
  assert.equal(hasOpeningView(clearOpeningView(next)), false);
  assert.equal(clearOpeningView(next).default_view.limit, 300);
  assert.equal(hasOpeningView(config()), false);
});

test("the opening view never contains the reader's search text or transient state", () => {
  const next = setOpeningView(config(), { hiddenObjectTypes: [], hiddenRelationshipTypes: [], attributeFilters: [], include: [], selection: null, search: "secret" });

  assert.equal(JSON.stringify(next).includes("secret"), false);
});

test("the server's sanitised documents replace ours, but typed metadata is left alone", () => {
  const typing = setMetadata(setMetadata(config(), "title", "Half-typed title  "), "filename", "half");
  const echoed = {
    scope: { ...config().scope, object_types: { excluded: [] } },
    presentation: { version: 1, theme_colour: "#111111" },
    default_view: config().default_view,
    title: "Trimmed by the server",
  };

  const merged = adoptServerDocuments(toggleObjectType(typing, "stale"), echoed);

  assert.deepEqual(merged.scope.object_types.excluded, []);
  assert.equal(merged.presentation.theme_colour, "#111111");
  assert.equal(merged.title, "Half-typed title  ");
  assert.equal(merged.filename, "half");
  assert.equal(adoptServerDocuments(typing, null), typing);
});

test("filenames are read from Content-Disposition headers", () => {
  assert.equal(filenameFromDisposition('attachment; filename="board.html"', "x.html"), "board.html");
  assert.equal(filenameFromDisposition("attachment; filename=board.html", "x.html"), "board.html");
  assert.equal(
    filenameFromDisposition("attachment; filename*=utf-8''%C3%9Cbersicht%20Stra%C3%9Fe.html", "x.html"),
    "Übersicht Straße.html",
  );
  assert.equal(filenameFromDisposition("attachment", "x.html"), "x.html");
  assert.equal(filenameFromDisposition(null, "x.html"), "x.html");
});
