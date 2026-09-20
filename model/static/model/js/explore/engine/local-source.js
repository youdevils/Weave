/**
 * The published Explorer's source: answers graph, search and details questions
 * from a portable bundle held in memory. No network, no server, no authentication.
 *
 * It satisfies the same source contract as the live Explorer's remote source
 * (see explorer-controller.js) and returns the same response shapes, so the
 * controller and renderers are shared unchanged. Every method is a pure
 * function of the bundle and the state it is given.
 */

import { createDataset } from "./dataset.js";
import { objectDetails, relationshipDetails } from "./details.js";
import { compileGraph } from "./graph.js";
import { project } from "./projection.js";
import { QueryError, sanitiseState, toState } from "./query.js";
import { searchObjects } from "./search.js";

const EMPTY_PROVENANCE = Object.freeze({ entries: [], truncated: false });

export function createLocalSource(bundle) {
  const dataset = createDataset(bundle.dataset);
  const defaultLimit = bundle.defaultView?.limit;
  const canvasBackground = bundle.presentation?.canvasBackground;

  function explore(state) {
    const { query, dropped } = sanitiseState(state, dataset, { limit: defaultLimit });
    return { query, dropped, projection: project(dataset, query) };
  }

  function graphData(state) {
    const { query, dropped, projection } = explore(state);
    return {
      success: true,
      payload: compileGraph(dataset, projection, bundle.graphTemplate),
      summary: projection.summary,
      state: toState(query),
      dropped,
      canvasBackground,
    };
  }

  const respond = (compute) => {
    try {
      return Promise.resolve({ ok: true, status: 200, data: compute() });
    } catch (error) {
      if (error instanceof QueryError) return Promise.resolve({ ok: false, status: 400, data: { success: false, error: error.message } });
      throw error;
    }
  };

  const notFound = (kind) => ({
    ok: false,
    status: 404,
    data: { success: false, code: "not_found", error: `This ${kind} is not part of this publication.` },
  });

  return {
    dataset,

    /** The initial graph response, synchronously (used to start the explorer). */
    graphSync: graphData,

    graph: (state) => respond(() => graphData(state)),

    search: (state, query) =>
      respond(() => {
        const { query: sanitised, dropped, projection } = explore(state);
        return { success: true, ...searchObjects(dataset, query, { projection }), state: toState(sanitised), dropped };
      }),

    details(state, selection) {
      return respond(() => {
        const { query, projection } = explore(state);
        const isObject = selection.kind === "object";
        const details = isObject
          ? objectDetails(dataset, selection.id, projection)
          : relationshipDetails(dataset, selection.id, projection);
        if (details === null) return null;

        const chains = isObject ? bundle.provenance?.objects : bundle.provenance?.relationships;
        details.provenance = chains?.[details.id] ?? EMPTY_PROVENANCE;
        return { success: true, details, state: toState(query) };
      }).then((response) => (response.data === null ? notFound(selection.kind) : response));
    },

    cancel() {},
  };
}
