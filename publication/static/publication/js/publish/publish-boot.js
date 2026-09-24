/**
 * Publishing page controller.
 *
 * Two things live side by side here:
 *
 *   - the *definition* being edited (scope, details, opening view), held as the
 *     same document the server stores (publish-state.js);
 *   - a *preview*: the portable Explorer running over exactly the data the
 *     definition would publish. The server builds that data (the same pipeline
 *     that publishes it); this page only mounts the shared Explorer over it.
 *
 * Every change to the scope asks the server for a fresh preview. Publishing
 * sends the definition back together with the revision and digest of the last
 * preview, and the server refuses if anything changed since, so what is
 * downloaded is always what was previewed.
 *
 * The shared Explorer kit is injected (``kit``) because it is served from the
 * model app's static files; this module imports nothing across apps.
 */

import { createPublishApi, saveDownload } from "./publish-api.js";
import * as view from "./publish-render.js";
import * as state from "./publish-state.js";

const PREVIEW_DEBOUNCE_MS = 200;
const SEARCH_DEBOUNCE_MS = 220;

export function startPublishing({ kit, bootstrap, api = createPublishApi({ urls: bootstrap.urls }) }) {
  const { explorerState, explorerRender } = kit;
  const $ = (id) => document.getElementById(id);
  const el = {
    scope: $("publish-scope"),
    notices: $("publish-notices"),
    chips: $("publish-scope-chips"),
    typeFilters: $("publish-type-filters"),
    builder: $("publish-filter-builder"),
    builderMessage: $("publish-builder-message"),
    search: $("publish-search"),
    results: $("publish-results"),
    traversal: $("publish-traversal"),
    title: $("publish-title"),
    description: $("publish-description"),
    filename: $("publish-filename"),
    colour: $("publish-theme-colour"),
    colourReset: $("publish-theme-reset"),
    openingSummary: $("publish-opening-summary"),
    openingSet: $("publish-opening-set"),
    openingClear: $("publish-opening-clear"),
    previous: $("publish-previous"),
    clearScope: $("publish-clear-scope"),
    button: $("publish-button"),
    status: $("publish-status"),
    banner: $("publish-banner"),
    summary: $("publish-summary"),
    tooLarge: $("publish-too-large"),
    preview: $("model-explorer"),
  };

  let config = bootstrap.config;
  const facets = bootstrap.facets; // of the whole canonical model: what can be excluded or filtered
  let rootNames = { ...bootstrap.roots };
  let notices = bootstrap.notices;
  let previous = bootstrap.previous;
  let lastResults = null;
  let builderDraft = { typeId: null, key: null };

  let explorer = null;
  let preview = null; // the last successful preview: {revision, digest}
  let previewToken = 0;
  let previewAbort = null;
  let previewTimer = null;
  let searchAbort = null;
  let searchTimer = null;
  let publishing = false;

  // -- rendering -----------------------------------------------------------------

  const startingIds = () => config.scope.traversal.roots;

  function renderScope() {
    el.typeFilters.innerHTML = explorerRender.renderTypeFilters(facets, state.scopeAsExplorerState(config));
    el.builder.innerHTML = explorerRender.renderFilterBuilder(facets, builderDraft);
    el.chips.innerHTML = view.renderScopeChips(
      state.describeScope(config, facets, rootNames, explorerState.describeAttributeFilter),
    );
    el.traversal.innerHTML = view.renderTraversal(
      config.scope.traversal.roots,
      rootNames,
      config.scope.traversal.depth,
      bootstrap.depth,
    );
    el.notices.innerHTML = view.renderNotices(notices);
    el.clearScope.hidden = !state.hasScope(config);
    if (lastResults) el.results.innerHTML = view.renderLocatorResults(lastResults, startingIds());
  }

  function renderOpening() {
    el.openingSummary.innerHTML = view.renderOpeningViewSummary(
      state.hasOpeningView(config),
      config.default_view.selection ? "an item" : null,
    );
    el.openingClear.disabled = !state.hasOpeningView(config);
  }

  function fillDetails() {
    el.title.value = config.title;
    el.description.value = config.description;
    el.filename.value = config.filename;
    el.colour.value = config.presentation.theme_colour.toLowerCase();
    applyThemeColour();
    el.previous.innerHTML = view.renderPreviousNote(previous);
  }

  function applyThemeColour() {
    el.preview.style.setProperty("--onyxjar-theme", config.presentation.theme_colour);
  }

  function setStatus(text) {
    el.status.textContent = text;
  }

  function showBanner(kind, message) {
    el.banner.innerHTML = view.renderBanner(kind, message);
  }

  function updateButton() {
    el.button.disabled = !preview || publishing || previewTimer !== null;
    el.button.textContent = publishing ? "Publishing…" : "Publish and download";
  }

  // -- preview ---------------------------------------------------------------------

  /** Ask for a fresh preview of the current definition (debounced unless ``immediately``). */
  function schedulePreview({ immediately = false } = {}) {
    previewToken += 1; // whatever is in flight is now out of date
    previewAbort?.abort();
    clearTimeout(previewTimer);
    preview = null;
    setStatus("Updating preview…");
    previewTimer = setTimeout(runPreview, immediately ? 0 : PREVIEW_DEBOUNCE_MS);
    updateButton();
  }

  function readerState() {
    return { ...explorerState.initialState(), ...state.openingExplorerState(config) };
  }

  async function showPreview(bundle) {
    const source = kit.createLocalSource(bundle);
    if (!explorer) {
      const opening = readerState();
      explorer = kit.createExplorer({
        OnyxJarViewer: kit.OnyxJarViewer,
        source,
        bootstrap: { graph: source.graphSync(opening), facets: bundle.facets },
        state: opening,
        defaultState: opening,
      });
    } else {
      explorer.setDefaultState(readerState());
      await explorer.setSource(source, { facets: bundle.facets, fit: true });
    }
  }

  async function runPreview() {
    previewTimer = null;
    const controller = new AbortController();
    previewAbort = controller;
    const token = previewToken;

    const response = await api.preview(config, controller.signal);
    if (!response || token !== previewToken) return;

    if (!response.ok || !response.data?.success) {
      setStatus(response.data?.error ?? "The preview could not be updated.");
      updateButton();
      return;
    }

    const data = response.data;
    config = state.adoptServerDocuments(config, data.config);
    rootNames = { ...rootNames, ...data.roots };
    notices = data.notices;
    renderScope();
    renderOpening();

    el.summary.innerHTML = view.renderSummary(data.summary, data.revision);
    el.tooLarge.hidden = !data.tooLarge;
    el.tooLarge.textContent = data.tooLarge ?? "";

    if (!data.bundle) {
      setStatus("Too large to publish; narrow the scope.");
      updateButton();
      return;
    }

    await showPreview(data.bundle);
    if (token !== previewToken) return;
    preview = { revision: data.revision, digest: data.digest };
    setStatus("Preview is up to date.");
    updateButton();
  }

  /** A scope change: re-render the controls now and refresh the preview shortly. */
  function scopeChanged(next) {
    config = next;
    renderScope();
    renderOpening();
    schedulePreview();
  }

  // -- finding starting points -------------------------------------------------------------

  async function runSearch() {
    const query = el.search.value.trim();
    searchAbort?.abort();
    if (!query) {
      lastResults = null;
      el.results.innerHTML = "";
      return;
    }
    searchAbort = new AbortController();
    const response = await api.search(query, searchAbort.signal);
    if (!response) return;
    if (!response.ok) {
      el.results.innerHTML = '<p class="model-explorer-empty-note">Search is unavailable right now.</p>';
      return;
    }
    lastResults = response.data;
    el.results.innerHTML = view.renderLocatorResults(lastResults, startingIds());
  }

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

  // -- scope events ----------------------------------------------------------------------------

  el.scope.addEventListener("change", (event) => {
    const target = event.target;
    switch (target.dataset.action) {
      case "toggle-object-type":
        scopeChanged(state.toggleObjectType(config, target.dataset.id));
        break;
      case "toggle-relationship-type":
        scopeChanged(state.toggleRelationshipType(config, target.dataset.id));
        break;
      case "builder-type":
        builderDraft = { typeId: target.value, key: null };
        el.builder.innerHTML = explorerRender.renderFilterBuilder(facets, builderDraft);
        break;
      case "builder-attribute": {
        const builder = target.closest(".model-explorer-builder");
        builderDraft = { typeId: builder.dataset.typeId, key: target.value };
        el.builder.innerHTML = explorerRender.renderFilterBuilder(facets, builderDraft);
        break;
      }
      case "set-depth":
        scopeChanged(state.setDepth(config, target.value === "all" ? null : Number(target.value)));
        break;
      default:
        break;
    }
  });

  el.scope.addEventListener("click", (event) => {
    const actionElement = event.target.closest("[data-action]");
    if (!actionElement || ["INPUT", "SELECT"].includes(actionElement.tagName)) return;
    const { action, id } = actionElement.dataset;

    switch (action) {
      case "pick-result": {
        const result = lastResults?.results.find((r) => r.id === id);
        if (result) rootNames[id] = { name: result.name, typeName: result.typeName };
        scopeChanged(state.addRoot(config, id));
        break;
      }
      case "remove-root":
        scopeChanged(state.removeRoot(config, id));
        break;
      case "remove-scope-chip":
        scopeChanged(
          state.removeScopeChip(config, { kind: actionElement.dataset.chipKind, key: actionElement.dataset.chipKey }),
        );
        break;
      case "add-filter": {
        const built = kit.readFilterBuilder(el.builder);
        el.builderMessage.textContent = built?.error || "";
        if (built?.filter) scopeChanged(state.addAttributeFilter(config, built.filter));
        break;
      }
      default:
        break;
    }
  });

  el.clearScope.addEventListener("click", () => scopeChanged(state.clearScope(config)));

  // -- details, presentation and opening view (do not change what is published, so no new preview) ---

  el.title.addEventListener("input", () => {
    config = state.setMetadata(config, "title", el.title.value);
  });
  el.description.addEventListener("input", () => {
    config = state.setMetadata(config, "description", el.description.value);
  });
  el.filename.addEventListener("input", () => {
    config = state.setMetadata(config, "filename", el.filename.value);
  });
  el.colour.addEventListener("input", () => {
    config = state.setThemeColour(config, el.colour.value);
    applyThemeColour();
  });
  el.colourReset.addEventListener("click", () => {
    config = state.setThemeColour(config, bootstrap.modelAccent);
    el.colour.value = bootstrap.modelAccent.toLowerCase();
    applyThemeColour();
  });

  el.openingSet.addEventListener("click", () => {
    if (!explorer) return;
    config = state.setOpeningView(config, explorer.getState());
    explorer.setDefaultState(readerState());
    renderOpening();
    showBanner("success", "The preview's current view will be the view readers open on.");
  });
  el.openingClear.addEventListener("click", () => {
    config = state.clearOpeningView(config);
    explorer?.setDefaultState(readerState());
    renderOpening();
    showBanner("success", "Readers will open on the whole publication.");
  });

  // -- publishing ---------------------------------------------------------------------------------------

  el.button.addEventListener("click", async () => {
    if (!preview || publishing) return;
    publishing = true;
    showBanner("", "");
    setStatus("Publishing…");
    updateButton();

    const response = await api.publish(config, { revision: preview.revision, digest: preview.digest });

    if (response.ok) {
      const filename = state.filenameFromDisposition(response.headers.get("Content-Disposition"), config.filename);
      saveDownload(response.blob, filename);
      const sequence = response.headers.get("X-Publication-Sequence");
      const revision = response.headers.get("X-Publication-Revision");
      previous = {
        sequence,
        title: config.title,
        revision,
        publishedAt: response.headers.get("X-Publication-Published-At"),
      };
      el.previous.innerHTML = view.renderPreviousNote(previous);
      showBanner("success", `Published revision ${revision} as publication #${sequence}. Your browser downloaded ${filename}.`);
      setStatus("Published.");
    } else if (response.status === 409) {
      showBanner("changed", response.data?.error ?? "The model changed since your preview. Please review it and publish again.");
      schedulePreview({ immediately: true });
    } else {
      showBanner("error", response.data?.error ?? "The publication could not be created.");
      setStatus("Not published.");
    }

    publishing = false;
    updateButton();
  });

  // -- start -----------------------------------------------------------------------------------------------

  renderScope();
  renderOpening();
  fillDetails();
  schedulePreview({ immediately: true });

  return { getConfig: () => config };
}
