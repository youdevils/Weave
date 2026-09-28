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
  selectAllState,
  setDepth,
  setMetadata,
  setOpeningView,
  setThemeColour,
  setTypesIncluded,
  toggleObjectType,
  toggleRelationshipType,
  typesForScope,
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

test("a full reset clears every scope restriction and leaves the details and opening view exactly as they were", () => {
  let next = toggleObjectType(config(), "t1");
  next = toggleRelationshipType(next, "r1");
  next = addAttributeFilter(next, roleFilter);
  next = addRoot(next, "o1");
  next = setMetadata(setMetadata(setMetadata(next, "title", "Kept"), "description", "Also kept"), "filename", "kept.html");
  next = setThemeColour(next, "#00AA00");
  next = setOpeningView(next, {
    hiddenObjectTypes: ["t1"],
    hiddenRelationshipTypes: [],
    attributeFilters: [],
    include: [],
    selection: { kind: "object", id: "o9" },
  });

  const cleared = clearScope(next);

  assert.equal(hasScope(cleared), false);
  assert.deepEqual(cleared.scope.object_types.excluded, []);
  assert.deepEqual(cleared.scope.relationship_types.excluded, []);
  assert.deepEqual(cleared.scope.attribute_filters, []);
  assert.deepEqual(cleared.scope.traversal.roots, []);
  for (const field of ["title", "description", "filename", "presentation", "default_view"]) {
    assert.deepEqual(cleared[field], next[field], field);
  }
});

test("a starting point never changes the explicit type selections or filters, and they never remove it", () => {
  const start = addRoot(config(), "o1");

  assert.deepEqual(start.scope.object_types.excluded, []);
  assert.deepEqual(start.scope.relationship_types.excluded, []);
  assert.deepEqual(start.scope.attribute_filters, []);

  let refined = toggleObjectType(start, "t1");
  refined = toggleRelationshipType(refined, "r1");
  refined = addAttributeFilter(refined, roleFilter);
  assert.deepEqual(refined.scope.traversal, { roots: ["o1"], depth: 1 });

  refined = setTypesIncluded(refined, "object", ["t1"], true);
  refined = removeAttributeFilter(refined, 0);
  assert.deepEqual(refined.scope.traversal, { roots: ["o1"], depth: 1 });
  assert.equal(hasScope(refined), true); // the exclusion of r1 and the starting point remain
});

const modelTypes = [
  { id: "t1", name: "Person", count: 40 },
  { id: "t2", name: "Team", count: 12 },
  { id: "t3", name: "Place", count: 0 },
];

test("selector counts come from the scoped result, and an excluded type keeps its whole-model count", () => {
  const scoped = [
    { id: "t1", count: 3 },
    { id: "t3", count: 0 },
  ]; // t2 is excluded so it is absent from the scoped facets

  const types = typesForScope(modelTypes, ["t2"], scoped);

  assert.deepEqual(
    types.map((t) => [t.id, t.count]),
    [["t1", 3], ["t2", 12], ["t3", 0]],
  );
  assert.equal(types.find((t) => t.id === "t2").applicable, true);
});

test("an active type with nothing in the result stays listed, marked empty, and is not an exclusion", () => {
  const scoped = [{ id: "t1", count: 3 }, { id: "t2", count: 0 }, { id: "t3", count: 0 }];
  const start = addRoot(config(), "o1");

  const types = typesForScope(modelTypes, start.scope.object_types.excluded, scoped);

  assert.deepEqual(types.map((t) => [t.id, t.empty, t.applicable]), [
    ["t1", false, true],
    ["t2", true, false],
    ["t3", true, false],
  ]);
  assert.deepEqual(start.scope.object_types.excluded, []);
});

test("an included type missing from the scoped result counts as zero; with no scoped result the model counts show", () => {
  assert.equal(typesForScope(modelTypes, [], [{ id: "t1", count: 3 }]).find((t) => t.id === "t2").count, 0);
  assert.deepEqual(typesForScope(modelTypes, [], null).map((t) => t.count), [40, 12, 0]);
});

test("All acts only on applicable types and only on the explicit exclusions", () => {
  const start = addRoot(toggleRelationshipType(config(), "r1"), "o1");
  const scoped = [{ id: "t1", count: 3 }, { id: "t2", count: 0 }, { id: "t3", count: 0 }];
  const applicable = typesForScope(modelTypes, [], scoped).filter((t) => t.applicable).map((t) => t.id);

  const none = setTypesIncluded(start, "object", applicable, false);

  assert.deepEqual(none.scope.object_types.excluded, ["t1"]); // t2/t3 have no matching data: not excluded
  assert.deepEqual(none.scope.relationship_types.excluded, ["r1"]);
  assert.deepEqual(none.scope.traversal, { roots: ["o1"], depth: 1 });
  assert.deepEqual(none.scope.attribute_filters, []);
  assert.deepEqual(setTypesIncluded(none, "object", applicable, true).scope.object_types.excluded, []);
  assert.deepEqual(setTypesIncluded(none, "object", ["t1"], false).scope.object_types.excluded, ["t1"]);
});

test("All re-including leaves other exclusions alone and never touches the input", () => {
  const before = toggleObjectType(toggleObjectType(config(), "t1"), "t2");

  const after = setTypesIncluded(before, "object", ["t1"], true);

  assert.deepEqual(after.scope.object_types.excluded, ["t2"]);
  assert.deepEqual(before.scope.object_types.excluded, ["t1", "t2"]);
  assert.deepEqual(setTypesIncluded(config(), "relationship", ["r1"], false).scope.relationship_types.excluded, ["r1"]);
});

test("the All checkbox reflects the applicable types only", () => {
  const scoped = [{ id: "t1", count: 3 }, { id: "t2", count: 5 }, { id: "t3", count: 0 }];

  const all = typesForScope(modelTypes, [], scoped);
  assert.deepEqual(selectAllState(all, []), { checked: true, indeterminate: false, disabled: false });

  const some = typesForScope(modelTypes, ["t1"], scoped);
  assert.deepEqual(selectAllState(some, ["t1"]), { checked: false, indeterminate: true, disabled: false });

  const noneLeft = typesForScope(modelTypes, ["t1", "t2"], scoped);
  assert.deepEqual(selectAllState(noneLeft, ["t1", "t2"]), { checked: false, indeterminate: false, disabled: false });

  const nothing = typesForScope([{ id: "t3", name: "Place", count: 0 }], [], []);
  assert.equal(selectAllState(nothing, []).disabled, true);
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
