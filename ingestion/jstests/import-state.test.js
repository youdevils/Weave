import assert from "node:assert/strict";
import test from "node:test";

import {
  availableSteps,
  buildMapping,
  canCreate,
  canPreview,
  defaultResolver,
  describeSummary,
  emptyRow,
  endpointResolvers,
  fieldOptions,
  KINDS,
  normaliseHeader,
  suggestMapping,
  WIZARD_STEPS,
} from "../static/ingestion/js/import-state.js";

const target = {
  attributes: [
    { key: "app_id", name: "App ID", data_type: "text", identity_eligible: true },
    { key: "owner", name: "Owner", data_type: "text", identity_eligible: true },
    { key: "live", name: "Live", data_type: "boolean", identity_eligible: false },
  ],
};

test("headers are compared ignoring case and punctuation", () => {
  assert.equal(normaliseHeader("  App_ID "), "appid");
  assert.equal(normaliseHeader("Is active?"), "isactive");
  assert.equal(normaliseHeader(null), "");
});

test("object targets offer identity, built-in and attribute fields", () => {
  const values = fieldOptions(KINDS.OBJECT, target).map((option) => option.value);

  assert.deepEqual(values, [
    "identity.key",
    "identity.id",
    "field.name",
    "field.description",
    "field.is_active",
    "attribute.app_id",
    "attribute.owner",
    "attribute.live",
  ]);
});

test("relationship targets offer endpoints instead of name and description", () => {
  const values = fieldOptions(KINDS.RELATIONSHIP, target).map((option) => option.value);

  assert.ok(values.includes("endpoint.subject"));
  assert.ok(values.includes("endpoint.object"));
  assert.ok(!values.includes("field.name"));
  assert.ok(values.includes("attribute.owner"));
});

test("endpoint resolvers list the OnyxJar Key and only identity-eligible attributes", () => {
  const resolvers = endpointResolvers([{ type_id: "T1", name: "Application", attributes: target.attributes }]);

  assert.deepEqual(
    resolvers.map((resolver) => resolver.value),
    ["key", "attribute:T1:app_id", "attribute:T1:owner", "id"],
  );
});

test("endpoint resolvers offer a per-type pin only when more than one type is allowed", () => {
  const objectTypes = [
    { type_id: "T1", name: "Application", attributes: target.attributes },
    { type_id: "T2", name: "Person", attributes: [] },
  ];

  const scopedToOne = endpointResolvers(objectTypes, ["T1"]);
  assert.deepEqual(
    scopedToOne.map((resolver) => resolver.value),
    ["key", "attribute:T1:app_id", "attribute:T1:owner", "id"],
  );

  const scopedToBoth = endpointResolvers(objectTypes, ["T1", "T2"]);
  assert.deepEqual(
    scopedToBoth.map((resolver) => resolver.value),
    ["key", "key:T1", "key:T2", "attribute:T1:app_id", "attribute:T1:owner", "id"],
  );

  const unscoped = endpointResolvers(objectTypes);
  assert.deepEqual(
    unscoped.map((resolver) => resolver.value),
    ["key", "key:T1", "key:T2", "attribute:T1:app_id", "attribute:T1:owner", "id"],
  );
});

test("defaultResolver pins to the one allowed type, and leaves the choice open otherwise", () => {
  assert.equal(defaultResolver({ subject_type_ids: ["T1"] }, "subject"), "key:T1");
  assert.equal(defaultResolver({ subject_type_ids: ["T1", "T2"] }, "subject"), "");
  assert.equal(defaultResolver({ object_type_ids: [] }, "object"), "");
  assert.equal(defaultResolver(undefined, "subject"), "");
});

test("suggestions match a header to a field label or key, each field once", () => {
  const options = fieldOptions(KINDS.OBJECT, target);
  const suggestion = suggestMapping(["app_id", "Name", "OWNER", "Owner", "Unknown"], options);

  assert.deepEqual(suggestion, { 0: "attribute.app_id", 1: "field.name", 2: "attribute.owner" });
});

test("suggestions use synonyms for endpoints and ids but never turn matching on", () => {
  const options = fieldOptions(KINDS.RELATIONSHIP, target);

  assert.deepEqual(suggestMapping(["From", "To", "OnyxJar ID"], options), {
    0: "endpoint.subject",
    1: "endpoint.object",
    2: "identity.id",
  });
});

test("the mapping document lists only mapped columns, by index", () => {
  const rows = [
    { ...emptyRow(), field: "attribute.app_id", match: true },
    emptyRow(),
    { ...emptyRow(), field: "field.name" },
  ];

  assert.deepEqual(buildMapping({ kind: KINDS.OBJECT, typeId: "T", rows }), {
    target: { kind: "object", type_id: "T" },
    columns: [
      { column: 0, field: "attribute.app_id", match: true },
      { column: 2, field: "field.name" },
    ],
  });
});

