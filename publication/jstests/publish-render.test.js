import assert from "node:assert/strict";
import test from "node:test";

import {
  EMPTY_TYPE_TITLE,
  renderBanner,
  renderFilterNote,
  renderLocatorResults,
  renderNotices,
  renderOpeningViewSummary,
  renderPreviousNote,
  renderScopeChips,
  renderSummary,
  renderTraversal,
} from "../static/publication/js/publish/publish-render.js";

const HOSTILE = '<img src=x onerror="alert(1)">';

test("scope chips carry the action, kind and key, and escape their label", () => {
  const html = renderScopeChips([{ kind: "root", key: "o1", label: HOSTILE }]);

  assert.match(html, /data-action="remove-scope-chip"/);
  assert.match(html, /data-chip-kind="root"/);
  assert.match(html, /data-chip-key="o1"/);
  assert.doesNotMatch(html, /<img/);
});

test("with no starting point the publication starts from the whole model", () => {
  const html = renderTraversal([], {}, 1, { max: 5 });

  assert.match(html, /No starting point set/);
  assert.match(html, /whole model/);
  assert.doesNotMatch(html, /<select/);
});

test("the depth options say how many steps from the starting objects are included", () => {
  const html = renderTraversal(["o1"], {}, 1, { max: 2 });

  assert.match(html, /Only the starting objects/);
  assert.match(html, /Up to 1 step away/);
  assert.match(html, /Up to 2 steps away/);
  assert.match(html, /Everything connected/);
  assert.doesNotMatch(html, /hop/);
});

test("a type with nothing in the current result is described as such, never as inactive", () => {
  assert.match(EMPTY_TYPE_TITLE, /No matching data in the current result/);
  assert.doesNotMatch(EMPTY_TYPE_TITLE, /inactive/i);
});

test("the object filter note appears only while no filter is applied", () => {
  assert.match(renderFilterNote(0), /No object filters applied/);
  assert.equal(renderFilterNote(1), "");
});

test("starting points list their names and offer every depth including unlimited", () => {
  const html = renderTraversal(["o1"], { o1: { name: HOSTILE, typeName: "Person" } }, 2, { max: 5 });

  assert.doesNotMatch(html, /<img/);
  assert.match(html, /data-action="remove-root" data-id="o1"/);
  for (const hops of [0, 1, 2, 3, 4, 5]) assert.match(html, new RegExp(`<option value="${hops}"`));
  assert.match(html, /<option value="2" selected>/);
  assert.match(html, /<option value="all" >/);
  assert.match(renderTraversal(["o1"], {}, null, { max: 5 }), /<option value="all" selected>/);
});

test("locator results offer a choice, mark existing starting points and escape everything", () => {
  const response = {
    query: "a",
    total: 2,
    truncated: false,
    results: [
      { id: "o1", name: HOSTILE, typeName: "Person", subtitle: "Email: a@b", match: null },
      { id: "o2", name: "Bob", typeName: "Person", subtitle: null, match: { field: "Role", snippet: "Lead" } },
    ],
  };

  const html = renderLocatorResults(response, ["o2"]);

  assert.doesNotMatch(html, /<img/);
  assert.match(html, /data-action="pick-result" data-id="o1" >/);
  assert.match(html, /data-id="o2" disabled/);
  assert.match(html, /starting point/);
  assert.match(html, /Role: Lead/);
  assert.match(html, /2 matches/);
  assert.equal(renderLocatorResults(null, []), "");
  assert.equal(renderLocatorResults({ query: "", total: 0, results: [] }, []), "");
  assert.match(renderLocatorResults({ query: "zz", total: 0, results: [] }, []), /No objects match/);
});

test("the summary says what is being published out of what exists", () => {
  const html = renderSummary({ objects: 1, relationships: 0, totalObjects: 1930, totalRelationships: 1 }, 14);

  assert.match(html, /Publishing 1 of 1,930 objects/);
  assert.match(html, /0 of 1 relationship\b/);
  assert.match(html, /revision 14/);
});

test("notices are listed and escaped; none means nothing is rendered", () => {
  assert.equal(renderNotices([]), "");
  assert.equal(renderNotices(null), "");
  const html = renderNotices([{ message: HOSTILE }, { message: "Scope: an object type was removed." }]);

  assert.doesNotMatch(html, /<img/);
  assert.match(html, /no longer apply/);
  assert.equal((html.match(/<li>/g) ?? []).length, 2);
});

test("banners are alerts unless they report success, and escape their message", () => {
  assert.match(renderBanner("success", "Done"), /role="status"/);
  assert.match(renderBanner("error", "Bad"), /role="alert"/);
  assert.equal(renderBanner("error", ""), "");
  assert.doesNotMatch(renderBanner("error", HOSTILE), /<img/);
});

test("the previous publication is described without suggesting it changes", () => {
  assert.match(renderPreviousNote(null), /first publication/);
  const html = renderPreviousNote({ sequence: 3, title: HOSTILE, revision: 9 });

  assert.match(html, /publication #3/);
  assert.match(html, /revision 9/);
  assert.match(html, /not changed/);
  assert.doesNotMatch(html, /<img/);
});

test("the opening view summary distinguishes the default from a chosen view", () => {
  assert.match(renderOpeningViewSummary(false), /whole publication/);
  assert.match(renderOpeningViewSummary(true, null), /your chosen view/);
  assert.match(renderOpeningViewSummary(true, "an item"), /with an item selected/);
});
