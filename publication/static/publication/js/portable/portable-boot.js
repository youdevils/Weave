/**
 * Starts the published (portable) Explorer.
 *
 * Read-only by construction: it is built from the shared Explorer controller and
 * the local source only. There is no remote source, no appearance form, no
 * proposal code and no network access in this file or anything it imports; the
 * generated document also forbids network requests with a Content-Security-Policy.
 */

import { WeaveViewer } from "../../../../../viewer/static/viewer/js/weave-viewer.js";
import { createLocalSource } from "../../../../../model/static/model/js/explore/engine/local-source.js";
import { createExplorer } from "../../../../../model/static/model/js/explore/explorer-controller.js";
import { initialState } from "../../../../../model/static/model/js/explore/explorer-state.js";

/** The state a reader opens in: the publication's opening view. */
export function openingState(defaultView) {
  const view = defaultView?.state ?? {};
  return {
    ...initialState(),
    hiddenObjectTypes: view.hiddenObjectTypes ?? [],
    hiddenRelationshipTypes: view.hiddenRelationshipTypes ?? [],
    attributeFilters: view.attributeFilters ?? [],
    include: view.include ?? [],
    selection: defaultView?.selection ?? null,
  };
}

export function startPortableExplorer({ bundle }) {
  const source = createLocalSource(bundle);
  const state = openingState(bundle.defaultView);

  return createExplorer({
    WeaveViewer,
    source,
    bootstrap: { graph: source.graphSync(state), facets: bundle.facets },
    state,
    defaultState: state,
  });
}

function boot() {
  const data = document.getElementById("weave-published-data");
  try {
    startPortableExplorer({ bundle: JSON.parse(data.textContent) });
  } catch (error) {
    const box = document.getElementById("explorer-error");
    if (box) {
      box.textContent = "This published explorer could not start.";
      box.hidden = false;
    }
    throw error;
  }
}

if (typeof document !== "undefined") boot();
