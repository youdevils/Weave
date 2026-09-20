/**
 * Sanitising an Explorer state into a query: the JS counterpart of
 * ``ExplorerQuery.from_state`` (model/services/model_graph/query.py).
 *
 * Stale or unknown ids and invalid filters are dropped and reported rather than
 * trusted, exactly as the server does. The two implementations are kept in step
 * by the shared golden fixtures (publication/jstests/fixtures/parity.json).
 */

import { casefold, isPopulated, normaliseId, pyStr, toFloat } from "./text.js";

export const DEFAULT_LIMIT = 300;
export const MIN_LIMIT = 1;
export const MAX_LIMIT = 1000;

export const OP_IN = "in";
export const OP_CONTAINS = "contains";
export const OP_RANGE = "range";

/** The operator each attribute data type supports. */
export const OPERATOR_BY_DATA_TYPE = Object.freeze({
  choice: OP_IN,
  boolean: OP_IN,
  text: OP_CONTAINS,
  number: OP_RANGE,
  date: OP_RANGE,
  datetime: OP_RANGE,
});

export class QueryError extends Error {}

const sortedUnique = (values) => [...new Set(values)].sort();

function knownIds(rawIds, known, kind, dropped) {
  const kept = [];
  for (const raw of rawIds) {
    const id = normaliseId(raw);
    if (id === null || !known.has(id)) dropped.push({ kind, id: pyStr(raw), reason: "unknown" });
    else if (!kept.includes(id)) kept.push(id);
  }
  return kept;
}

function parseLimit(raw) {
  let value = null;
  if (typeof raw === "number" && Number.isFinite(raw)) value = Math.trunc(raw);
  else if (typeof raw === "string" && /^\s*[+-]?\d+\s*$/.test(raw)) value = Number.parseInt(raw, 10);
  return value === null ? DEFAULT_LIMIT : Math.max(MIN_LIMIT, Math.min(MAX_LIMIT, value));
}

function cleanValue(op, dataType, raw) {
  if (op === OP_IN) {
    const list = typeof raw === "string" ? [raw] : raw;
    if (!Array.isArray(list)) return null;
    const values = [...new Set(list.map((v) => pyStr(v).trim()).filter((v) => v !== ""))];
    return values.length > 0 ? values : null;
  }

  if (op === OP_CONTAINS) {
    const text = typeof raw === "string" ? raw.trim() : "";
    return text || null;
  }

  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const bounds = [];
  for (const bound of [raw.min, raw.max]) {
    if (bound === null || bound === undefined || bound === "") {
      bounds.push(null);
    } else if (dataType === "number") {
      const number = toFloat(bound);
      if (number === null) return null;
      bounds.push(number);
    } else {
      bounds.push(pyStr(bound).trim() || null);
    }
  }
  return bounds[0] === null && bounds[1] === null ? null : bounds;
}

function parseFilter(entry, dataset) {
  if (entry === null || typeof entry !== "object" || Array.isArray(entry)) return null;
  const typeId = normaliseId(entry.type_id);
  const objectType = typeId ? dataset.objectTypes.get(typeId) : null;
  if (!objectType) return null;

  const spec = objectType.attributes.find((s) => s.key === entry.key);
  if (!spec) return null;

  const op = OPERATOR_BY_DATA_TYPE[spec.dataType];
  if (op === undefined || (Object.hasOwn(entry, "op") ? entry.op : op) !== op) return null;

  const value = cleanValue(op, spec.dataType, entry.value);
  return value === null ? null : { typeId, key: spec.key, op, value };
}

/** ``{query, dropped}`` for a client state document (``hiddenObjectTypes`` ... ``include``, optional ``limit``). */
export function sanitiseState(state, dataset, { limit } = {}) {
  const source = state !== null && typeof state === "object" && !Array.isArray(state) ? state : {};
  const dropped = [];

  const list = (value) => (Array.isArray(value) ? value : value === null || value === undefined ? [] : [value]);

  const hiddenObjectTypes = knownIds(list(source.hiddenObjectTypes), dataset.objectTypes, "object_type", dropped);
  const hiddenRelationshipTypes = knownIds(
    list(source.hiddenRelationshipTypes),
    dataset.relationshipTypes,
    "relationship_type",
    dropped,
  );
  const include = knownIds(list(source.include), dataset.objects, "object", dropped);

  if (source.attributeFilters !== undefined && source.attributeFilters !== null && !Array.isArray(source.attributeFilters)) {
    throw new QueryError("attributeFilters must be a list.");
  }
  const attributeFilters = [];
  for (const entry of source.attributeFilters ?? []) {
    const parsed = parseFilter(entry, dataset);
    if (parsed === null) {
      dropped.push({ kind: "attribute_filter", id: JSON.stringify(entry), reason: "invalid" });
    } else if (!attributeFilters.some((f) => JSON.stringify(f) === JSON.stringify(parsed))) {
      attributeFilters.push(parsed);
    }
  }

  return {
    query: {
      hiddenObjectTypes: new Set(hiddenObjectTypes),
      hiddenRelationshipTypes: new Set(hiddenRelationshipTypes),
      attributeFilters,
      include: new Set(include),
      limit: parseLimit(source.limit ?? limit),
    },
    dropped,
  };
}

/** The sanitised query as the client should hold it (``ExplorerQuery.to_state``). */
export function toState(query) {
  return {
    hiddenObjectTypes: sortedUnique(query.hiddenObjectTypes),
    hiddenRelationshipTypes: sortedUnique(query.hiddenRelationshipTypes),
    attributeFilters: query.attributeFilters.map((f) => ({
      type_id: f.typeId,
      key: f.key,
      op: f.op,
      value: f.op === OP_RANGE ? { min: f.value[0], max: f.value[1] } : f.value,
    })),
    include: sortedUnique(query.include),
  };
}

/** Whether a stored attribute value satisfies a filter (``AttributeFilter.matches``). */
export function filterMatches(filter, raw) {
  if (!isPopulated(raw)) return false;

  if (filter.op === OP_IN) {
    const wanted = new Set(filter.value.map(casefold));
    return wanted.has(casefold(pyStr(raw)));
  }
  if (filter.op === OP_CONTAINS) {
    return casefold(pyStr(raw)).includes(casefold(filter.value));
  }

  const [minimum, maximum] = filter.value;
  if (typeof minimum === "number" || typeof maximum === "number") {
    const number = toFloat(raw);
    if (number === null) return false;
    return (minimum === null || number >= minimum) && (maximum === null || number <= maximum);
  }
  if (typeof raw !== "string") return false;
  if (minimum !== null && raw < minimum) return false;
  // Truncate so a date-only maximum includes the whole day of a datetime.
  return maximum === null || raw.slice(0, maximum.length) <= maximum;
}
