import assert from "node:assert/strict";
import test from "node:test";

import { ICON_NAMES, icon } from "../static/model/js/explore/explorer-icons.js";
import { renderDetailsError, renderEmptyDetails } from "../static/model/js/explore/explorer-render.js";

test("every icon is a self-contained inline svg with no external references", () => {
  assert.deepEqual([...ICON_NAMES].sort(), ["cursor", "paperclip", "search", "slash-circle"]);
  for (const name of ICON_NAMES) {
    const svg = icon(name);
    assert.match(svg, /^<svg class="weave-icon"/);
    assert.match(svg, /aria-hidden="true"/);
    assert.doesNotMatch(svg, /https?:|href=|url\(/);
  }
});

test("an unknown icon is an error, not empty markup", () => {
  assert.throws(() => icon("nope"), /Unknown icon/);
});

test("the render layer uses inline icons rather than the Bootstrap Icons font", () => {
  assert.doesNotMatch(renderEmptyDetails(), /\bbi\b/);
  assert.match(renderEmptyDetails(), /<svg class="weave-icon"/);
  assert.match(renderDetailsError("gone"), /<svg class="weave-icon"/);
});
