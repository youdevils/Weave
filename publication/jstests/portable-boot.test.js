import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { openingState } from "../static/publication/js/portable/portable-boot.js";

test("the reader opens on the publication's opening view", () => {
  const state = openingState({
    state: {
      hiddenObjectTypes: ["t1"],
      hiddenRelationshipTypes: ["r1"],
      attributeFilters: [{ type_id: "t2", key: "k", op: "in", value: ["v"] }],
      include: ["o1"],
    },
    selection: { kind: "object", id: "o1" },
  });

  assert.deepEqual(state, {
    hiddenObjectTypes: ["t1"],
    hiddenRelationshipTypes: ["r1"],
    attributeFilters: [{ type_id: "t2", key: "k", op: "in", value: ["v"] }],
    include: ["o1"],
    selection: { kind: "object", id: "o1" },
  });
});

test("a publication without an opening view opens on everything", () => {
  for (const view of [undefined, null, {}, { state: {} }]) {
    assert.deepEqual(openingState(view), {
      hiddenObjectTypes: [],
      hiddenRelationshipTypes: [],
      attributeFilters: [],
      include: [],
      selection: null,
    });
  }
});

test("the portable entry point cannot reach the network or any editing module", () => {
  const dir = new URL("../static/publication/js/portable/", import.meta.url);
  const source = readFileSync(new URL("portable-boot.js", dir), "utf8");

  for (const forbidden of ["fetch(", "XMLHttpRequest", "explorer-boot", "remote-source", "appearance-form", "sendBeacon", "WebSocket"]) {
    assert.equal(source.includes(forbidden), false, `portable-boot.js must not reference ${forbidden}`);
  }
  assert.deepEqual(readdirSync(dir), ["portable-boot.js"]);
});

test("none of the shared explorer engine can perform I/O", () => {
  const engine = new URL("../../model/static/model/js/explore/engine/", import.meta.url);
  for (const file of readdirSync(engine)) {
    const source = readFileSync(join(engine.pathname.replace(/^\//, ""), file), "utf8");
    for (const forbidden of ["fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "localStorage", "document."]) {
      assert.equal(source.includes(forbidden), false, `${file} must not reference ${forbidden}`);
    }
  }
});
