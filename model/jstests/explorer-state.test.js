import test from "node:test";
import assert from "node:assert/strict";

import {
  addAttributeFilter,
  clearFilters,
  clearIncluded,
  clearSelection,
  deselectAllObjectTypes,
  deselectAllRelationshipTypes,
  describeAttributeFilter,
  describeFilters,
  hasActiveNarrowing,
  includeObjects,
  initialState,
  reconcile,
  removeAttributeFilter,
  removeChip,
  removeInclude,
  reset,
  select,
  selectAllObjectTypes,
  selectAllRelationshipTypes,
  showAllTypes,
  toQueryParams,
  toggleObjectType,
  toggleRelationshipType,
} from "../static/model/js/explore/explorer-state.js";

const facets = {
  objectTypes: [
    {
      id: "t-app",
      name: "Application",
      attributes: [
        { key: "status", name: "Status", op: "in", values: [{ value: "Live", count: 2 }, { value: "true", label: "Yes", count: 1 }] },
        { key: "owner", name: "Owner", op: "contains", values: [] },
        { key: "users", name: "Users", op: "range", values: [] },
      ],
    },
    { id: "t-team", name: "Team", attributes: [] },
  ],
  relationshipTypes: [{ id: "r-uses", name: "Uses" }],
};

// ---------------------------------------------------------------------------
// Reducers
// ---------------------------------------------------------------------------

test("initial state is unfiltered with nothing selected", () => {
  assert.deepEqual(initialState(), {
    hiddenObjectTypes: [],
    hiddenRelationshipTypes: [],
    attributeFilters: [],
    include: [],
    selection: null,
  });
  assert.equal(hasActiveNarrowing(initialState()), false);
});

test("reducers never mutate the previous state", () => {
  const before = initialState();
  const snapshot = JSON.stringify(before);

  toggleObjectType(before, "a");
  toggleRelationshipType(before, "b");
  addAttributeFilter(before, { type_id: "t", key: "k", op: "in", value: ["x"] });
  includeObjects(before, ["o1"]);
  select(before, "object", "o1");

  assert.equal(JSON.stringify(before), snapshot);
});

test("toggling a type hides it and toggling again restores it", () => {
  let state = toggleObjectType(initialState(), "t-app");
  assert.deepEqual(state.hiddenObjectTypes, ["t-app"]);
  assert.equal(hasActiveNarrowing(state), true);

  state = toggleObjectType(state, "t-app");
  assert.deepEqual(state.hiddenObjectTypes, []);
  assert.equal(hasActiveNarrowing(state), false);
});

test("hiding an object type and a relationship type are independent", () => {
  let state = toggleRelationshipType(toggleObjectType(initialState(), "t-app"), "r-uses");

  assert.deepEqual(state.hiddenObjectTypes, ["t-app"]);
  assert.deepEqual(state.hiddenRelationshipTypes, ["r-uses"]);

  state = showAllTypes(state);
  assert.deepEqual([state.hiddenObjectTypes, state.hiddenRelationshipTypes], [[], []]);
});

test("selectAllObjectTypes clears hidden object types without touching relationship types", () => {
  let state = toggleObjectType(initialState(), "t-app");
  state = toggleRelationshipType(state, "r-uses");

  const shown = selectAllObjectTypes(state);

  assert.deepEqual(shown.hiddenObjectTypes, []);
  assert.deepEqual(shown.hiddenRelationshipTypes, ["r-uses"]);
});

test("deselectAllObjectTypes hides every object type from the given list, leaving relationship types alone", () => {
  let state = toggleRelationshipType(initialState(), "r-uses");

  const hidden = deselectAllObjectTypes(state, facets.objectTypes);

  assert.deepEqual(hidden.hiddenObjectTypes, ["t-app", "t-team"]);
  assert.deepEqual(hidden.hiddenRelationshipTypes, ["r-uses"]);
});

test("selectAllRelationshipTypes clears hidden relationship types without touching object types", () => {
  let state = toggleObjectType(initialState(), "t-app");
  state = toggleRelationshipType(state, "r-uses");

  const shown = selectAllRelationshipTypes(state);

  assert.deepEqual(shown.hiddenRelationshipTypes, []);
  assert.deepEqual(shown.hiddenObjectTypes, ["t-app"]);
});

