import assert from "node:assert/strict";
import test from "node:test";

import { createPublishApi, saveDownload } from "../static/publication/js/publish/publish-api.js";

const urls = { search: "/s/", preview: "/p/", submit: "/x/" };

async function withDocument(fn) {
  const previous = globalThis.document;
  globalThis.document = {
    querySelector: (selector) => (selector.includes("csrfmiddlewaretoken") ? { value: "tok" } : null),
  };
  try {
    return await fn();
  } finally {
    globalThis.document = previous;
  }
}

const jsonResponse = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

test("search is a GET with the query", async () => {
  const calls = [];
  const api = createPublishApi({ urls, fetchFn: async (url, options) => (calls.push({ url, options }), jsonResponse({ results: [] })) });

  const response = await api.search("a b");

  assert.equal(calls[0].url, "/s/?q=a+b");
  assert.equal(calls[0].options.method, undefined);
  assert.equal(response.ok, true);
});

test("preview is a CSRF-protected JSON POST of the definition", async () => {
  await withDocument(async () => {
    const calls = [];
    const api = createPublishApi({ urls, fetchFn: async (url, options) => (calls.push({ url, options }), jsonResponse({ success: true })) });

    await api.preview({ title: "T" });

    const { url, options } = calls[0];
    assert.equal(url, "/p/");
    assert.equal(options.method, "POST");
    assert.equal(options.headers["X-CSRFToken"], "tok");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), { config: { title: "T" } });
  });
});

test("publish sends the definition with the previewed revision and digest", async () => {
  await withDocument(async () => {
    const calls = [];
    const blob = new Blob(["<html></html>"]);
    const api = createPublishApi({
      urls,
      fetchFn: async (url, options) => (calls.push({ url, options }), { ok: true, status: 200, blob: async () => blob, headers: new Headers() }),
    });

    const result = await api.publish({ title: "T" }, { revision: 4, digest: "abc" });

    assert.deepEqual(JSON.parse(calls[0].options.body), { config: { title: "T" }, expected: { revision: 4, digest: "abc" } });
    assert.equal(result.ok, true);
    assert.equal(result.blob, blob);
  });
});

test("a refused publish returns the server's JSON error and its status", async () => {
  await withDocument(async () => {
    const api = createPublishApi({ urls, fetchFn: async () => jsonResponse({ code: "changed", error: "Changed." }, 409) });

    const result = await api.publish({}, { revision: 1, digest: "x" });

    assert.deepEqual(result, { ok: false, status: 409, data: { code: "changed", error: "Changed." } });
  });
});

test("network failures and aborts are reported without throwing", async () => {
  await withDocument(async () => {
    const offline = createPublishApi({ urls, fetchFn: async () => Promise.reject(new TypeError("offline")) });
    assert.equal((await offline.publish({}, {})).status, 0);
    assert.equal((await offline.preview({})).status, 0);
    assert.equal((await offline.search("x")).status, 0);

    const aborting = createPublishApi({ urls, fetchFn: async () => Promise.reject(Object.assign(new Error("a"), { name: "AbortError" })) });
    assert.equal(await aborting.preview({}), null);
    assert.equal(await aborting.search("x"), null);
  });
});

test("only same-origin publication endpoints are ever requested", async () => {
  await withDocument(async () => {
    const seen = [];
    const api = createPublishApi({ urls, fetchFn: async (url) => (seen.push(url), jsonResponse({})) });

    await api.search("q");
    await api.preview({});
    await api.publish({}, {});

    assert.ok(seen.every((url) => url.startsWith("/")));
  });
});

test("saveDownload hands the blob to the browser as a named download and cleans up", () => {
  const appended = [];
  const doc = {
    createElement: () => ({ click() { this.clicked = true; }, remove() { this.removed = true; } }),
    body: { appendChild: (node) => appended.push(node) },
  };
  const revoked = [];
  const urlApi = { createObjectURL: () => "blob:x", revokeObjectURL: (u) => revoked.push(u) };

  saveDownload(new Blob(["x"]), "board.html", doc, urlApi);

  const [link] = appended;
  assert.equal(link.href, "blob:x");
  assert.equal(link.download, "board.html");
  assert.equal(link.clicked, true);
  assert.equal(link.removed, true);
});
