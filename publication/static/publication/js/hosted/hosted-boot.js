/**
 * Starts the hosted View: the shared Explorer kit mounted over a stored
 * Publication's bundle, served as a normal page rather than a downloaded file.
 *
 * Reads the same ``defaultView``/``facets`` shape the portable file's local
 * source does, so the opening view matches a Download of the same publication
 * exactly. The Explorer kit (``OnyxJarViewer``, ``createExplorer``,
 * ``createLocalSource``, ``initialState``) is injected because it is served
 * from the model and viewer apps' static files; this module imports nothing
 * across apps (same rule ``publish-boot.js`` follows).
 */

export function startHostedExplorer({ kit, bundle }) {
  const { OnyxJarViewer, createExplorer, createLocalSource, initialState } = kit;

  const view = bundle.defaultView?.state ?? {};
  const state = {
    ...initialState(),
    hiddenObjectTypes: view.hiddenObjectTypes ?? [],
    hiddenRelationshipTypes: view.hiddenRelationshipTypes ?? [],
    attributeFilters: view.attributeFilters ?? [],
    include: view.include ?? [],
    selection: bundle.defaultView?.selection ?? null,
  };

  const source = createLocalSource(bundle);

  return createExplorer({
    OnyxJarViewer,
    source,
    bootstrap: { graph: source.graphSync(state), facets: bundle.facets },
    state,
    defaultState: state,
    panelLabels: { legend: "Explore", sidebar: "Details", controls: "Graph Controls" },
    detailsSectioned: true,
    exclusivePanelsBelow: 900,
  });
}
