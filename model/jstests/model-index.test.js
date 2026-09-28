import test from "node:test";
import assert from "node:assert/strict";

import {
  emptyState,
  isVisible,
  matchesQuery,
} from "../static/model/js/model-index.js";

const active = { active: true, search: "customer cust_id" };
const retired = { active: false, search: "legacy account legacy_acct" };

test("matchesQuery ignores case and requires every token", () => {
  assert.equal(matchesQuery("Customer cust_id", "CUSTOMER"), true);
  assert.equal(matchesQuery("customer cust_id", "cust customer"), true);
  assert.equal(matchesQuery("customer cust_id", "customer order"), false);
});

test("matchesQuery treats an empty or blank query as a match", () => {
  assert.equal(matchesQuery("anything", ""), true);
  assert.equal(matchesQuery("anything", "   "), true);
  assert.equal(matchesQuery("anything", undefined), true);
});

test("matchesQuery matches the key as well as the name", () => {
  assert.equal(matchesQuery("customer cust_id", "cust_id"), true);
});

test("Active hides inactive items; All shows both", () => {
  assert.equal(isVisible(active, { query: "", filter: "active" }), true);
  assert.equal(isVisible(retired, { query: "", filter: "active" }), false);
  assert.equal(isVisible(active, { query: "", filter: "all" }), true);
  assert.equal(isVisible(retired, { query: "", filter: "all" }), true);
});

test("search and the Active/All filter combine", () => {
  assert.equal(isVisible(active, { query: "cust", filter: "active" }), true);
  assert.equal(isVisible(active, { query: "legacy", filter: "active" }), false);
  assert.equal(isVisible(retired, { query: "legacy", filter: "active" }), false);
  assert.equal(isVisible(retired, { query: "legacy", filter: "all" }), true);
  assert.equal(isVisible(retired, { query: "cust", filter: "all" }), false);
});

test("a search with no matches names the query and offers to clear it", () => {
  const state = emptyState({
    query: " finance ",
    filter: "active",
    noun: "object types",
    retiredMatches: 0,
  });
  assert.equal(state.message, 'No object types match "finance".');
  assert.equal(state.showClear, true);
  assert.equal(state.showAll, false);
});

test("a search only matched by retired items offers Show all", () => {
  const state = emptyState({
    query: "legacy",
    filter: "active",
    noun: "relationship types",
    retiredMatches: 2,
  });
  assert.equal(state.showAll, true);
});

test("under All, a search never offers Show all", () => {
  const state = emptyState({
    query: "zzz",
    filter: "all",
    noun: "object types",
    retiredMatches: 0,
  });
  assert.equal(state.showAll, false);
});

test("no active items and no query offers Show all", () => {
  const state = emptyState({
    query: "",
    filter: "active",
    noun: "object types",
  });
  assert.equal(state.message, "No active object types.");
  assert.equal(state.showClear, false);
  assert.equal(state.showAll, true);
});