test("deselectAllRelationshipTypes hides every relationship type from the given list, leaving object types alone", () => {
  let state = toggleObjectType(initialState(), "t-app");

  const hidden = deselectAllRelationshipTypes(state, facets.relationshipTypes);

  assert.deepEqual(hidden.hiddenRelationshipTypes, ["r-uses"]);
  assert.deepEqual(hidden.hiddenObjectTypes, ["t-app"]);
});

test("select-all/deselect-all tolerate an empty type list", () => {
  assert.deepEqual(deselectAllObjectTypes(initialState(), []).hiddenObjectTypes, []);
  assert.deepEqual(deselectAllRelationshipTypes(initialState(), []).hiddenRelationshipTypes, []);
});

test("an attribute filter replaces an earlier one for the same type and attribute", () => {
  let state = addAttributeFilter(initialState(), { type_id: "t-app", key: "status", op: "in", value: ["Live"] });
  state = addAttributeFilter(state, { type_id: "t-app", key: "owner", op: "contains", value: "a" });
  state = addAttributeFilter(state, { type_id: "t-app", key: "status", op: "in", value: ["Retired"] });

  assert.equal(state.attributeFilters.length, 2);
  assert.deepEqual(state.attributeFilters.find((f) => f.key === "status").value, ["Retired"]);
});

test("removing an attribute filter by index", () => {
  let state = addAttributeFilter(initialState(), { type_id: "t", key: "a", op: "contains", value: "x" });
  state = addAttributeFilter(state, { type_id: "t", key: "b", op: "contains", value: "y" });

  assert.deepEqual(removeAttributeFilter(state, 0).attributeFilters.map((f) => f.key), ["b"]);
});

test("include is a set: duplicates collapse and it can be removed or cleared", () => {
  let state = includeObjects(initialState(), ["a", "b", "a"]);
  state = includeObjects(state, ["b", "c"]);
  assert.deepEqual(state.include, ["a", "b", "c"]);

  assert.deepEqual(removeInclude(state, "b").include, ["a", "c"]);
  assert.deepEqual(clearIncluded(state).include, []);
});

test("clearFilters restores the broader view but keeps the selection", () => {
  let state = toggleObjectType(initialState(), "t-app");
  state = addAttributeFilter(state, { type_id: "t-app", key: "owner", op: "contains", value: "x" });
  state = includeObjects(state, ["o1"]);
  state = select(state, "object", "o9");

  const cleared = clearFilters(state);

  assert.equal(hasActiveNarrowing(cleared), false);
  assert.deepEqual(cleared.selection, { kind: "object", id: "o9" });
});

test("filter changes do not disturb the selection", () => {
  let state = select(initialState(), "object", "o1");

  state = toggleObjectType(state, "t-app");
  state = includeObjects(state, ["o2"]);
  state = addAttributeFilter(state, { type_id: "t-app", key: "owner", op: "contains", value: "x" });

  assert.deepEqual(state.selection, { kind: "object", id: "o1" });
});

test("selection can be set, replaced and cleared", () => {
  let state = select(initialState(), "object", "o1");
  state = select(state, "relationship", "r1");
  assert.deepEqual(state.selection, { kind: "relationship", id: "r1" });

  assert.equal(clearSelection(state).selection, null);
});

test("reset returns to the initial state", () => {
  let state = toggleObjectType(initialState(), "t-app");
  state = includeObjects(select(state, "object", "o1"), ["o2"]);

  assert.deepEqual(reset(state), initialState());
});

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

test("toQueryParams encodes every part of the state the server understands", () => {
  let state = toggleObjectType(initialState(), "t-app");
  state = toggleRelationshipType(state, "r-uses");
  state = includeObjects(state, ["o1", "o2"]);
  state = addAttributeFilter(state, { type_id: "t-app", key: "status", op: "in", value: ["Live"] });

  const params = toQueryParams(state, { q: "web" });

  assert.deepEqual(params.getAll("hide_objects"), ["t-app"]);
  assert.deepEqual(params.getAll("hide_relationships"), ["r-uses"]);
  assert.deepEqual(params.getAll("include"), ["o1", "o2"]);
  assert.deepEqual(JSON.parse(params.get("filters")), state.attributeFilters);
  assert.equal(params.get("q"), "web");
});

test("the selection is not sent as a query parameter", () => {
  const params = toQueryParams(select(initialState(), "object", "o1"));

  assert.equal(params.toString(), "");
});

test("an unfiltered state produces an empty query", () => {
  assert.equal(toQueryParams(initialState()).toString(), "");
});

