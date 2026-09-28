/**
 * Publishing page state: the publication definition being edited.
 *
 * Pure and immutable: every function returns a new config. The config has the
 * same shape the server stores and sanitises (see publication/services/config.py):
 *
 *   {title, description, filename,
 *    scope: {object_types: {excluded}, relationship_types: {excluded},
 *            attribute_filters: [{type_id, key, op, value}],
 *            traversal: {roots, depth}},
 *    presentation: {theme_colour},
 *    default_view: {state, selection, limit}}
 *
 * The scope is what is *in the file*; the opening view is what a reader sees
 * first. Search text is deliberately not part of either: it only helps the
 * publisher find a starting object.
 *
 * The server is authoritative: it echoes a sanitised scope back with every
 * preview and ``adoptServerDocuments`` takes that, so stale ids never linger.
 */

const toggled = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function withScope(config, changes) {
  return { ...config, scope: { ...config.scope, ...changes } };
}

// -- scope: what is included -------------------------------------------------

export const toggleObjectType = (config, typeId) =>
  withScope(config, { object_types: { excluded: toggled(config.scope.object_types.excluded, typeId) } });

export const toggleRelationshipType = (config, typeId) =>
  withScope(config, { relationship_types: { excluded: toggled(config.scope.relationship_types.excluded, typeId) } });

const EXCLUSION_KEYS = { object: "object_types", relationship: "relationship_types" };

/**
 * Include (or exclude) several types at once: what the "All" selector does.
 *
 * Only the ids given are touched, and only the explicit exclusion list changes:
 * the starting point, its depth and the object filters are never involved, and a
 * type that merely has nothing in the current result is never added here.
 */
export function setTypesIncluded(config, kind, ids, included) {
  const key = EXCLUSION_KEYS[kind];
  const current = config.scope[key].excluded;
  const next = included
    ? current.filter((id) => !ids.includes(id))
    : [...current, ...ids.filter((id) => !current.includes(id))];
  return withScope(config, { [key]: { excluded: next } });
}

/** One filter per (type, attribute): adding again replaces the earlier one. */
export function addAttributeFilter(config, filter) {
  const kept = config.scope.attribute_filters.filter((f) => !(f.type_id === filter.type_id && f.key === filter.key));
  return withScope(config, { attribute_filters: [...kept, filter] });
}

export const removeAttributeFilter = (config, index) =>
  withScope(config, { attribute_filters: config.scope.attribute_filters.filter((_, i) => i !== index) });

export function addRoot(config, objectId) {
  const roots = config.scope.traversal.roots;
  if (roots.includes(objectId)) return config;
  return withScope(config, { traversal: { ...config.scope.traversal, roots: [...roots, objectId] } });
}

export const removeRoot = (config, objectId) =>
  withScope(config, {
    traversal: { ...config.scope.traversal, roots: config.scope.traversal.roots.filter((id) => id !== objectId) },
  });

/** ``depth`` is a whole number of hops, or ``null`` for unlimited. */
export const setDepth = (config, depth) => withScope(config, { traversal: { ...config.scope.traversal, depth } });

/** Back to publishing the whole model (metadata, presentation and opening view are kept). */
export const clearScope = (config) =>
  withScope(config, {
    object_types: { excluded: [] },
    relationship_types: { excluded: [] },
    attribute_filters: [],
    traversal: { ...config.scope.traversal, roots: [] },
  });

export function hasScope(config) {
  const { object_types, relationship_types, attribute_filters, traversal } = config.scope;
  return (
    object_types.excluded.length > 0 ||
    relationship_types.excluded.length > 0 ||
    attribute_filters.length > 0 ||
    traversal.roots.length > 0
  );
}

/**
 * The scope in the shape the shared Explorer filter renderers expect
 * (``hiddenObjectTypes`` ... ), so "included" checkboxes reuse them unchanged.
 */
export const scopeAsExplorerState = (config) => ({
  hiddenObjectTypes: config.scope.object_types.excluded,
  hiddenRelationshipTypes: config.scope.relationship_types.excluded,
  attributeFilters: config.scope.attribute_filters,
  include: [],
  selection: null,
});

/**
 * The types for one selector group, with counts of what would actually be published.
 *
 * Two sources, deliberately never derived from one another:
 *   - ``modelTypes``: the whole model's active facets. They decide which types are
 *     eligible to appear at all, and give the count of a type the user excluded
 *     (an excluded type is absent from the scoped facets, but still needs a count).
 *   - ``scopedTypes``: the facets of the latest preview, i.e. the effective result of
 *     starting point + type selections + object filters. ``null`` when there is none
 *     (nothing previewed yet, or too large), in which case model counts are shown.
 *
 * ``empty`` marks a type the user has *not* excluded that has nothing in the current
 * result (because of the starting point, a filter, or another exclusion). It is not
 * an explicit exclusion and never becomes one; ``applicable`` is what "All" acts on.
 */