test("match is only sent for an attribute on an object import", () => {
  const rows = [
    { ...emptyRow(), field: "field.name", match: true },
    { ...emptyRow(), field: "attribute.app_id", match: true },
  ];

  const object = buildMapping({ kind: KINDS.OBJECT, typeId: "T", rows });
  assert.equal(object.columns[0].match, undefined);
  assert.equal(object.columns[1].match, true);

  const relationship = buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "T", rows });
  assert.equal(relationship.columns[1].match, undefined);
});

test("endpoint resolvers become by / object_type_id", () => {
  const rows = [
    { ...emptyRow(), field: "endpoint.subject", resolver: "attribute:TYPE-1:app_id" },
    { ...emptyRow(), field: "endpoint.object", resolver: "id" },
  ];

  assert.deepEqual(buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "R", rows }).columns, [
    { column: 0, field: "endpoint.subject", by: "attribute:app_id", object_type_id: "TYPE-1" },
    { column: 1, field: "endpoint.object", by: "id" },
  ]);
});

test("a key resolver with no pin searches every allowed type", () => {
  const rows = [{ ...emptyRow(), field: "endpoint.subject", resolver: "key" }];

  assert.deepEqual(buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "R", rows }).columns, [
    { column: 0, field: "endpoint.subject", by: "key" },
  ]);
});

test("a key resolver pinned to one type sends its object_type_id", () => {
  const rows = [{ ...emptyRow(), field: "endpoint.subject", resolver: "key:TYPE-1" }];

  assert.deepEqual(buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "R", rows }).columns, [
    { column: 0, field: "endpoint.subject", by: "key", object_type_id: "TYPE-1" },
  ]);
});

test("an endpoint column with no resolver chosen sends no `by`, forcing an explicit choice", () => {
  const rows = [{ ...emptyRow(), field: "endpoint.subject" }];

  assert.deepEqual(buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "R", rows }).columns, [
    { column: 0, field: "endpoint.subject" },
  ]);
});

test("suggestions recognise key-based headers for objects and relationship endpoints", () => {
  const objectOptions = fieldOptions(KINDS.OBJECT, target);
  assert.deepEqual(suggestMapping(["OnyxJar Key", "Name"], objectOptions), {
    0: "identity.key",
    1: "field.name",
  });

  const relationshipOptions = fieldOptions(KINDS.RELATIONSHIP, target);
  assert.deepEqual(suggestMapping(["Source object key", "Target object key"], relationshipOptions), {
    0: "endpoint.subject",
    1: "endpoint.object",
  });
});

test("previews need a source, a target and at least one mapped column", () => {
  assert.equal(canPreview({ source: {}, target: {}, mapping: { columns: [{}] } }), true);
  assert.equal(canPreview({ source: {}, target: {}, mapping: { columns: [] } }), false);
  assert.equal(canPreview({ source: null, target: {}, mapping: { columns: [{}] } }), false);
});

test("creating needs a fresh, unblocked preview", () => {
  assert.equal(canCreate({ preview: { blocked: false }, previewIsFresh: true }), true);
  assert.equal(canCreate({ preview: { blocked: true }, previewIsFresh: true }), false);
  assert.equal(canCreate({ preview: { blocked: false }, previewIsFresh: false }), false);
  assert.equal(canCreate({ preview: null, previewIsFresh: true }), false);
});

test("the summary line names the kind of record", () => {
  assert.equal(
    describeSummary({ kind: "object", creates: 92, updates: 31, no_ops: 24 }),
    "92 objects to create, 31 to update, 24 unchanged",
  );
  assert.match(describeSummary({ kind: "relationship", creates: 1, updates: 0, no_ops: 0 }), /relationships/);
});

test("the workflow opens one step further at a time as its prerequisites are met", () => {
  const mapping = { columns: [{ column: 0, field: "field.name" }] };
  const previewed = { blocked: false, change_count: 1 };
  const open = (input) => WIZARD_STEPS.filter((step) => availableSteps(input)[step]);

  assert.deepEqual(open({}), ["upload"]);
  assert.deepEqual(open({ source: {} }), ["upload", "target"]);
  assert.deepEqual(open({ source: {}, target: {}, mapping: { columns: [] } }), ["upload", "target", "map"]);
  assert.deepEqual(open({ source: {}, target: {}, mapping }), ["upload", "target", "map", "preview"]);
  assert.deepEqual(open({ source: {}, target: {}, mapping, preview: previewed, previewIsFresh: true }), WIZARD_STEPS);
});

test("a stale or blocked preview does not open the final step", () => {
  const base = { source: {}, target: {}, mapping: { columns: [{ column: 0, field: "field.name" }] } };

  assert.equal(availableSteps({ ...base, preview: { blocked: false }, previewIsFresh: false }).create, false);
  assert.equal(availableSteps({ ...base, preview: { blocked: true }, previewIsFresh: true }).create, false);
});
