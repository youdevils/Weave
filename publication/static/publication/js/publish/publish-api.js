/**
 * Requests made by the Publishing page. All of them are same-origin calls to the
 * publication endpoints; preview and search are read-only, and publishing is the
 * only call that records anything.
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

const jsonPost = (body, signal) => ({
  method: "POST",
  signal,
  headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
  body: JSON.stringify(body),
});

export function createPublishApi({ urls, fetchFn = globalThis.fetch?.bind(globalThis) }) {
  return {
    /** Find objects to use as starting points; ``null`` when the request was aborted. */
    async search(query, signal) {
      try {
        const response = await fetchFn(`${urls.search}?${new URLSearchParams({ q: query })}`, {
          signal,
          headers: { Accept: "application/json" },
        });
        return { ok: response.ok, status: response.status, data: await readJson(response) };
      } catch (error) {
        if (error.name === "AbortError") return null;
        return { ok: false, status: 0, data: { error: "Could not reach the server." } };
      }
    },

    /** The bundle this definition would publish; ``null`` when aborted. */
    async preview(config, signal) {
      try {
        const response = await fetchFn(urls.preview, jsonPost({ config }, signal));
        return { ok: response.ok, status: response.status, data: await readJson(response) };
      } catch (error) {
        if (error.name === "AbortError") return null;
        return { ok: false, status: 0, data: { error: "Could not reach the server." } };
      }
    },

    /**
     * Publish. On success ``{ok: true, blob, headers}``; on refusal or failure
     * ``{ok: false, status, data}`` with the server's JSON error.
     */
    async publish(config, expected) {
      try {
        const response = await fetchFn(urls.submit, jsonPost({ config, expected }));
        if (response.ok) return { ok: true, status: response.status, blob: await response.blob(), headers: response.headers };
        return { ok: false, status: response.status, data: await readJson(response) };
      } catch {
        return { ok: false, status: 0, data: { error: "Could not reach the server." } };
      }
    },
  };
}

/** Hand a generated file to the browser as a download (the browser decides where it is saved). */
export function saveDownload(blob, filename, doc = document, urlApi = URL) {
  const url = urlApi.createObjectURL(blob);
  const link = doc.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  doc.body.appendChild(link);
  link.click();
  link.remove();
  const timer = setTimeout(() => urlApi.revokeObjectURL(url), 10_000);
  timer?.unref?.(); // Node only (tests): a pending revoke must not keep the process alive
}
