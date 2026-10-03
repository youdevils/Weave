import test from "node:test";
import assert from "node:assert/strict";

import { widgetState } from "../static/model/js/bulk-edit/field-widgets.js";

test("a field's value control is enabled only when its mode is Set", () => {
  assert.equal(widgetState("set"), true);
  assert.equal(widgetState("nochange"), false);
  assert.equal(widgetState("clear"), false);
  assert.equal(widgetState("activate"), false);
  assert.equal(widgetState("retire"), false);
});
