import test from "node:test";
import assert from "node:assert/strict";

import {
  selectionCount,
  syncHeaderCheckboxState,
  toggleSelection,
} from "../static/model/js/bulk-edit/selection-state.js";

test("toggleSelection adds and removes ids without mutating the input set", () => {
  const original = new Set(["a"]);

  const added = toggleSelection(original, "b", true);
  assert.deepEqual([...added].sort(), ["a", "b"]);
  assert.deepEqual([...original], ["a"]);

  const removed = toggleSelection(added, "a", false);
  assert.deepEqual([...removed], ["b"]);
});

test("selectionCount reflects the set size", () => {
  assert.equal(selectionCount(new Set()), 0);
  assert.equal(selectionCount(new Set(["a", "b"])), 2);
});

test("header checkbox is unchecked and not indeterminate when nothing is selected", () => {
  const state = syncHeaderCheckboxState(new Set(), ["a", "b", "c"]);
  assert.equal(state.checked, false);
  assert.equal(state.indeterminate, false);
});

test("header checkbox is checked when every visible row is selected", () => {
  const state = syncHeaderCheckboxState(new Set(["a", "b", "c"]), ["a", "b", "c"]);
  assert.equal(state.checked, true);
  assert.equal(state.indeterminate, false);
});

test("header checkbox is indeterminate when some but not all visible rows are selected", () => {
  const state = syncHeaderCheckboxState(new Set(["a"]), ["a", "b", "c"]);
  assert.equal(state.checked, false);
  assert.equal(state.indeterminate, true);
});

test("a selection entirely outside the visible rows (e.g. after paging) is neither checked nor indeterminate", () => {
  const state = syncHeaderCheckboxState(new Set(["z"]), ["a", "b", "c"]);
  assert.equal(state.checked, false);
  assert.equal(state.indeterminate, false);
});

test("an empty visible-row list is never checked or indeterminate", () => {
  const state = syncHeaderCheckboxState(new Set(["a"]), []);
  assert.equal(state.checked, false);
  assert.equal(state.indeterminate, false);
});
