import assert from "node:assert/strict";
import test from "node:test";

import { createImportApi } from "../static/ingestion/js/import-api.js";

const urls = { upload: "/u/", preview: "/p/", create: "/c/", discard: "/d/" };

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

function recorder(response) {
  const calls = [];
  const fetchFn = async (url, options) => (calls.push({ url, options }), response);
  return { calls, api: createImportApi({ urls, fetchFn }) };
}

test("upload posts the file as multipart with the CSRF token", async () =>
  withDocument(async () => {
    const { calls, api } = recorder(jsonResponse({ success: true }));
    const file = new Blob(["a,b"], { type: "text/csv" });

    const result = await api.upload(file);

    assert.equal(calls[0].url, "/u/");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[0].options.headers["X-CSRFToken"], "tok");
    assert.ok(calls[0].options.body instanceof FormData);
    assert.ok(calls[0].options.body.get("file"));
    // The browser sets the multipart boundary; a manual Content-Type would break it.
    assert.equal(calls[0].options.headers["Content-Type"], undefined);
    assert.equal(result.ok, true);
  }));

test("preview and create post the source id and mapping as JSON", async () =>
  withDocument(async () => {
    const { calls, api } = recorder(jsonResponse({ success: true }));
    const mapping = { target: { kind: "object", type_id: "T" }, columns: [] };

    await api.preview("S", mapping);
    await api.create("S", mapping);

    assert.equal(calls[0].url, "/p/");
    assert.equal(calls[1].url, "/c/");

    for (const call of calls) {
      assert.equal(call.options.headers["Content-Type"], "application/json");
      assert.deepEqual(JSON.parse(call.options.body), { source_id: "S", mapping });
    }
  }));

test("discard posts the source id", async () =>
  withDocument(async () => {
    const { calls, api } = recorder(jsonResponse({ success: true }));

    await api.discard("S");

    assert.equal(calls[0].url, "/d/");
    assert.deepEqual(JSON.parse(calls[0].options.body), { source_id: "S" });
  }));

test("a refusal comes back with its status and server message", async () =>
  withDocument(async () => {
    const { api } = recorder(jsonResponse({ success: false, error: "Nope" }, 422));

    const result = await api.create("S", {});

    assert.equal(result.ok, false);
    assert.equal(result.status, 422);
    assert.equal(result.data.error, "Nope");
  }));

test("a network failure becomes a friendly result instead of throwing", async () =>
  withDocument(async () => {
    const api = createImportApi({ urls, fetchFn: async () => { throw new Error("offline"); } });

    const result = await api.preview("S", {});

    assert.equal(result.ok, false);
    assert.equal(result.status, 0);
    assert.match(result.data.error, /Could not reach the server/);
  }));
