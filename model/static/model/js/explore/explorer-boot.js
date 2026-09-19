/**
 * Explorer controller: wires the page together.
 *
 * Responsibilities are deliberately split three ways:
 *   - the server decides *what data* belongs in the current graph (projection);
 *   - this controller owns *what the user is investigating* (explorer-state.js);
 *   - WeaveViewer decides *how it is drawn*.
 *
 * Nothing here edits the model: every request is a read (GET).
 */

import { applyCanvasBackground } from "../appearance/appearance-form.js";
import {
  addAttributeFilter,
  clearFilters,
  clearIncluded,
  clearSelection,
  describeFilters,
  hasActiveNarrowing,
  includeObjects,
  initialState,
  reconcile,
  removeChip,
  reset,
  select,
  toggleObjectType,
  toggleRelationshipType,
  toQueryParams,
} from "./explorer-state.js";
import {
  renderChips,
  renderCounts,
  renderDetails,
  renderDetailsError,
  renderEmptyDetails,
  renderFilterBuilder,
  renderNotices,
  renderResults,
  renderSelectionChip,
  renderTypeFilters,
} from "./explorer-render.js";

const SEARCH_DEBOUNCE_MS = 220;
const FOCUS_OPTIONS = { scale: 1, animation: { duration: 400, easingFunction: "easeInOutQuad" } };

