/**
 * Requests made by the Data Import page. Every call is a same-origin POST to an
 * ingestion endpoint; upload and preview never change the model, and only
 * "create" produces anything (one Working Proposal).
 *
 * Every function resolves to ``{ok, status, data}`` and never throws, so the
 * page can show the server's message (or a generic one when the network fails).
 */

function csrfToken() {
  const input = document.querySelector("input[name=csrfmiddlewaretoken]");
  if (input?.value) return input.value;
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ?? "";
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function send(fetchFn, url, init) {
  try {
    const response = await fetchFn(url, init);
    return { ok: response.ok, status: response.status, data: await readJson(response) };
  } catch {
    return { ok: false, status: 0, data: { error: "Could not reach the server." } };
  }
}

const jsonPost = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
  body: JSON.stringify(body),
});

export function createImportApi({ urls, fetchFn = globalThis.fetch?.bind(globalThis) }) {
  return {
    /** Upload a file; the server parses it and returns its columns and a sample. */
    upload(file) {
      const form = new FormData();
      form.append("file", file);
      return send(fetchFn, urls.upload, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: form,
      });
    },

    /** What the mapping would change. Read-only. */
    preview(sourceId, mapping) {
      return send(fetchFn, urls.preview, jsonPost({ source_id: sourceId, mapping }));
    },

    /** Create the one Working Proposal (or learn there is nothing to change). */
    create(sourceId, mapping) {
      return send(fetchFn, urls.create, jsonPost({ source_id: sourceId, mapping }));
    },

    /** Drop a staged upload ("Start over"). */
    discard(sourceId) {
      return send(fetchFn, urls.discard, jsonPost({ source_id: sourceId }));
    },
  };
}
