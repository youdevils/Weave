import assert from "node:assert/strict";
import test from "node:test";

import {
  banner,
  displayValue,
  escapeHtml,
  formatBytes,
  mappingTable,
  previewPanel,
  problemsFromError,
  typeOptions,
  uploadSummary,
} from "../static/ingestion/js/import-render.js";

const HOSTILE = `<img src=x onerror="alert(1)"><script>alert(2)</script>`;

const OWN_TAGS = new Set([
  "div", "dl", "dt", "dd", "ul", "li", "p", "span", "strong", "h3", "details", "summary", "table",
  "thead", "tbody", "tr", "th", "td", "select", "optgroup", "option", "label", "input",
]);

function assertInert(html) {
  // Every tag in the output is one this module wrote; none came from the hostile text,
  // which survives only as escaped text.
  const tags = [...html.matchAll(/<\/?([a-z][a-z0-9]*)/gi)].map((match) => match[1].toLowerCase());
  for (const tag of tags) assert.ok(OWN_TAGS.has(tag), `unexpected <${tag}> in ${html}`);
  assert.ok(html.includes("&lt;"), html);
}

test("escapeHtml neutralises markup and quotes", () => {
  assert.equal(escapeHtml(`<a href="x">&'</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;");
  assert.equal(escapeHtml(null), "");
});

test("blank values are shown as an empty marker, not dropped", () => {
  assert.match(displayValue(""), /import-empty/);
  assert.match(displayValue(null), /import-empty/);
  assert.equal(displayValue(false), "false");
});

test("file sizes are human readable", () => {
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MB");
});

test("an upload summary escapes the filename, headers, cells and warnings", () => {
  const html = uploadSummary({
    source: { filename: HOSTILE, format: "csv", size_bytes: 10, row_count: 1, column_count: 1 },
    columns: [{ index: 0, header: HOSTILE }],
    sampleRows: [[HOSTILE]],
    warnings: [HOSTILE],
  });

  assertInert(html);
  assert.ok(html.includes("&lt;script&gt;"));
});

test("the mapping table escapes headers, samples and attribute names", () => {
  const target = { attributes: [{ key: "k", name: HOSTILE, data_type: "text", identity_eligible: true }] };
  const html = mappingTable({
    kind: "object",
    target,
    columns: [{ index: 0, header: HOSTILE }],
    sampleRows: [[HOSTILE]],
    rows: [{ field: "attribute.k", match: false, resolver: "id" }],
    objectTypes: [],
  });

  assertInert(html);
  assert.match(html, /data-role="field"/);
  assert.match(html, /data-role="match"/);
});

test("a field already used by another column is disabled in the others", () => {
  const target = { attributes: [] };
  const html = mappingTable({
    kind: "object",
    target,
    columns: [{ index: 0, header: "A" }, { index: 1, header: "B" }],
    sampleRows: [],
    rows: [{ field: "field.name" }, { field: "" }],
    objectTypes: [],
  });

  const second = html.split('data-column="1"')[1];
  assert.match(second, /value="field.name" disabled/);
});

test("relationship endpoints get an 'identified by' choice", () => {
  const html = mappingTable({
    kind: "relationship",
    target: { attributes: [] },
    columns: [{ index: 0, header: "From" }],
    sampleRows: [],
    rows: [{ field: "endpoint.subject", resolver: "id" }],
    objectTypes: [{ type_id: "T", name: "App", attributes: [{ key: "app_id", name: "App ID", identity_eligible: true }] }],
  });

  assert.match(html, /data-role="resolver"/);
  assert.match(html, /App: App ID/);
});

test("type options mark the selected type and escape names", () => {
  const html = typeOptions([{ type_id: "1", name: HOSTILE }, { type_id: "2", name: "Ok" }], "2");

  assertInert(html);
  assert.match(html, /value="2" selected/);
});

test("a blocked preview lists problems with row numbers, escaped, and hides counts", () => {
  const html = previewPanel({
    blocked: true,
    problem_count: 3,
    problems: [{ row: 4, message: HOSTILE, code: "x" }],
    summary: { kind: "object", rows: 10 },
    items: [],
    change_count: 0,
  });

  assertInert(html);
  assert.match(html, /Row 4/);
  assert.match(html, /2 more/);
  assert.ok(!html.includes("CREATE"));
});

test("a preview shows CREATE / UPDATE / NO-OP counts, duplicates, and escaped diffs", () => {
  const html = previewPanel({
    blocked: false,
    problem_count: 0,
    problems: [],
    change_count: 2,
    summary: {
      kind: "object", rows: 147, creates: 92, updates: 31, no_ops: 24, field_changes: 40,
      duplicate_identities: 3, duplicate_rows: 7, unconverted_cells: 0, warnings: [HOSTILE],
    },
    items: [
      { operation: "update", label: HOSTILE, row: 2, rows: 2, fields: [{ field: "name", before: HOSTILE, after: null }] },
    ],
  });

  assertInert(html);
  assert.match(html, /92 CREATE/);
  assert.match(html, /31 UPDATE/);
  assert.match(html, /24 NO-OP/);
  assert.match(html, /3 \(across 7 rows/);
  assert.match(html, /import-empty/);
});

test("a preview with nothing to change says so plainly", () => {
  const html = previewPanel({
    blocked: false, problem_count: 0, problems: [], change_count: 0, items: [],
    summary: { kind: "object", rows: 5, creates: 0, updates: 0, no_ops: 5, field_changes: 0, warnings: [] },
  });

  assert.match(html, /No changes detected/);
});

test("problems returned with a refused create are rendered escaped", () => {
  const html = problemsFromError({ problem_count: 1, problems: [{ row: 2, message: HOSTILE }] });

  assertInert(html);
  assert.equal(problemsFromError(null), "");
});

test("banners escape the message and render nothing when empty", () => {
  assertInert(banner("danger", HOSTILE));
  assert.equal(banner("danger", ""), "");
});