export function startExplorer({ WeaveViewer, bootstrap }) {
  const $ = (id) => document.getElementById(id);
  const el = {
    root: $("model-explorer"),
    graph: $("model-explorer-graph"),
    search: $("explorer-search"),
    results: $("explorer-results"),
    typeFilters: $("explorer-type-filters"),
    builder: $("explorer-filter-builder"),
    builderMessage: $("explorer-builder-message"),
    counts: $("explorer-counts"),
    chips: $("explorer-chips"),
    notices: $("explorer-notices"),
    details: $("explorer-details"),
    error: $("explorer-error"),
  };
  const { urls } = bootstrap;
  const facets = bootstrap.facets;

  let state = initialState();
  let graph = bootstrap.graph;
  let details = null;
  let builderDraft = { typeId: null, key: null };
  const inFlight = {};

  const viewer = new WeaveViewer(el.graph);
  viewer.create(graph.payload);
  viewer.fit();
  applyCanvasBackground(el.graph, graph.canvasBackground);

  // -- requests --------------------------------------------------------------

  /** GET JSON; a newer request of the same kind cancels an older one (returns null). */
  async function getJson(kind, url, params) {
    inFlight[kind]?.abort();
    const controller = new AbortController();
    inFlight[kind] = controller;

    try {
      const response = await fetch(`${url}?${params}`, { signal: controller.signal, headers: { Accept: "application/json" } });
      let data = null;
      try {
        data = await response.json();
      } catch (_error) {
        data = null;
      }
      return { ok: response.ok, status: response.status, data };
    } catch (error) {
      if (error.name === "AbortError") return null;
      return { ok: false, status: 0, data: { error: "Could not reach the server." } };
    } finally {
      if (inFlight[kind] === controller) delete inFlight[kind];
    }
  }

  function showError(message) {
    el.error.textContent = message || "";
    el.error.hidden = !message;
  }

  // -- graph -------------------------------------------------------------------

  const nodeIds = () => graph.payload.nodes.map((n) => n.id);
  const hasNode = (id) => graph.payload.nodes.some((n) => n.id === id);

  async function refreshGraph({ fit = false } = {}) {
    const response = await getJson("graph", urls.graph, toQueryParams(state));
    if (!response) return;
    if (!response.ok) {
      showError(response.data?.error || "Could not update the graph.");
      return;
    }
    showError("");

    graph = response.data;
    state = reconcile(state, graph.state);

    viewer.update(graph.payload, { preservePositions: true });
    applyCanvasBackground(el.graph, graph.canvasBackground);
    if (fit) viewer.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });

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

    const template = selection.kind === "object" ? urls.object : urls.relationship;
    const response = await getJson("details", template.replace(urls.placeholder, selection.id), toQueryParams(state));
    if (!response) return;

    if (response.status === 404) {
      // The entity is gone from the effective model (e.g. a proposal removes it).
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
      inFlight.search?.abort();
      el.results.innerHTML = "";
      return;
    }
    const response = await getJson("search", urls.search, toQueryParams(state, { q: query }));
    if (!response) return;
    if (!response.ok) {
      el.results.innerHTML = `<p class="model-explorer-empty-note">Search is unavailable right now.</p>`;
      return;
    }
    el.results.innerHTML = renderResults(response.data);
  }

  let searchTimer = null;
  el.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, SEARCH_DEBOUNCE_MS);
  });
  el.search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      el.search.value = "";
      runSearch();
    }
  });

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
    el.typeFilters.innerHTML = renderTypeFilters(facets, state);
    el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
  }

  function renderDetailsPanel() {
    el.details.innerHTML = state.selection && details ? renderDetails(details) : renderEmptyDetails();
  }

  // -- attribute filter builder ------------------------------------------------------

  function readBuilder() {
    const builder = el.builder.querySelector(".model-explorer-builder");
    if (!builder) return null;
    const { typeId, key, op } = builder.dataset;
    let value;

    if (op === "in") {
      value = [...builder.querySelectorAll("[data-builder-value]:checked")].map((box) => box.dataset.builderValue);
      if (value.length === 0) return { error: "Choose at least one value." };
    } else if (op === "contains") {
      value = builder.querySelector("[data-builder-text]").value.trim();
      if (!value) return { error: "Enter some text to match." };
    } else {
      const min = builder.querySelector("[data-builder-min]").value;
      const max = builder.querySelector("[data-builder-max]").value;
      if (!min && !max) return { error: "Enter a minimum, a maximum, or both." };
      value = { min: min || null, max: max || null };
    }
    return { filter: { type_id: typeId, key, op, value } };
  }

  // -- events ---------------------------------------------------------------------------

  const closestAction = (target) => target.closest("[data-action]");

  el.root.addEventListener("change", async (event) => {
    const target = event.target;
    const action = target.dataset.action;

    if (action === "toggle-object-type") {
      state = toggleObjectType(state, target.dataset.id);
      await refreshGraph({ fit: true });
    } else if (action === "toggle-relationship-type") {
      state = toggleRelationshipType(state, target.dataset.id);
      await refreshGraph({ fit: true });
    } else if (action === "builder-type") {
      builderDraft = { typeId: target.value, key: null };
      el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
    } else if (action === "builder-attribute") {
      const builder = target.closest(".model-explorer-builder");
      builderDraft = { typeId: builder.dataset.typeId, key: target.value };
      el.builder.innerHTML = renderFilterBuilder(facets, builderDraft);
    }
  });

  el.root.addEventListener("click", async (event) => {
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
      case "add-filter": {
        const built = readBuilder();
        el.builderMessage.textContent = built?.error || "";
        if (built?.filter) {
          state = addAttributeFilter(state, built.filter);
          await refreshGraph({ fit: true });
        }
        break;
      }
      case "reset-view":
        state = reset();
        details = null;
        el.search.value = "";
        el.results.innerHTML = "";
        el.builderMessage.textContent = "";
        builderDraft = { typeId: null, key: null };
        showError("");
        await refreshGraph({ fit: true });
        break;
      case "fit-view":
        viewer.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
        break;
      default:
        break;
    }
  });

  // Graph interaction: pick objects/relationships, click empty space to deselect.
  viewer.on("click", (params) => {
    if (params.nodes.length > 0) selectEntity("object", params.nodes[0]);
    else if (params.edges.length > 0) selectEntity("relationship", params.edges[0]);
    else if (state.selection) deselect();
  });

  renderFilters();
  renderStateBar();
  renderDetailsPanel();

  return { viewer, getState: () => state };
}