// ---------------------------------------------------------------------------
// Reconciliation with the server
// ---------------------------------------------------------------------------

test("reconcile adopts the server's sanitised echo, dropping stale ids and filters", () => {
  let state = toggleObjectType(initialState(), "gone");
  state = includeObjects(state, ["stale"]);
  state = addAttributeFilter(state, { type_id: "gone", key: "k", op: "in", value: ["x"] });

  const reconciled = reconcile(state, {
    hiddenObjectTypes: [],
    hiddenRelationshipTypes: [],
    attributeFilters: [],
    include: [],
  });

  assert.equal(hasActiveNarrowing(reconciled), false);
});

test("reconcile never drops a selection just because filters hide it", () => {
  const state = select(toggleObjectType(initialState(), "t-team"), "object", "o1");

  const reconciled = reconcile(state, { hiddenObjectTypes: ["t-team"], hiddenRelationshipTypes: [], attributeFilters: [], include: [] });

  assert.deepEqual(reconciled.selection, { kind: "object", id: "o1" });
});

test("reconcile without an echo leaves the state alone", () => {
  const state = toggleObjectType(initialState(), "t-app");

  assert.equal(reconcile(state, null), state);
});

// ---------------------------------------------------------------------------
// Making filters visible
// ---------------------------------------------------------------------------

test("describeAttributeFilter reads naturally for each operator", () => {
  assert.equal(
    describeAttributeFilter({ type_id: "t-app", key: "status", op: "in", value: ["Live", "true"] }, facets),
    "Application: Status is Live or Yes",
  );
  assert.equal(
    describeAttributeFilter({ type_id: "t-app", key: "owner", op: "contains", value: "car" }, facets),
    'Application: Owner contains "car"',
  );
  assert.equal(
    describeAttributeFilter({ type_id: "t-app", key: "users", op: "range", value: { min: 10, max: 99 } }, facets),
    "Application: Users 10 to 99",
  );
  assert.equal(
    describeAttributeFilter({ type_id: "t-app", key: "users", op: "range", value: { min: 10, max: null } }, facets),
    "Application: Users from 10",
  );
  assert.equal(
    describeAttributeFilter({ type_id: "t-app", key: "users", op: "range", value: { min: null, max: 5 } }, facets),
    "Application: Users up to 5",
  );
});

test("describeAttributeFilter tolerates a type or attribute the facets no longer know", () => {
  assert.equal(
    describeAttributeFilter({ type_id: "zzz", key: "mystery", op: "contains", value: "x" }, facets),
    'Object: mystery contains "x"',
  );
});

test("describeFilters lists every active filter as a chip", () => {
  let state = toggleObjectType(initialState(), "t-team");
  state = toggleRelationshipType(state, "r-uses");
  state = addAttributeFilter(state, { type_id: "t-app", key: "status", op: "in", value: ["Live"] });
  state = includeObjects(state, ["o1", "o2", "o3"]);

  assert.deepEqual(
    describeFilters(state, facets).map((c) => [c.kind, c.label]),
    [
      ["hiddenObjectType", "Hiding Team"],
      ["hiddenRelationshipType", "Hiding Uses"],
      ["attributeFilter", "Application: Status is Live"],
      ["include", "3 added to view"],
    ],
  );
  assert.deepEqual(describeFilters(initialState(), facets), []);
});

test("removing a chip undoes exactly that filter", () => {
  let state = toggleObjectType(initialState(), "t-team");
  state = toggleRelationshipType(state, "r-uses");
  state = addAttributeFilter(state, { type_id: "t-app", key: "status", op: "in", value: ["Live"] });
  state = includeObjects(state, ["o1"]);

  const chips = Object.fromEntries(describeFilters(state, facets).map((c) => [c.kind, c]));

  assert.deepEqual(removeChip(state, chips.hiddenObjectType).hiddenObjectTypes, []);
  assert.deepEqual(removeChip(state, chips.hiddenRelationshipType).hiddenRelationshipTypes, []);
  assert.deepEqual(removeChip(state, chips.attributeFilter).attributeFilters, []);
  assert.deepEqual(removeChip(state, chips.include).include, []);
  // The others are untouched by each removal.
  assert.deepEqual(removeChip(state, chips.include).hiddenObjectTypes, ["t-team"]);
  assert.equal(removeChip(state, { kind: "unknown", key: "x" }), state);
});
