import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMapping,
  canCreate,
  canPreview,
  describeSummary,
  emptyRow,
  endpointResolvers,
  fieldOptions,
  KINDS,
  normaliseHeader,
  suggestMapping,
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

test("endpoint resolvers list the OnyxJar id and only identity-eligible attributes", () => {
  const resolvers = endpointResolvers([{ type_id: "T1", name: "Application", attributes: target.attributes }]);

  assert.deepEqual(
    resolvers.map((resolver) => resolver.value),
    ["id", "attribute:T1:app_id", "attribute:T1:owner"],
  );
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
    { ...emptyRow(), field: "endpoint.object" },
  ];

  assert.deepEqual(buildMapping({ kind: KINDS.RELATIONSHIP, typeId: "R", rows }).columns, [
    { column: 0, field: "endpoint.subject", by: "attribute:app_id", object_type_id: "TYPE-1" },
    { column: 1, field: "endpoint.object", by: "id" },
  ]);
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
