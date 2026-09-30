/**
 * The preview Explorer on the publishing page shows only the graph and its state
 * bar. The shared controller (explorer-controller.js) still looks up every element
 * it was written against and never null-guards them, so the ones this page does not
 * show are handed to it as detached nodes: nothing on the page, nothing to leak.
 *
 * Every name in the controller's ELEMENT_IDS must appear in exactly one of the two
 * lists below; publication/jstests/publish-panels.test.js fails if the controller
 * ever asks for something new.
 */

/** Present on the page (publish.html and model/_explorer_main.html). */
export const RETAINED_ELEMENTS = [
  "root",
  "graph",
  "counts",
  "chips",
  "notices",
  "error",
  "controls",
  "controlsToggle",
  "controlsReopen",
];

/** Not shown on the page: element name -> the tag of the detached stand-in. */
const DETACHED_TAGS = {
  search: "input",
  results: "div",
  legend: "aside",
  legendToggle: "button",
  legendReopen: "button",
  objectTypeRows: "div",
  objectTypeToggle: "button",
  relationshipTypeRows: "div",
  relationshipTypeToggle: "button",
  selectAllObjectTypes: "input",
  selectAllRelationshipTypes: "input",
  builder: "div",
  builderMessage: "p",
  sidebar: "aside",
  sidebarToggle: "button",
  sidebarReopen: "button",
  details: "div",
};

export const DETACHED_ELEMENTS = Object.keys(DETACHED_TAGS);

/** ``{name: node}`` for the ``elements`` option of createExplorer. */
export function detachedExplorerElements(createElement) {
  const elements = {};
  for (const [name, tag] of Object.entries(DETACHED_TAGS)) {
    const node = createElement(tag);
    if (name.startsWith("selectAll")) node.type = "checkbox";
    elements[name] = node;
  }
  return elements;
}
