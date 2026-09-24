/**
 * Explorer controller: wires an Explorer surface together.
 *
 * Responsibilities are deliberately split three ways:
 *   - a *source* decides what data belongs in the current graph, and answers
 *     search and details (the live Explorer asks the server; the published
 *     Explorer and the Publishing preview compute from an embedded dataset);
 *   - this controller owns *what the user is investigating* (explorer-state.js);
 *   - OnyxJarViewer decides *how it is drawn*.
 *
 * The controller performs no I/O of its own and never edits the model. Every
 * request goes through the source, which is the only seam between the Explorer
 * UI and where its data lives.
 *
 * Source contract (each method returns a promise of ``{ok, status, data}``, or
 * ``null`` when a newer request of the same kind superseded it):
 *   graph(state)              data: {payload, summary, state, dropped, canvasBackground}
 *   search(state, query)      data: {query, total, limit, truncated, results, ...}
 *   details(state, selection) data: {details, state}; status 404 when the item is gone
 * and optionally ``cancel(kind)`` to drop an in-flight request ("search" | "graph" | "details").
 */

import {
  addAttributeFilter,
  clearFilters,
  clearSelection,
  deselectAllObjectTypes,
  deselectAllRelationshipTypes,
  describeFilters,
  hasActiveNarrowing,
  includeObjects,
  initialState,
  reconcile,
  removeChip,
  select,
  selectAllObjectTypes,
  selectAllRelationshipTypes,
  toggleObjectType,
  toggleRelationshipType,
} from "./explorer-state.js";
import { buildObjectCopyHtml, buildObjectCopyText } from "./copy-format.js";
import { readFilterBuilder } from "./explorer-builder.js";
import {
  renderChips,
  renderCounts,
  renderDetails,
  renderDetailsError,
  renderEmptyDetails,
  renderFilterBuilder,
  renderNotices,
  renderObjectTypeRows,
  renderRelationshipTypeRows,
  renderResults,
  renderSelectionChip,
} from "./explorer-render.js";

const SEARCH_DEBOUNCE_MS = 220;
const FOCUS_OPTIONS = { scale: 1, animation: { duration: 400, easingFunction: "easeInOutQuad" } };
const FIT_OPTIONS = { animation: { duration: 400, easingFunction: "easeInOutQuad" } };

const ELEMENT_IDS = {
  root: "model-explorer",
  graph: "model-explorer-graph",
  search: "explorer-search",
  results: "explorer-results",
  legend: "explorer-legend",
  legendToggle: "explorer-legend-toggle",
  objectTypeRows: "explorer-object-type-rows",
  objectTypeToggle: "explorer-object-type-toggle",
  relationshipTypeRows: "explorer-relationship-type-rows",
  relationshipTypeToggle: "explorer-relationship-type-toggle",
  selectAllObjectTypes: "explorer-select-all-object-types",
  selectAllRelationshipTypes: "explorer-select-all-relationship-types",
  builder: "explorer-filter-builder",
  builderMessage: "explorer-builder-message",
  counts: "explorer-counts",
  chips: "explorer-chips",
  notices: "explorer-notices",
  sidebar: "explorer-details-panel",
  sidebarToggle: "explorer-sidebar-toggle",
  details: "explorer-details",
  error: "explorer-error",
};

const defaultApplyBackground = (container, colour) => {
  if (container && colour) container.style.background = colour;
};

/**
 * @param {object} config
 * @param {Function} config.OnyxJarViewer
 * @param {object} config.source            see the source contract above
 * @param {{graph: object, facets: object}} config.bootstrap  initial graph response and filter facets
 * @param {object} [config.state]           the state the exploration starts in (default: nothing narrowed)
 * @param {object} [config.defaultState]    what "Reset view" returns to (default: ``config.state``)
 * @param {Function} [config.applyBackground]  (container, colour) => void
 * @param {object} [config.elements]        overrides for the elements looked up by id
 */
