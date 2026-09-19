/**
 * Explorer state: what the user is investigating.
 *
 * Pure and immutable: every function returns a new state. The state is small
 * and explicit so filtering is always visible and reversible:
 *
 *   hiddenObjectTypes / hiddenRelationshipTypes  ids the user has switched off
 *   attributeFilters                             [{type_id, key, op, value}]
 *   include                                      object ids brought into view
 *                                                beyond filters (search, "show connected")
 *   selection                                    {kind: "object" | "relationship", id} | null
 *
 * The server is authoritative about which ids and filters are valid;
 * ``reconcile`` adopts its echo so the client never holds stale state.
 */

export function initialState() {
  return {
    hiddenObjectTypes: [],
    hiddenRelationshipTypes: [],
    attributeFilters: [],
    include: [],
    selection: null,
  };
}

const toggled = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
const union = (list, ids) => [...list, ...ids.filter((id, i) => !list.includes(id) && ids.indexOf(id) === i)];

export const toggleObjectType = (state, typeId) => ({
  ...state,
  hiddenObjectTypes: toggled(state.hiddenObjectTypes, typeId),
});

export const toggleRelationshipType = (state, typeId) => ({
  ...state,
  hiddenRelationshipTypes: toggled(state.hiddenRelationshipTypes, typeId),
});

export const showAllTypes = (state) => ({ ...state, hiddenObjectTypes: [], hiddenRelationshipTypes: [] });

/** One filter per (type, attribute): adding again replaces the earlier one. */
export function addAttributeFilter(state, filter) {
  const kept = state.attributeFilters.filter((f) => !(f.type_id === filter.type_id && f.key === filter.key));
  return { ...state, attributeFilters: [...kept, filter] };
}

export const removeAttributeFilter = (state, index) => ({
  ...state,
  attributeFilters: state.attributeFilters.filter((_, i) => i !== index),
});

export const includeObjects = (state, ids) => ({ ...state, include: union(state.include, ids) });

export const removeInclude = (state, id) => ({ ...state, include: state.include.filter((x) => x !== id) });

export const clearIncluded = (state) => ({ ...state, include: [] });

/** Clears everything that narrows or widens the graph; the selection is kept. */
export const clearFilters = (state) => ({
  ...state,
  hiddenObjectTypes: [],
  hiddenRelationshipTypes: [],
  attributeFilters: [],
  include: [],
});

export const select = (state, kind, id) => ({ ...state, selection: { kind, id } });

export const clearSelection = (state) => ({ ...state, selection: null });

/** Back to the initial exploration. */
export const reset = () => initialState();

export function hasActiveNarrowing(state) {
  return (
    state.hiddenObjectTypes.length > 0 ||
    state.hiddenRelationshipTypes.length > 0 ||
    state.attributeFilters.length > 0 ||
    state.include.length > 0
  );
}

/** Query string for the graph / search / details endpoints. */
export function toQueryParams(state, extra = {}) {
  const params = new URLSearchParams();
  for (const id of state.hiddenObjectTypes) params.append("hide_objects", id);
  for (const id of state.hiddenRelationshipTypes) params.append("hide_relationships", id);
  for (const id of state.include) params.append("include", id);
  if (state.attributeFilters.length > 0) params.set("filters", JSON.stringify(state.attributeFilters));
  for (const [key, value] of Object.entries(extra)) params.set(key, value);
  return params;
}

/**
 * Adopt the server's sanitised echo of the query (stale ids and invalid
 * filters removed). The selection is left alone here: it is kept while the
 * entity exists, even if filters hide it, and is cleared by the controller
 * only when the details call reports the entity is gone.
 */
export function reconcile(state, echo) {
  if (!echo) return state;
  return {
    ...state,
    hiddenObjectTypes: echo.hiddenObjectTypes ?? [],
    hiddenRelationshipTypes: echo.hiddenRelationshipTypes ?? [],
    attributeFilters: echo.attributeFilters ?? [],
    include: echo.include ?? [],
  };
}

// ---------------------------------------------------------------------------
// Presentation of the current filters
// ---------------------------------------------------------------------------

const findType = (facets, kind, id) => (facets?.[kind] ?? []).find((t) => t.id === id);

function rangeLabel(value) {
  const { min, max } = value;
  if (min != null && max != null) return `${min} to ${max}`;
  if (min != null) return `from ${min}`;
  return `up to ${max}`;
}

export function describeAttributeFilter(filter, facets) {
  const objectType = findType(facets, "objectTypes", filter.type_id);
  const attribute = objectType?.attributes.find((a) => a.key === filter.key);
  const typeName = objectType?.name ?? "Object";
  const attributeName = attribute?.name ?? filter.key;

  let condition;
  if (filter.op === "in") {
    const labels = filter.value.map((v) => attribute?.values.find((x) => x.value === v)?.label ?? v);
    condition = `is ${labels.join(" or ")}`;
  } else if (filter.op === "contains") {
    condition = `contains "${filter.value}"`;
  } else {
    condition = rangeLabel(filter.value);
  }
  return `${typeName}: ${attributeName} ${condition}`;
}

/**
 * The active filters as removable chips, so the current filter state is always
 * visible: [{kind, key, label}] where kind is one of hiddenObjectType,
 * hiddenRelationshipType, attributeFilter or include.
 */
export function describeFilters(state, facets) {
  const chips = [];

  for (const id of state.hiddenObjectTypes) {
    chips.push({ kind: "hiddenObjectType", key: id, label: `Hiding ${findType(facets, "objectTypes", id)?.name ?? "type"}` });
  }
  for (const id of state.hiddenRelationshipTypes) {
    chips.push({
      kind: "hiddenRelationshipType",
      key: id,
      label: `Hiding ${findType(facets, "relationshipTypes", id)?.name ?? "relationship"}`,
    });
  }
  state.attributeFilters.forEach((filter, index) => {
    chips.push({ kind: "attributeFilter", key: String(index), label: describeAttributeFilter(filter, facets) });
  });
  if (state.include.length > 0) {
    const count = state.include.length;
    chips.push({ kind: "include", key: "all", label: `${count} added to view` });
  }

  return chips;
}

/** Apply the removal of a chip returned by describeFilters. */
export function removeChip(state, chip) {
  switch (chip.kind) {
    case "hiddenObjectType":
      return toggleObjectType(state, chip.key);
    case "hiddenRelationshipType":
      return toggleRelationshipType(state, chip.key);
    case "attributeFilter":
      return removeAttributeFilter(state, Number(chip.key));
    case "include":
      return clearIncluded(state);
    default:
      return state;
  }
}
