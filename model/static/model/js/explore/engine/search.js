/**
 * Object search over the dataset: the JS counterpart of
 * ``model.services.model_graph.search.search_objects``.
 *
 * Case-insensitive partial match over names and populated attribute values,
 * ranked name-exact, name-prefix, name-contains, attribute-exact,
 * attribute-contains. Names are folded on the server (``foldKey``) so only the
 * needle and attribute text are folded here.
 */

import { casefold, codePoints, compareStrings, isPopulated, pyStr } from "./text.js";

export const DEFAULT_RESULT_LIMIT = 25;
const SNIPPET_LENGTH = 80;

const [NAME_EXACT, NAME_PREFIX, NAME_CONTAINS, ATTRIBUTE_EXACT, ATTRIBUTE_CONTAINS] = [0, 1, 2, 3, 4];

/** ``[label, text, folded]`` triples; the first is always the name. */
function searchableFields(object, objectType) {
  const fields = [["Name", object.name, object.foldKey]];
  for (const spec of objectType.attributes) {
    const value = object.attributes[spec.key];
    if (spec.dataType !== "boolean" && isPopulated(value)) {
      const text = pyStr(value);
      fields.push([spec.name, text, casefold(text)]);
    }
  }
  return fields;
}

function snippet(text) {
  const characters = codePoints(text);
  return characters.length <= SNIPPET_LENGTH ? text : `${characters.slice(0, SNIPPET_LENGTH - 1).join("")}…`;
}

function bestMatch(needle, fields) {
  let best = null;
  fields.forEach(([label, text, folded], index) => {
    if (!folded.includes(needle)) return;
    let tier;
    if (index === 0) tier = folded === needle ? NAME_EXACT : folded.startsWith(needle) ? NAME_PREFIX : NAME_CONTAINS;
    else tier = folded === needle ? ATTRIBUTE_EXACT : ATTRIBUTE_CONTAINS;
    if (best === null || tier < best[0]) best = [tier, label, text];
  });
  return best;
}

const indexes = new WeakMap();

/** The per-object searchable fields, built once per dataset. */
function fieldsFor(dataset) {
  let index = indexes.get(dataset);
  if (!index) {
    index = new Map();
    for (const object of dataset.objects.values()) {
      index.set(object.id, searchableFields(object, dataset.objectTypes.get(object.typeId)));
    }
    indexes.set(dataset, index);
  }
  return index;
}

function subtitle(fields) {
  const [first] = fields.slice(1);
  return first ? `${first[0]}: ${snippet(first[1])}` : null;
}

export function searchObjects(dataset, q, { projection = null, limit = DEFAULT_RESULT_LIMIT } = {}) {
  const normalised = String(q ?? "").split(/\s+/).filter(Boolean).join(" ");
  const needle = casefold(normalised);
  if (!needle) return { query: "", total: 0, limit, truncated: false, results: [] };

  const index = fieldsFor(dataset);
  const ranked = [];
  for (const object of dataset.objects.values()) {
    const fields = index.get(object.id);
    const match = bestMatch(needle, fields);
    if (match !== null) ranked.push({ tier: match[0], object, fields, match });
  }

  ranked.sort(
    (a, b) =>
      a.tier - b.tier || compareStrings(a.object.foldKey, b.object.foldKey) || compareStrings(a.object.id, b.object.id),
  );

  const results = ranked.slice(0, limit).map(({ object, fields, match }) => {
    const objectType = dataset.objectTypes.get(object.typeId);
    return {
      id: object.id,
      name: object.name,
      typeId: objectType.id,
      typeName: objectType.name,
      isProposed: false,
      inView: projection ? projection.containsObject(object.id) : null,
      connections: dataset.degree(object.id),
      subtitle: subtitle(fields),
      match: match[0] >= ATTRIBUTE_EXACT ? { field: match[1], snippet: snippet(match[2]) } : null,
    };
  });

  return { query: normalised, total: ranked.length, limit, truncated: ranked.length > results.length, results };
}