export function createExplorer({
  OnyxJarViewer,
  source: initialSource,
  bootstrap,
  state: startState = initialState(),
  defaultState = startState,
  applyBackground = defaultApplyBackground,
  elements = {},
}) {
  const el = {};
  for (const [name, id] of Object.entries(ELEMENT_IDS)) el[name] = elements[name] ?? document.getElementById(id);

  const listeners = new AbortController();
  const { signal } = listeners;

  let source = initialSource;
  let facets = bootstrap.facets;
  let state = startState;
  let graph = bootstrap.graph;
  let details = null;
  let builderDraft = { typeId: null, key: null };
  let searchTimer = null;
  let destroyed = false;

  const viewer = new OnyxJarViewer(el.graph);
  viewer.create(graph.payload);
  viewer.fit();
  applyBackground(el.graph, graph.canvasBackground);

  function showError(message) {
    el.error.textContent = message || "";
    el.error.hidden = !message;
  }

  // -- graph -------------------------------------------------------------------

  const nodeIds = () => graph.payload.nodes.map((n) => n.id);
  const hasNode = (id) => graph.payload.nodes.some((n) => n.id === id);

  async function refreshGraph({ fit = false } = {}) {
    const response = await source.graph(state);
    if (!response || destroyed) return;
    if (!response.ok) {
      showError(response.data?.error || "Could not update the graph.");
      return;
    }
    showError("");

    graph = response.data;
    state = reconcile(state, graph.state);

    viewer.update(graph.payload, { preservePositions: true });
    applyBackground(el.graph, graph.canvasBackground);
    if (fit) viewer.fit(FIT_OPTIONS);

    renderFilters();
    afterSelectionOrGraphChange();
    if (el.search.value.trim()) runSearch();
  }

  // -- selection ---------------------------------------------------------------

  /** Highlight the selection and its immediate context; dim the rest. */
  function applyHighlight() {
    const selection = state.selection;
    const { nodes, edges } = graph.payload;
    const nodeStates = {};
    const edgeStates = {};

    if (selection?.kind === "object" && hasNode(selection.id)) {
      const connected = viewer.getConnected(selection.id);
      for (const id of nodeIds()) nodeStates[id] = "dimmed";
      for (const edge of edges) edgeStates[edge.id] = "dimmed";
      for (const id of connected.nodes) nodeStates[id] = "related";
      for (const id of connected.edges) edgeStates[id] = "related";
      nodeStates[selection.id] = "selected";
    } else if (selection?.kind === "relationship" && edges.some((e) => e.id === selection.id)) {
      const edge = edges.find((e) => e.id === selection.id);
      for (const node of nodes) nodeStates[node.id] = "dimmed";
      for (const other of edges) edgeStates[other.id] = "dimmed";
      nodeStates[edge.source] = "related";
      nodeStates[edge.target] = "related";
      edgeStates[edge.id] = "selected";
    }

    viewer.setItemStates({ nodes: nodeStates, edges: edgeStates });
  }

  function syncViewerSelection() {
    const selection = state.selection;
    if (selection?.kind === "object" && hasNode(selection.id)) viewer.selectNode(selection.id);
    else if (selection?.kind === "relationship" && graph.payload.edges.some((e) => e.id === selection.id)) viewer.selectEdge(selection.id);
    else viewer.clearSelection();
  }

  function afterSelectionOrGraphChange() {
    syncViewerSelection();
    applyHighlight();
    renderStateBar();
    if (state.selection) loadDetails();
    else renderDetailsPanel();
  }

  async function selectEntity(kind, id, { focus = false, bringIntoView = false } = {}) {
    state = select(state, kind, id);

    if (kind === "object" && bringIntoView && !hasNode(id)) {
      state = includeObjects(state, [id]);
      await refreshGraph();
    } else {
      afterSelectionOrGraphChange();
    }

    if (focus && kind === "object" && hasNode(id)) viewer.focusNode(id, FOCUS_OPTIONS);
    if (focus && kind === "relationship") viewer.focusEdge(id);
  }

  function deselect() {
    state = clearSelection(state);
    details = null;
    afterSelectionOrGraphChange();
  }

  async function loadDetails() {
    const selection = state.selection;
    if (!selection) return;

    const response = await source.details(state, selection);
    if (!response || destroyed) return;

    if (response.status === 404) {
      // The entity is gone from the dataset being explored.
      state = clearSelection(state);
      details = null;
      viewer.clearSelection();
      viewer.clearItemStates();
      el.details.innerHTML = renderDetailsError(response.data?.error || "This item is no longer available.");
      renderStateBar();
      return;
    }
    if (!response.ok) {
      showError(response.data?.error || "Could not load details.");
      return;
    }

    details = response.data.details;
    renderDetailsPanel();
    renderStateBar();
  }

  /** Bring the selected item into view (un-hiding its relationship type if needed). */
  function showSelection() {
    if (!details) return;
    if (details.kind === "object") {
      state = includeObjects(state, [details.id]);
    } else {
      state = includeObjects(state, [details.source.id, details.target.id]);
      if (state.hiddenRelationshipTypes.includes(details.type.id)) {
        state = toggleRelationshipType(state, details.type.id);
      }
    }
    return refreshGraph();
  }

  // -- search --------------------------------------------------------------------

  async function runSearch() {
    const query = el.search.value.trim();
    if (!query) {
      source.cancel?.("search");
      el.results.innerHTML = "";
      return;
    }
    const response = await source.search(state, query);
    if (!response || destroyed) return;
    if (!response.ok) {
      el.results.innerHTML = `<p class="model-explorer-empty-note">Search is unavailable right now.</p>`;
      return;
    }
    el.results.innerHTML = renderResults(response.data);
  }

  el.search.addEventListener(
    "input",
    () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS);
    },
    { signal },
  );
  el.search.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape") {
        el.search.value = "";
        runSearch();
      }
    },
    { signal },
  );

  // -- rendering -----------------------------------------------------------------

  function selectionLabel() {
    return state.selection && details && details.id === state.selection.id ? details.name || details.type.name : null;
  }

  function renderStateBar() {
    el.counts.innerHTML = renderCounts(graph.summary);
    el.chips.innerHTML = renderChips(describeFilters(state, facets)) + renderSelectionChip(selectionLabel());
    el.notices.innerHTML = renderNotices(graph.summary, { hasNarrowing: hasActiveNarrowing(state) });
  }

  function renderFilters() {
    // The current graph's own nodes/edges -- so the legend's attribute-value
    // breakdown always matches what is actually on screen, and reflects it on
    // every refresh (filter, search, or otherwise).
    el.objectTypeRows.innerHTML = renderObjectTypeRows(facets.objectTypes, state.hiddenObjectTypes, graph.payload.nodes);
    el.relationshipTypeRows.innerHTML = renderRelationshipTypeRows(
      facets.relationshipTypes,
      state.hiddenRelationshipTypes,
      graph.payload.edges,
    );
    syncSelectAll(el.selectAllObjectTypes, facets.objectTypes, state.hiddenObjectTypes);
    syncSelectAll(el.selectAllRelationshipTypes, facets.relationshipTypes, state.hiddenRelationshipTypes);
    el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
  }

  // -- collapsible panels (legend, sidebar, legend sections) ---------------------
  //
  // Purely presentational: never touched by graph refreshes, `state`, or
  // `defaultState`, so it can't be perturbed by filtering/selecting and never
  // persists across a reload. "Reset view" explicitly re-expands everything.

  function togglePanel(panel, toggle, collapsedClass, label) {
    const collapsed = panel.classList.toggle(collapsedClass);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${label}`);
  }

  function expandPanel(panel, toggle, collapsedClass, label) {
    panel.classList.remove(collapsedClass);
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", `Collapse ${label}`);
  }

  function toggleSection(rows, toggle) {
    const collapsed = rows.classList.toggle("collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
  }

  function expandSection(rows, toggle) {
    rows.classList.remove("collapsed");
    toggle.setAttribute("aria-expanded", "true");
  }

  function syncSelectAll(checkbox, types, hidden) {
    const hiddenCount = types.filter((t) => hidden.includes(t.id)).length;
    checkbox.checked = types.length > 0 && hiddenCount === 0;
    checkbox.indeterminate = hiddenCount > 0 && hiddenCount < types.length;
  }

  function expandAllPanels() {
    expandPanel(el.legend, el.legendToggle, "legend-collapsed", "legend");
    expandPanel(el.sidebar, el.sidebarToggle, "sidebar-collapsed", "details");
    expandSection(el.objectTypeRows, el.objectTypeToggle);
    expandSection(el.relationshipTypeRows, el.relationshipTypeToggle);
  }

  function renderDetailsPanel() {
    el.details.innerHTML =
      state.selection && details ? renderDetails(details, { canCopy: Boolean(source.dataset) }) : renderEmptyDetails();
  }

  /** Copies a human-readable extract of the selected object; a published-viewer-only convenience. */
  async function copySelectedDetails(button) {
    if (!details || details.kind !== "object" || !source.dataset) return;

    const text = buildObjectCopyText(details, source.dataset);
    const originalLabel = button.innerHTML;

    try {
      if (globalThis.ClipboardItem && navigator.clipboard?.write) {
        const html = buildObjectCopyHtml(details, source.dataset);
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/plain": new Blob([text], { type: "text/plain" }),
            "text/html": new Blob([html], { type: "text/html" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(text);
      }
      button.textContent = "Copied";
    } catch (_error) {
      button.textContent = "Couldn't copy";
    }

    setTimeout(() => {
      button.innerHTML = originalLabel;
    }, 1500);
  }

  // -- events ---------------------------------------------------------------------------

  const closestAction = (target) => target.closest("[data-action]");

  el.root.addEventListener(
    "change",
    async (event) => {
      const target = event.target;
      const action = target.dataset.action;

      if (action === "toggle-object-type") {
        state = toggleObjectType(state, target.dataset.id);
        await refreshGraph({ fit: true });
      } else if (action === "toggle-relationship-type") {
        state = toggleRelationshipType(state, target.dataset.id);
        await refreshGraph({ fit: true });
      } else if (action === "select-all-object-types") {
        state = target.checked ? selectAllObjectTypes(state) : deselectAllObjectTypes(state, facets.objectTypes);
        await refreshGraph({ fit: true });
      } else if (action === "select-all-relationship-types") {
        state = target.checked
          ? selectAllRelationshipTypes(state)
          : deselectAllRelationshipTypes(state, facets.relationshipTypes);
        await refreshGraph({ fit: true });
      } else if (action === "builder-type") {
        builderDraft = { typeId: target.value, key: null };
        el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
      } else if (action === "builder-attribute") {
        const builder = target.closest(".model-explorer-builder");
        builderDraft = { typeId: builder.dataset.typeId, key: target.value };
        el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
      }
    },
    { signal },
  );

  el.root.addEventListener(
    "click",
    async (event) => {
      const actionElement = closestAction(event.target);
      if (!actionElement || actionElement.tagName === "INPUT" || actionElement.tagName === "SELECT") return;
      const { action, id } = actionElement.dataset;

      switch (action) {
        case "pick-result":
          await selectEntity("object", id, { focus: true, bringIntoView: true });
          break;
        case "select-object":
          await selectEntity("object", id, { focus: true, bringIntoView: true });
          break;
        case "select-relationship":
          await selectEntity("relationship", id, { focus: true });
          break;
        case "show-selection":
          await showSelection();
          break;
        case "copy-details":
          await copySelectedDetails(actionElement);
          break;
        case "include-connected":
          state = includeObjects(state, actionElement.dataset.ids.split(",").filter(Boolean));
          await refreshGraph();
          break;
        case "clear-selection":
          deselect();
          break;
        case "remove-chip":
          state = removeChip(state, { kind: actionElement.dataset.chipKind, key: actionElement.dataset.chipKey });
          await refreshGraph({ fit: true });
          break;
        case "clear-filters":
          state = clearFilters(state);
          await refreshGraph({ fit: true });
          break;
        case "toggle-legend":
          togglePanel(el.legend, el.legendToggle, "legend-collapsed", "legend");
          break;
        case "toggle-sidebar":
          togglePanel(el.sidebar, el.sidebarToggle, "sidebar-collapsed", "details");
          break;
        case "toggle-legend-section":
          toggleSection(
            id === "object" ? el.objectTypeRows : el.relationshipTypeRows,
            id === "object" ? el.objectTypeToggle : el.relationshipTypeToggle,
          );
          break;
        case "add-filter": {
          const built = readFilterBuilder(el.builder);
          el.builderMessage.textContent = built?.error || "";
          if (built?.filter) {
            state = addAttributeFilter(state, built.filter);
            await refreshGraph({ fit: true });
          }
          break;
        }
        case "reset-view":
          state = defaultState;
          details = null;
          el.search.value = "";
          el.results.innerHTML = "";
          el.builderMessage.textContent = "";
          builderDraft = { typeId: null, key: null };
          showError("");
          expandAllPanels();
          await refreshGraph({ fit: true });
          break;
        case "fit-view":
          viewer.fit(FIT_OPTIONS);
          break;
        default:
          break;
      }
    },
    { signal },
  );

  // Graph interaction: pick objects/relationships, click empty space to deselect.
  viewer.on("click", (params) => {
    if (params.nodes.length > 0) selectEntity("object", params.nodes[0]);
    else if (params.edges.length > 0) selectEntity("relationship", params.edges[0]);
    else if (state.selection) deselect();
  });

  renderFilters();
  renderStateBar();
  renderDetailsPanel();
  if (state.selection) afterSelectionOrGraphChange();

  return {
    viewer,
    getState: () => state,

    /**
     * Point the explorer at different data (e.g. a new preview of the same
     * publication). The reader's state is reconciled against the new dataset
     * (stale ids dropped) and the graph refreshed without recentring it.
     */
    async setSource(nextSource, { facets: nextFacets, fit = false } = {}) {
      source = nextSource;
      if (nextFacets) facets = nextFacets;
      builderDraft = { typeId: null, key: null };
      await refreshGraph({ fit });
    },

    /** What "Reset view" returns to (e.g. a publication's opening view, which can change while editing). */
    setDefaultState(next) {
      defaultState = next;
    },

    /** Stop listening and release the viewer; the instance is unusable afterwards. */
    destroy() {
      destroyed = true;
      clearTimeout(searchTimer);
      listeners.abort();
      viewer.destroy();
    },
  };
}
