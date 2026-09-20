import assert from "node:assert/strict";
import test from "node:test";

import { createRemoteSource } from "../static/model/js/explore/remote-source.js";
import { initialState, toggleObjectType } from "../static/model/js/explore/explorer-state.js";

const urls = {
  graph: "/g/",
  search: "/s/",
  object: "/o/PLACEHOLDER/",
  relationship: "/r/PLACEHOLDER/",
  placeholder: "PLACEHOLDER",
};

function fakeFetch(handler) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url, options });
    return handler(url, options);
  };
  fn.calls = calls;
  return fn;
}

const ok = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

test("graph and search send the state as query parameters over GET", async () => {
  const fetchFn = fakeFetch(() => ok({ success: true }));
  const source = createRemoteSource({ urls, fetchFn });
  const state = toggleObjectType(initialState(), "t1");

  const graph = await source.graph(state);
  await source.search(state, "alice");

  assert.deepEqual(graph, { ok: true, status: 200, data: { success: true } });
  assert.equal(fetchFn.calls[0].url, "/g/?hide_objects=t1");
  assert.equal(fetchFn.calls[1].url, "/s/?hide_objects=t1&q=alice");
  assert.equal(fetchFn.calls[0].options.headers.Accept, "application/json");
});

test("details use the placeholder url for the selected kind", async () => {
  const fetchFn = fakeFetch(() => ok({ success: true }));
  const source = createRemoteSource({ urls, fetchFn });

  await source.details(initialState(), { kind: "object", id: "abc" });
  await source.details(initialState(), { kind: "relationship", id: "def" });

  assert.equal(fetchFn.calls[0].url, "/o/abc/?");
  assert.equal(fetchFn.calls[1].url, "/r/def/?");
});

test("a newer request of the same kind supersedes an older one", async () => {
  const pending = [];
  const fetchFn = (url, { signal }) =>
    new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      pending.push(() => resolve(ok({ url })));
    });
  const source = createRemoteSource({ urls, fetchFn });

  const first = source.graph(initialState());
  const second = source.graph(initialState());
  pending[1]();

  assert.equal(await first, null);
  assert.equal((await second).ok, true);
});

test("network failures become an error response rather than a throw", async () => {
  const source = createRemoteSource({ urls, fetchFn: async () => Promise.reject(new TypeError("offline")) });

  const response = await source.graph(initialState());

  assert.equal(response.ok, false);
  assert.equal(response.status, 0);
  assert.match(response.data.error, /Could not reach the server/);
});

test("cancel aborts the in-flight request of that kind", async () => {
  const fetchFn = (url, { signal }) =>
    new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    });
  const source = createRemoteSource({ urls, fetchFn });

  const search = source.search(initialState(), "x");
  source.cancel("search");

  assert.equal(await search, null);
});
