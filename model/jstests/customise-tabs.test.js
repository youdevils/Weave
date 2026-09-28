import test from "node:test";
import assert from "node:assert/strict";

import { nextTabIndex } from "../static/model/js/appearance/customise-tabs.js";

test("ArrowRight and ArrowLeft move between tabs and wrap", () => {
  assert.equal(nextTabIndex(0, 2, "ArrowRight"), 1);
  assert.equal(nextTabIndex(1, 2, "ArrowRight"), 0);
  assert.equal(nextTabIndex(1, 2, "ArrowLeft"), 0);
  assert.equal(nextTabIndex(0, 2, "ArrowLeft"), 1);
});

test("Home and End jump to the first and last tab", () => {
  assert.equal(nextTabIndex(1, 3, "Home"), 0);
  assert.equal(nextTabIndex(0, 3, "End"), 2);
});

test("other keys and empty tab lists are ignored", () => {
  assert.equal(nextTabIndex(0, 2, "Enter"), null);
  assert.equal(nextTabIndex(0, 2, "ArrowDown"), null);
  assert.equal(nextTabIndex(0, 0, "ArrowRight"), null);
});
