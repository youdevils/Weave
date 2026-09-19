import test from "node:test";
import assert from "node:assert/strict";

import {
  escapeHtml,
  formatCardinality,
  renderChips,
  renderCounts,
  renderDetails,
  renderDetailsError,
  renderEmptyDetails,
  renderFilterBuilder,
  renderNotices,
  renderResults,
  renderSelectionChip,
  renderTypeFilters,
  safeUrlHref,
} from "../static/model/js/explore/explorer-render.js";
import { initialState, toggleObjectType } from "../static/model/js/explore/explorer-state.js";

const HOSTILE = `<img src=x onerror="alert('x')"> & "quotes"`;

function assertNoLiveMarkup(html) {
  assert.ok(!html.includes("<img"), "raw <img> tag leaked");
  assert.ok(!/onerror="/.test(html), "unescaped attribute leaked");
}

// ---------------------------------------------------------------------------

test("escapeHtml escapes all five significant characters", () => {
  assert.equal(escapeHtml(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(42), "42");
});

test("formatCardinality shows an open maximum as *", () => {
  assert.equal(formatCardinality(0, null), "0..*");
  assert.equal(formatCardinality(1, 1), "1..1");
});

// ---------------------------------------------------------------------------
// Search results
// ---------------------------------------------------------------------------

const result = (over = {}) => ({
  id: "o1",
  name: "Web Portal",
  typeName: "Application",
  isProposed: false,
  inView: true,
  subtitle: null,
  match: null,
  ...over,
});

test("no results shows a clear message that repeats the query safely", () => {
  const html = renderResults({ query: HOSTILE, total: 0, results: [], truncated: false });

  assert.match(html, /No objects match/);
  assertNoLiveMarkup(html);
});

test("an empty query renders nothing", () => {
  assert.equal(renderResults({ query: "", total: 0, results: [] }), "");
  assert.equal(renderResults(null), "");
});

test("results show the type, and disambiguate duplicates with a detail line", () => {
  const html = renderResults({
    query: "alice",
    total: 2,
    truncated: false,
    results: [
      result({ id: "a1", name: "Alice", typeName: "Person", subtitle: "Email: alice@a.com" }),
      result({ id: "a2", name: "Alice", typeName: "Person", subtitle: "Email: alice@b.com" }),
    ],
  });

  assert.equal((html.match(/data-action="pick-result"/g) || []).length, 2);
  assert.match(html, /data-id="a1"/);
  assert.match(html, /data-id="a2"/);
  assert.match(html, /alice@a\.com/);
  assert.match(html, /alice@b\.com/);
  assert.match(html, /2 matches/);
});

test("an attribute match shows which field matched", () => {
  const html = renderResults({
    query: "carol",
    total: 1,
    truncated: false,
    results: [result({ match: { field: "Owner", snippet: "Carol" } })],
  });

  assert.match(html, /Owner: Carol/);
});

test("results outside the current view and proposed results are flagged", () => {
  const html = renderResults({
    query: "x",
    total: 1,
    truncated: false,
    results: [result({ inView: false, isProposed: true })],
  });

  assert.match(html, /not in view/);
  assert.match(html, /Proposed/);
});

test("a large result set says it is truncated and asks to refine", () => {
  const html = renderResults({
    query: "p",
    total: 480,
    truncated: true,
    results: Array.from({ length: 25 }, (_, i) => result({ id: `o${i}`, name: `P${i}` })),
  });

  assert.match(html, /Showing 25 of 480/);
  assert.match(html, /Refine your search/);
});

test("names and details from users are escaped in results", () => {
  const html = renderResults({
    query: "x",
    total: 1,
    truncated: false,
    results: [result({ name: HOSTILE, typeName: HOSTILE, subtitle: HOSTILE })],
  });

  assertNoLiveMarkup(html);
  assert.match(html, /&lt;img/);
});

// ---------------------------------------------------------------------------
// Details
// ---------------------------------------------------------------------------

const ref = (over = {}) => ({ id: "o2", name: "Ops", typeId: "t2", typeName: "Team", isProposed: false, inView: true, ...over });

const objectDetails = (over = {}) => ({
  kind: "object",
  id: "o1",
  name: "Web Portal",
  description: "",
  type: { id: "t1", name: "Application" },
  isProposed: false,
  inView: true,
  attributes: [
    { key: "status", label: "Status", display: "Live" },
    { key: "owner", label: "Owner", display: null },
  ],
  relationships: [
    {
      type: { id: "r1", name: "Uses" },
      items: [
        { relationshipId: "rel1", direction: "incoming", isProposed: false, inView: true, counterpart: ref(), attributes: [{ label: "Since", display: "2020" }] },
      ],
    },
  ],
  connectionCount: 1,
  hiddenConnectionIds: [],
  ...over,
});

test("no selection has a clear empty state", () => {
  assert.match(renderDetails(null), /Nothing selected/);
  assert.equal(renderDetails(null), renderEmptyDetails());
});

test("object details show name, type, attributes (missing ones as not set) and grouped connections", () => {
  const html = renderDetails(objectDetails());

  assert.match(html, /Web Portal/);
  assert.match(html, /Application/);
  assert.match(html, /Status/);
  assert.match(html, /Live/);
  assert.match(html, /Not set/);
  assert.match(html, /Uses/);
  assert.match(html, /data-action="select-object" data-id="o2"/);
  assert.match(html, /data-action="select-relationship" data-id="rel1"/);
  assert.match(html, /Since: 2020/);
});

test("connection direction is shown", () => {
  const incoming = renderDetails(objectDetails());
  const outgoing = renderDetails(
    objectDetails({
      relationships: [
        { type: { id: "r1", name: "Uses" }, items: [{ relationshipId: "x", direction: "outgoing", inView: true, counterpart: ref(), attributes: [] }] },
      ],
    }),
  );

  assert.match(incoming, /&larr;/);
  assert.match(outgoing, /&rarr;/);
});

test("an object with no relationships says so", () => {
  assert.match(renderDetails(objectDetails({ relationships: [], connectionCount: 0 })), /no relationships/);
});

test("hidden connections offer a way to bring them into view", () => {
  const html = renderDetails(objectDetails({ hiddenConnectionIds: ["h1", "h2"] }));

  assert.match(html, /Show 2 hidden connections/);
  assert.match(html, /data-ids="h1,h2"/);
});

test("a single hidden connection uses the singular", () => {
  assert.match(renderDetails(objectDetails({ hiddenConnectionIds: ["h1"] })), /Show 1 hidden connection</);
});

test("no hidden-connections button when everything is visible", () => {
  assert.doesNotMatch(renderDetails(objectDetails()), /include-connected/);
});

test("a selected object hidden by filters is called out with a way to show it", () => {
  const html = renderDetails(objectDetails({ inView: false }));

  assert.match(html, /hidden by the current filters/);
  assert.match(html, /data-action="show-selection"/);
  assert.doesNotMatch(renderDetails(objectDetails({ inView: true })), /show-selection/);
});

test("connections whose counterpart is not in view are marked", () => {
  const html = renderDetails(
    objectDetails({
      relationships: [
        { type: { id: "r1", name: "Uses" }, items: [{ relationshipId: "x", direction: "outgoing", inView: false, counterpart: ref({ inView: false }), attributes: [] }] },
      ],
    }),
  );

  assert.match(html, /not in view/);
  assert.match(html, /model-explorer-faded/);
});

test("relationship details show type, both endpoints, attributes and cardinality", () => {
  const html = renderDetails({
    kind: "relationship",
    id: "rel1",
    type: { id: "r1", name: "Uses" },
    source: ref({ id: "s", name: "Ops", typeName: "Team" }),
    target: ref({ id: "t", name: "Web Portal", typeName: "Application" }),
    attributes: [{ key: "since", label: "Since", display: "2021" }],
    validFrom: "2021-01-01T00:00:00+00:00",
    validTo: null,
    cardinality: { subject: { minimum: 1, maximum: null }, object: { minimum: 0, maximum: 1 } },
    isProposed: true,
    inView: true,
  });

  assert.match(html, /Uses/);
  assert.match(html, /data-id="s"/);
  assert.match(html, /data-id="t"/);
  assert.match(html, /Since/);
  assert.match(html, /2021/);
  assert.match(html, /Allowed: Team 1\.\.\* &rarr; 0\.\.1 Application/);
  assert.match(html, /Proposed/);
  assert.match(html, /Valid from 2021-01-01/);
});

test("a relationship without a matching rule shows no cardinality line", () => {
  const html = renderDetails({
    kind: "relationship",
    id: "x",
    type: { id: "r", name: "Uses" },
    source: ref(),
    target: ref({ id: "o3" }),
    attributes: [],
    validFrom: null,
    validTo: null,
    cardinality: null,
    isProposed: false,
    inView: true,
  });

  assert.doesNotMatch(html, /Allowed:/);
});

test("all user-supplied text in details is escaped", () => {
  const html = renderDetails(
    objectDetails({
      name: HOSTILE,
      description: HOSTILE,
      type: { id: "t", name: HOSTILE },
      attributes: [{ key: "k", label: HOSTILE, display: HOSTILE }],
      relationships: [
        {
          type: { id: "r", name: HOSTILE },
          items: [{ relationshipId: "x", direction: "outgoing", inView: true, counterpart: ref({ name: HOSTILE, typeName: HOSTILE }), attributes: [{ label: HOSTILE, display: HOSTILE }] }],
        },
      ],
    }),
  );

  assertNoLiveMarkup(html);
});

test("a stale-selection message is escaped and explains itself", () => {
  const html = renderDetailsError(`Gone <b>${HOSTILE}</b>`);

  assert.match(html, /Selection cleared/);
  assertNoLiveMarkup(html);
});

// ---------------------------------------------------------------------------
// State bar
// ---------------------------------------------------------------------------

const summary = (over = {}) => ({
  totalObjects: 77,
  totalRelationships: 164,
  matchingObjects: 77,
  shownObjects: 77,
  shownRelationships: 164,
  truncated: false,
  ...over,
});

test("counts show shown of total for objects and relationships", () => {
  assert.equal(renderCounts(summary({ shownObjects: 12, shownRelationships: 9 })), "12 of 77 objects &middot; 9 of 164 relationships");
  assert.match(renderCounts(summary({ totalObjects: 1, shownObjects: 1, totalRelationships: 1, shownRelationships: 1 })), /1 of 1 object &middot; 1 of 1 relationship$/);
});

test("large counts are grouped", () => {
  assert.match(renderCounts(summary({ totalObjects: 12345, shownObjects: 300 })), /300 of 12,345 objects/);
});

test("chips are removable and escaped", () => {
  const html = renderChips([{ kind: "attributeFilter", key: "0", label: HOSTILE }]);

  assert.match(html, /data-action="remove-chip"/);
  assert.match(html, /data-chip-kind="attributeFilter"/);
  assertNoLiveMarkup(html);
});

test("the selection chip is only shown when something is selected", () => {
  assert.equal(renderSelectionChip(null), "");
  assert.match(renderSelectionChip("Web Portal"), /Selected: Web Portal/);
  assert.match(renderSelectionChip("Web Portal"), /clear-selection/);
  assertNoLiveMarkup(renderSelectionChip(HOSTILE));
});

test("an empty model is explained", () => {
  const html = renderNotices(summary({ totalObjects: 0, shownObjects: 0, matchingObjects: 0 }), { hasNarrowing: false });

  assert.match(html, /no objects yet/);
});

test("a zero-result filter is explained and offers to clear the filters", () => {
  const html = renderNotices(summary({ shownObjects: 0, matchingObjects: 0 }), { hasNarrowing: true });

  assert.match(html, /No objects match the current filters/);
  assert.match(html, /data-action="clear-filters"/);
});

test("a truncated view says why objects are missing", () => {
  const html = renderNotices(summary({ shownObjects: 300, matchingObjects: 1240, truncated: true }), { hasNarrowing: false });

  assert.match(html, /300 best-connected of 1,240 matching/);
  assert.match(html, /Narrow the view/);
});

test("nothing to say when the view is simply complete", () => {
  assert.equal(renderNotices(summary(), { hasNarrowing: false }), "");
});

// ---------------------------------------------------------------------------
// Filter panel
// ---------------------------------------------------------------------------

const facets = {
  objectTypes: [
    {
      id: "t-app",
      name: "Application",
      isProposed: false,
      count: 3,
      swatch: { background: "#EDF2FF", border: "#4C6EF5", shape: "box" },
      attributes: [
        { key: "status", name: "Status", dataType: "choice", op: "in", values: [{ value: "Live", count: 2 }, { value: "Retired", count: 1 }] },
        { key: "owner", name: "Owner", dataType: "text", op: "contains", values: [] },
        { key: "users", name: "Users", dataType: "number", op: "range", values: [] },
        { key: "launched", name: "Launched", dataType: "date", op: "range", values: [] },
      ],
    },
    { id: "t-team", name: "Team", isProposed: true, count: 1, swatch: null, attributes: [] },
  ],
  relationshipTypes: [{ id: "r-uses", name: "Uses", isProposed: false, count: 4, swatch: { colour: "#495057", lineStyle: "dashed" } }],
};

test("type filters show every type with counts and its resolved swatch, checked unless hidden", () => {
  const html = renderTypeFilters(facets, toggleObjectType(initialState(), "t-team"));

  assert.match(html, /Application/);
  // Object swatch: the resolved colours, as an SVG marker.
  assert.match(html, /<svg class="model-explorer-swatch" data-shape="box"/);
  assert.match(html, /fill="#EDF2FF" stroke="#4C6EF5"/);
  // Relationship swatch: unchanged colour and line style.
  assert.match(html, /border-top-color: #495057;/);
  assert.match(html, /data-line="dashed"/);
  const app = /<input[^>]*data-id="t-app"[^>]*>/.exec(html)[0];
  const team = /<input[^>]*data-id="t-team"[^>]*>/.exec(html)[0];
  assert.match(app, /checked/);
  assert.doesNotMatch(team, /checked/);
});

// ---------------------------------------------------------------------------
// Legend swatches: object types show their configured shape or icon
// ---------------------------------------------------------------------------

const objectFacets = (swatch) => ({
  objectTypes: [{ id: "t", name: "Thing", isProposed: false, count: 1, swatch, attributes: [] }],
  relationshipTypes: [],
});

const shapeSwatch = (shape) => ({ background: "#FFF3BF", border: "#F08C00", shape, icon: null, image: null });

const swatchHtml = (swatch) => /<svg class="model-explorer-swatch"[\s\S]*?<\/svg>/.exec(renderTypeFilters(objectFacets(swatch), initialState()))[0];

test("every curated shape gets its own marker geometry", () => {
  const expected = {
    box: "<rect",
    ellipse: "<ellipse",
    circle: "<circle",
    database: "<path",
    dot: "<circle",
    square: "<rect",
    diamond: "<polygon",
    triangle: "<polygon",
    hexagon: "<polygon",
    star: "<polygon",
  };
  const seen = new Set();

  for (const [shape, element] of Object.entries(expected)) {
    const html = swatchHtml(shapeSwatch(shape));

    assert.match(html, new RegExp(`data-shape="${shape}"`), shape);
    assert.ok(html.includes(element), `${shape} should draw ${element}`);
    seen.add(html.replace(/data-shape="[^"]*"|aria-label="[^"]*"/g, ""));
  }
  assert.equal(seen.size, 10, "each shape is visually distinct");
});

test("shape markers are drawn in the type's own fill and border colours", () => {
  for (const shape of ["box", "hexagon", "star", "database"]) {
    const html = swatchHtml({ background: "#112233", border: "#445566", shape, icon: null, image: null });

    assert.match(html, /fill="#112233" stroke="#445566"/, shape);
  }
});

test("a star has ten alternating points", () => {
  const points = /points="([^"]+)"/.exec(swatchHtml(shapeSwatch("star")))[1].split(" ");

  assert.equal(points.length, 10);
});

test("a configured icon is drawn as a circle in the type colours around the same glyph", () => {
  const image = "data:image/svg+xml;charset=utf-8,%3Csvg%20stroke%3D%22%23AA0000%22%3E%3C%2Fsvg%3E";
  const html = swatchHtml({ background: "#EDF2FF", border: "#AA0000", shape: "hexagon", icon: "database", image });

  assert.match(html, /data-shape="icon" data-icon="database"/);
  assert.match(html, /<circle[^>]*fill="#EDF2FF" stroke="#AA0000"/);
  assert.ok(html.includes(`<image href="${image}"`));
  assert.ok(!html.includes("<polygon"), "the icon replaces the configured shape");
});

test("an icon type without an image falls back to its shape", () => {
  const html = swatchHtml({ background: "#EDF2FF", border: "#4C6EF5", shape: "diamond", icon: "person", image: null });

  assert.match(html, /data-shape="diamond"/);
  assert.ok(!html.includes("<image"));
});

test("an unknown shape falls back to the box marker", () => {
  assert.match(swatchHtml(shapeSwatch("blob")), /data-shape="box"/);
  assert.match(swatchHtml(shapeSwatch("constructor")), /data-shape="box"/);
});

test("a type without swatch data renders no marker and the row still works", () => {
  const html = renderTypeFilters(objectFacets(null), initialState());

  assert.doesNotMatch(html, /model-explorer-swatch/);
  assert.match(html, /data-action="toggle-object-type"/);
});

test("swatch values from the server are escaped", () => {
  const html = renderTypeFilters(
    objectFacets({ background: HOSTILE, border: HOSTILE, shape: HOSTILE, icon: HOSTILE, image: HOSTILE }),
    initialState(),
  );

  assertNoLiveMarkup(html);
});

test("the legend stays compact: one small marker per type, not a list of settings", () => {
  const html = renderTypeFilters(
    { objectTypes: [1, 2, 3].map((n) => ({ id: `t${n}`, name: `T${n}`, count: n, swatch: shapeSwatch("star"), attributes: [] })), relationshipTypes: [] },
    initialState(),
  );

  assert.equal((html.match(/<svg /g) || []).length, 3);
  assert.doesNotMatch(html, /Shape|Icon|Border|Fill|Size/, "no configuration details in the legend");
});

test("a hidden type stays in the panel so it can be shown again", () => {
  const html = renderTypeFilters(facets, toggleObjectType(initialState(), "t-app"));

  assert.match(html, /data-id="t-app"/);
});

test("type names are escaped in the filter panel", () => {
  const html = renderTypeFilters({ objectTypes: [{ id: "t", name: HOSTILE, count: 0, attributes: [], swatch: null }], relationshipTypes: [] }, initialState());

  assertNoLiveMarkup(html);
});

test("the builder offers value checkboxes for choice attributes", () => {
  const html = renderFilterBuilder(facets, { typeId: "t-app", key: "status" });

  assert.match(html, /data-op="in"/);
  assert.match(html, /data-builder-value="Live"/);
  assert.match(html, /data-builder-value="Retired"/);
});

test("the builder offers a text box for text attributes", () => {
  assert.match(renderFilterBuilder(facets, { typeId: "t-app", key: "owner" }), /data-builder-text/);
});

test("the builder offers min and max for numbers and dates with the right input type", () => {
  const number = renderFilterBuilder(facets, { typeId: "t-app", key: "users" });
  const date = renderFilterBuilder(facets, { typeId: "t-app", key: "launched" });

  assert.match(number, /type="number" class="form-control form-control-sm" data-builder-min/);
  assert.match(date, /type="date" class="form-control form-control-sm" data-builder-min/);
});

test("the builder defaults to the first type and attribute and only lists types that have attributes", () => {
  const html = renderFilterBuilder(facets, { typeId: null, key: null });

  assert.match(html, /data-type-id="t-app"/);
  assert.match(html, /data-key="status"/);
  assert.doesNotMatch(html, /<option value="t-team"/);
});

test("with no filterable attributes the builder says so", () => {
  const html = renderFilterBuilder({ objectTypes: [{ id: "t", name: "Team", attributes: [] }], relationshipTypes: [] }, {});

  assert.match(html, /No filterable attributes/);
});

// ---------------------------------------------------------------------------
// URL attributes: the definition's datatype (not the value) decides the link
// ---------------------------------------------------------------------------

const LINK = "https://example.com/docs?a=1&b=2#top";

const urlAttribute = (over = {}) => ({ key: "site", label: "Website", dataType: "url", value: LINK, display: LINK, ...over });

const relationshipWith = (attributes) => ({
  kind: "relationship",
  id: "rel1",
  type: { id: "r1", name: "Uses" },
  source: ref({ id: "s", name: "Ops", typeName: "Team" }),
  target: ref({ id: "t", name: "Web Portal", typeName: "Application" }),
  attributes,
  validFrom: null,
  validTo: null,
  cardinality: null,
  isProposed: false,
  inView: true,
});

test("a url attribute renders as a safe link to exactly the stored value", () => {
  const html = renderDetails(objectDetails({ attributes: [urlAttribute()] }));

  assert.match(html, /<a class="model-explorer-url" href="https:\/\/example\.com\/docs\?a=1&amp;b=2#top" target="_blank" rel="noopener noreferrer nofollow">/);
  assert.match(html, />https:\/\/example\.com\/docs\?a=1&amp;b=2#top<\/a>/);
});

test("a bare origin keeps its stored form as the link target (no normalised trailing slash)", () => {
  const html = renderDetails(objectDetails({ attributes: [urlAttribute({ display: "https://example.com" })] }));

  assert.match(html, /href="https:\/\/example\.com"/);
});

test("a text attribute holding the same string stays plain text", () => {
  const html = renderDetails(objectDetails({ attributes: [urlAttribute({ dataType: "text" })] }));

  assert.doesNotMatch(html, /<a /);
  assert.match(html, /https:\/\/example\.com\/docs/);
});

test("urls are never inferred: a string attribute without a datatype is plain text", () => {
  const html = renderDetails(objectDetails({ attributes: [{ key: "site", label: "Website", display: LINK }] }));

  assert.doesNotMatch(html, /<a /);
});

for (const unsafe of [
  "javascript:alert(1)",
  "JavaScript:alert(1)",
  "  javascript:alert(1)",
  "\tjava\nscript:alert(1)",
  "data:text/html,<script>alert(1)</script>",
  "vbscript:msgbox(1)",
  "file:///etc/passwd",
  "//example.com/relative",
  "/docs/relative",
  "not a url",
]) {
  test(`an unsafe or non-http(s) url value is shown as text, never a link: ${JSON.stringify(unsafe)}`, () => {
    assert.equal(safeUrlHref(unsafe), null);

    const html = renderDetails(objectDetails({ attributes: [urlAttribute({ display: unsafe })] }));

    assert.doesNotMatch(html, /<a /);
    assert.doesNotMatch(html, /href=/);
    assert.doesNotMatch(html, /<script/);
  });
}

test("safeUrlHref accepts http and https only", () => {
  assert.equal(safeUrlHref("http://example.com/a"), "http://example.com/a");
  assert.equal(safeUrlHref("https://example.com/a"), "https://example.com/a");
  assert.equal(safeUrlHref(" https://example.com/a "), "https://example.com/a");
  assert.equal(safeUrlHref(null), null);
  assert.equal(safeUrlHref(42), null);
});

test("url values and labels are escaped, so they cannot inject markup or break out of href", () => {
  const evil = `https://example.com/"><img src=x onerror="alert('x')">`;
  const html = renderDetails(objectDetails({ attributes: [urlAttribute({ label: HOSTILE, display: evil })] }));

  assertNoLiveMarkup(html);
  assert.match(html, /href="https:\/\/example\.com\/&quot;&gt;&lt;img/);
});

test("a very long url renders as a wrapping link inside the attribute row", () => {
  const long = `https://example.com/${"segment/".repeat(80)}end`;
  const html = renderDetails(objectDetails({ attributes: [urlAttribute({ display: long })] }));

  assert.match(html, /<dd><a class="model-explorer-url" href="https:\/\/example\.com\/segment\//);
  assert.ok(html.includes(`>${long}</a>`), "the full url is displayed, not truncated");
});

test("an unset url attribute shows Not set rather than an empty link", () => {
  const html = renderDetails(objectDetails({ attributes: [urlAttribute({ value: null, display: null })] }));

  assert.match(html, /Not set/);
  assert.doesNotMatch(html, /<a class="model-explorer-url"/);
});

test("relationship details render url attributes as links too", () => {
  const html = renderDetails(relationshipWith([urlAttribute(), { key: "note", label: "Note", dataType: "text", display: LINK }]));

  assert.equal((html.match(/<a class="model-explorer-url"/g) || []).length, 1);
  assert.match(html, /href="https:\/\/example\.com\/docs\?a=1&amp;b=2#top"/);
});

test("relationship attributes listed on an object's connections link consistently", () => {
  const details = objectDetails();
  details.relationships[0].items[0].attributes = [urlAttribute({ label: "Spec", display: "https://example.com/spec" })];
  const html = renderDetails(details);

  assert.match(html, /Spec: <a class="model-explorer-url" href="https:\/\/example\.com\/spec"/);

  details.relationships[0].items[0].attributes = [urlAttribute({ label: "Spec", display: "javascript:alert(1)" })];
  const unsafe = renderDetails(details);

  assert.match(unsafe, /Spec: javascript:alert\(1\)/);
  assert.doesNotMatch(unsafe, /<a class="model-explorer-url"/);
});
