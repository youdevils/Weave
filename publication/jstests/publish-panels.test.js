import assert from "node:assert/strict";
import test from "node:test";

import { ELEMENT_IDS } from "../../model/static/model/js/explore/explorer-controller.js";
import {
  DETACHED_ELEMENTS,
  RETAINED_ELEMENTS,
  detachedExplorerElements,
} from "../static/publication/js/publish/publish-panels.js";

const fakeElement = (tag) => ({ tag });

test("every element the Explorer controller looks up is either retained on the page or supplied detached", () => {
  const wanted = Object.keys(ELEMENT_IDS).sort();
  const supplied = [...RETAINED_ELEMENTS, ...DETACHED_ELEMENTS].sort();

  assert.deepEqual(supplied, wanted);
});

test("no element is both retained and detached", () => {
  const overlap = RETAINED_ELEMENTS.filter((name) => DETACHED_ELEMENTS.includes(name));

  assert.deepEqual(overlap, []);
});

test("a stand-in is created for each detached element, and only for those", () => {
  const elements = detachedExplorerElements(fakeElement);

  assert.deepEqual(Object.keys(elements).sort(), [...DETACHED_ELEMENTS].sort());
  for (const node of Object.values(elements)) assert.ok(node);
});

test("the select-all stand-ins are checkboxes and the search stand-in is an input", () => {
  const elements = detachedExplorerElements(fakeElement);

  assert.equal(elements.selectAllObjectTypes.type, "checkbox");
  assert.equal(elements.selectAllRelationshipTypes.type, "checkbox");
  assert.equal(elements.search.tag, "input");
});

test("each stand-in is a separate node", () => {
  const elements = detachedExplorerElements(fakeElement);

  assert.equal(new Set(Object.values(elements)).size, DETACHED_ELEMENTS.length);
});