export function typesForScope(modelTypes, excludedIds, scopedTypes) {
  const scoped = scopedTypes ? new Map(scopedTypes.map((type) => [type.id, type])) : null;
  return modelTypes.map((type) => {
    const excluded = excludedIds.includes(type.id);
    const count = excluded || !scoped ? type.count : (scoped.get(type.id)?.count ?? 0);
    const empty = !excluded && count === 0;
    return { ...type, count, empty, applicable: !empty };
  });
}

/** The state of an "All" selector over the applicable types of a group. */
export function selectAllState(types, excludedIds) {
  const applicable = types.filter((type) => type.applicable);
  const excluded = applicable.filter((type) => excludedIds.includes(type.id)).length;
  return {
    checked: applicable.length > 0 && excluded === 0,
    indeterminate: excluded > 0 && excluded < applicable.length,
    disabled: applicable.length === 0,
  };
}

// -- metadata and presentation ---------------------------------------------------

export const setMetadata = (config, field, value) => ({ ...config, [field]: value });

export const setThemeColour = (config, colour) => ({
  ...config,
  presentation: { ...config.presentation, theme_colour: colour },
});

// -- opening view ---------------------------------------------------------------------

/** Use the preview's current Explorer state (filters, extra objects, selection) as what a reader opens on. */
export function setOpeningView(config, explorerState) {
  return {
    ...config,
    default_view: {
      ...config.default_view,
      state: {
        hiddenObjectTypes: explorerState.hiddenObjectTypes,
        hiddenRelationshipTypes: explorerState.hiddenRelationshipTypes,
        attributeFilters: explorerState.attributeFilters,
        include: explorerState.include,
      },
      selection: explorerState.selection ?? null,
    },
  };
}

export const clearOpeningView = (config) => ({
  ...config,
  default_view: {
    ...config.default_view,
    state: { hiddenObjectTypes: [], hiddenRelationshipTypes: [], attributeFilters: [], include: [] },
    selection: null,
  },
});

export function hasOpeningView(config) {
  const { state, selection } = config.default_view;
  return (
    selection !== null ||
    state.hiddenObjectTypes.length > 0 ||
    state.hiddenRelationshipTypes.length > 0 ||
    state.attributeFilters.length > 0 ||
    state.include.length > 0
  );
}

/** The Explorer state a reader starts in, for the preview's "Reset view". */
export function openingExplorerState(config) {
  const { state, selection } = config.default_view;
  return {
    hiddenObjectTypes: state.hiddenObjectTypes,
    hiddenRelationshipTypes: state.hiddenRelationshipTypes,
    attributeFilters: state.attributeFilters,
    include: state.include,
    selection,
  };
}

// -- reconciling with the server ------------------------------------------------------------

/**
 * Adopt the server's sanitised scope, presentation and opening view. Title,
 * description and filename are left as typed (the server trims them when it
 * saves) so an echo never rewrites what someone is in the middle of typing.
 */
export function adoptServerDocuments(config, echoed) {
  if (!echoed) return config;
  return { ...config, scope: echoed.scope, presentation: echoed.presentation, default_view: echoed.default_view };
}

export const sameConfigForPreview = (a, b) => same(a, b);

// -- presentation of the current scope ---------------------------------------------------------

const nameOf = (facets, kind, id) => (facets?.[kind] ?? []).find((t) => t.id === id)?.name;

/**
 * The scope as removable chips: [{kind, key, label}] where kind is one of
 * excludedObjectType, excludedRelationshipType, attributeFilter, root.
 */
export function describeScope(config, facets, rootNames, describeAttributeFilter) {
  const chips = [];
  for (const id of config.scope.object_types.excluded) {
    chips.push({ kind: "excludedObjectType", key: id, label: `Excluding ${nameOf(facets, "objectTypes", id) ?? "type"}` });
  }
  for (const id of config.scope.relationship_types.excluded) {
    chips.push({
      kind: "excludedRelationshipType",
      key: id,
      label: `Excluding ${nameOf(facets, "relationshipTypes", id) ?? "relationship"}`,
    });
  }
  config.scope.attribute_filters.forEach((filter, index) => {
    chips.push({ kind: "attributeFilter", key: String(index), label: `Only ${describeAttributeFilter(filter, facets)}` });
  });
  for (const id of config.scope.traversal.roots) {
    chips.push({ kind: "root", key: id, label: `Start: ${rootNames?.[id]?.name ?? "object"}` });
  }
  return chips;
}

/** Apply the removal of a chip returned by describeScope. */
export function removeScopeChip(config, chip) {
  switch (chip.kind) {
    case "excludedObjectType":
      return toggleObjectType(config, chip.key);
    case "excludedRelationshipType":
      return toggleRelationshipType(config, chip.key);
    case "attributeFilter":
      return removeAttributeFilter(config, Number(chip.key));
    case "root":
      return removeRoot(config, chip.key);
    default:
      return config;
  }
}

// -- download -------------------------------------------------------------------------------------

/** The filename a ``Content-Disposition`` header suggests, or ``fallback``. */
export function filenameFromDisposition(header, fallback) {
  if (!header) return fallback;
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      /* fall through to the plain form */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : fallback;
}
