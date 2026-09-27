/**
 * The live Explorer's source: every question is a GET to the server, which
 * projects the effective model (canonical data plus the user's active proposal).
 *
 * A newer request of the same kind cancels an older one (the older resolves to
 * ``null``), so a slow response can never overwrite a fresher one.
 */

import { toQueryParams } from "./explorer-state.js";

export function createRemoteSource({ urls, fetchFn = globalThis.fetch?.bind(globalThis) }) {
  const inFlight = {};

  /** GET JSON; returns ``{ok, status, data}``, or ``null`` when superseded. */
  async function getJson(kind, url, params) {
    inFlight[kind]?.abort();
    const controller = new AbortController();
    inFlight[kind] = controller;

    try {
      const response = await fetchFn(`${url}?${params}`, { signal: controller.signal, headers: { Accept: "application/json" } });
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

  return {
    graph: (state) => getJson("graph", urls.graph, toQueryParams(state)),

    search: (state, query) => getJson("search", urls.search, toQueryParams(state, { q: query })),

    details(state, selection) {
      const template = selection.kind === "object" ? urls.object : urls.relationship;
      return getJson("details", template.replace(urls.placeholder, selection.id), toQueryParams(state));
    },

    /** Where to edit this record's data, or null if the bootstrap carries no edit route. */
    editUrl(kind, id, typeId) {
      const template = kind === "object" ? urls.objectEdit : urls.relationshipEdit;
      if (!template) return null;
      return template.replace(urls.placeholderType, typeId).replace(urls.placeholder, id);
    },

    cancel: (kind) => inFlight[kind]?.abort(),
  };
}
