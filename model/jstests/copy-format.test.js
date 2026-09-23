import assert from "node:assert/strict";
import test from "node:test";

import { buildObjectCopyHtml, buildObjectCopyText } from "../static/model/js/explore/copy-format.js";

function fakeDataset(objects, objectTypes) {
  return {
    objects: new Map(Object.entries(objects)),
    objectTypes: new Map(Object.entries(objectTypes)),
  };
}

const teamType = { attributes: [{ key: "area", name: "Business area", dataType: "text" }, { key: "location", name: "Location", dataType: "text" }] };
const processType = { attributes: [{ key: "owner", name: "Owner", dataType: "text" }, { key: "status", name: "Status", dataType: "text" }] };
const appType = { attributes: [{ key: "owner", name: "Owner", dataType: "text" }] };
const capabilityType = { attributes: [{ key: "owner", name: "Owner", dataType: "text" }] };

const dataset = fakeDataset(
  {
    claims: { typeId: "process", attributes: { owner: "Claims Operations", status: "Active" } },
    portal: { typeId: "application", attributes: { owner: "Digital" } },
    capability: { typeId: "capability", attributes: { owner: "Claims Operations" } },
    empty: { typeId: "application", attributes: {} },
  },
  { process: processType, application: appType, capability: capabilityType, team: teamType },
);

const details = {
  name: "Customer Service Team",
  type: { name: "Team" },
  attributes: [
    { label: "Business area", display: "Operations" },
    { label: "Location", display: "Auckland" },
    { label: "Owner", display: "Jane Smith" },
  ],
  relationships: [
    {
      type: { name: "Uses" },
      items: [
        { counterpart: { id: "claims", name: "Claims Assessment", typeName: "Process" } },
        { counterpart: { id: "portal", name: "Customer Portal", typeName: "Application" } },
      ],
    },
    {
      type: { name: "Supports" },
      items: [{ counterpart: { id: "capability", name: "Claims Capability", typeName: "Capability" } }],
    },
  ],
};

const EXPECTED_TEXT = `# Customer Service Team

Type: Team

## Attributes
- Business area: Operations
- Location: Auckland
- Owner: Jane Smith

## Connected Objects

### Uses

#### Claims Assessment
Type: Process
- Owner: Claims Operations
- Status: Active

#### Customer Portal
Type: Application
- Owner: Digital

### Supports

#### Claims Capability
Type: Capability
- Owner: Claims Operations
`;

test("matches the documented plain-text layout exactly", () => {
  assert.equal(buildObjectCopyText(details, dataset), EXPECTED_TEXT);
});

test("an object with no populated attributes has no Attributes section", () => {
  const text = buildObjectCopyText({ ...details, attributes: [] }, dataset);

  assert.doesNotMatch(text, /## Attributes/);
});

test("an object with no relationships has no Connected Objects section", () => {
  const text = buildObjectCopyText({ ...details, relationships: [] }, dataset);

  assert.doesNotMatch(text, /## Connected Objects/);
});

test("a connected object with no populated attributes gets a heading and type but no bullets", () => {
  const text = buildObjectCopyText(
    { ...details, relationships: [{ type: { name: "Uses" }, items: [{ counterpart: { id: "empty", name: "Empty App", typeName: "Application" } }] }] },
    dataset,
  );

  assert.equal(text, "# Customer Service Team\n\nType: Team\n\n## Attributes\n- Business area: Operations\n- Location: Auckland\n- Owner: Jane Smith\n\n## Connected Objects\n\n### Uses\n\n#### Empty App\nType: Application\n");
});

test("does not include internal ids or relationship-attribute noise", () => {
  const text = buildObjectCopyText(details, dataset);

  assert.doesNotMatch(text, /claims|portal|capability/); // the dataset keys are ids, never printed
});

test("the HTML version preserves headings and lists and escapes hostile values", () => {
  const hostile = {
    name: "<script>alert(1)</script>",
    type: { name: "Team" },
    attributes: [{ label: "Note", display: "<b>&</b>" }],
    relationships: [],
  };

  const html = buildObjectCopyHtml(hostile, dataset);

  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /<h1>/);
  assert.match(html, /<h2>Attributes<\/h2>/);
  assert.match(html, /<ul><li><strong>Note:<\/strong> &lt;b&gt;&amp;&lt;\/b&gt;<\/li><\/ul>/);
});

test("the HTML version renders one h3 per relationship group and one h4 per connected object", () => {
  const html = buildObjectCopyHtml(details, dataset);

  assert.equal((html.match(/<h3>/g) || []).length, 2);
  assert.equal((html.match(/<h4>/g) || []).length, 3);
  assert.match(html, /<h3>Uses<\/h3>/);
  assert.match(html, /<h3>Supports<\/h3>/);
});
