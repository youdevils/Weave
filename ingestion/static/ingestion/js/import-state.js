/**
 * Pure logic of the Data Import page: which fields a target offers, the
 * suggested column mapping, and the mapping document sent to the server.
 *
 * Nothing here decides identity or validity. The server re-validates every
 * mapping against the canonical ontology; this module only helps a person build
 * one and keeps the document in the exact shape the server expects:
 *
 *   {target: {kind, type_id},
 *    columns: [{column, field, match?, by?, object_type_id?}]}
 */

export const KINDS = { OBJECT: "object", RELATIONSHIP: "relationship" };

export function normaliseHeader(text) {
  return String(text ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

/** The fields a source column may be mapped to for `target`, grouped for display. */
export function fieldOptions(kind, target) {
  const attributes = (target?.attributes ?? []).map((attribute) => ({
    group: "Attributes",
    value: `attribute.${attribute.key}`,
    label: attribute.name,
    dataType: attribute.data_type,
    identityEligible: Boolean(attribute.identity_eligible),
  }));

  if (kind === KINDS.RELATIONSHIP) {
    return [
      { group: "Advanced", value: "identity.id", label: "Database ID (advanced)" },
      { group: "Endpoints", value: "endpoint.subject", label: "Source object" },
      { group: "Endpoints", value: "endpoint.object", label: "Target object" },
      { group: "Built-in fields", value: "field.is_active", label: "Active" },
      ...attributes,
    ];
  }

  return [
    { group: "Identity", value: "identity.key", label: "OnyxJar Key" },
    { group: "Advanced", value: "identity.id", label: "Database ID (advanced)" },
    { group: "Built-in fields", value: "field.name", label: "Name" },
    { group: "Built-in fields", value: "field.description", label: "Description" },
    { group: "Built-in fields", value: "field.is_active", label: "Active" },
    ...attributes,
  ];
}

/**
 * Ways one endpoint column can be identified, scoped to `candidateTypeIds`
 * (the object types the relationship's own rules allow on that side --
 * TargetSpec.subject_type_ids / object_type_ids from the server). The
 * normal choice is the object's OnyxJar Key, searched across every allowed
 * type on that side; when more than one type is allowed, pinning the
 * column to one specific type is also offered (unambiguous by
 * construction, and the simpler/faster path when it applies). An
 * explicitly chosen attribute, or the Database ID, remain advanced/
 * optional alternatives.
 */
export function endpointResolvers(objectTypes, candidateTypeIds) {
  const candidates = (objectTypes ?? []).filter(
    (type) => !candidateTypeIds || candidateTypeIds.includes(type.type_id),
  );

  const resolvers = [];

  if (candidates.length) {
    resolvers.push({ value: "key", label: "OnyxJar Key" });
  }

  if (candidates.length > 1) {
    for (const type of candidates) {
      resolvers.push({ value: `key:${type.type_id}`, label: `${type.name}: Key only` });
    }
  }

  for (const type of candidates) {
    for (const attribute of type.attributes ?? []) {
      if (attribute.identity_eligible) {
        resolvers.push({
          value: `attribute:${type.type_id}:${attribute.key}`,
          label: `${type.name}: ${attribute.name}`,
        });
      }
    }
  }

  resolvers.push({ value: "id", label: "Database ID (advanced)" });

  return resolvers;
}

/**
 * The resolver to pre-select once an endpoint column's field is chosen:
 * pinned to the one type the relationship allows on `side`
 * ("subject"/"object") when there's exactly one, otherwise left for the
 * person to choose explicitly -- never a silent guess when more than one
 * type is allowed, since the key could ambiguously match more than one
 * of them (surfaced as a blocking error at preview time, not here).
 */
export function defaultResolver(target, side) {
  const candidateIds = side === "subject" ? target?.subject_type_ids : target?.object_type_ids;

  if (candidateIds?.length === 1) {
    return `key:${candidateIds[0]}`;
  }

  return "";
}

const HEADER_SYNONYMS = {
  onyxjarkey: "identity.key",
  key: "identity.key",
  objectkey: "identity.key",
  onyxjarid: "identity.id",
  objectid: "identity.id",
  onyxjarobjectid: "identity.id",
  relationshipid: "identity.id",
  onyxjarrelationshipid: "identity.id",
  isactive: "field.is_active",
  active: "field.is_active",
  source: "endpoint.subject",
  from: "endpoint.subject",
  subject: "endpoint.subject",
  sourceobject: "endpoint.subject",
  sourceobjectkey: "endpoint.subject",
  sourcekey: "endpoint.subject",
  target: "endpoint.object",
  to: "endpoint.object",
  object: "endpoint.object",
  targetobject: "endpoint.object",
  targetobjectkey: "endpoint.object",
  targetkey: "endpoint.object",
};

/**
 * A starting point only: for each column, the field whose label or key matches
 * its header, each field used at most once (leftmost column wins). Never turns
 * on identity matching; that is always the person's explicit choice.
 * Returns {columnIndex: fieldValue}.
 */
export function suggestMapping(headers, options) {
  const byName = new Map();

  for (const option of options) {
    byName.set(normaliseHeader(option.label), option.value);

    if (option.value.startsWith("attribute.")) {
      byName.set(normaliseHeader(option.value.slice("attribute.".length)), option.value);
    }
  }

  const available = new Set(options.map((option) => option.value));
  const used = new Set();
  const suggestion = {};

  headers.forEach((header, index) => {
    const name = normaliseHeader(header);
    const field = byName.get(name) ?? (available.has(HEADER_SYNONYMS[name]) ? HEADER_SYNONYMS[name] : undefined);

    if (field && !used.has(field)) {
      used.add(field);
      suggestion[index] = field;
    }
  });

  return suggestion;
}

/** A blank row of mapping controls for one source column. */
export const emptyRow = () => ({ field: "", match: false, resolver: "" });

/**
 * The mapping document from the page's per-column rows (`rows[columnIndex]`).
 * Columns with no field are unmapped and omitted. An endpoint column with
 * no resolver chosen is sent with no `by` at all -- the server's own
 * mapping validation rejects that ("choose how the endpoint is
 * identified"), which is the forcing function for a person to pick one
 * when defaultResolver() left it unset (more than one type allowed).
 */
export function buildMapping({ kind, typeId, rows }) {
  const columns = [];

  rows.forEach((row, column) => {
    if (!row?.field) return;

    const entry = { column, field: row.field };

    if (row.match && row.field.startsWith("attribute.") && kind === KINDS.OBJECT) {
      entry.match = true;
    }

    if (row.field === "endpoint.subject" || row.field === "endpoint.object") {
      const resolver = row.resolver || "";

      if (resolver === "id") {
        entry.by = "id";
      } else if (resolver === "key") {
        entry.by = "key";
      } else if (resolver.startsWith("key:")) {
        entry.by = "key";
        entry.object_type_id = resolver.slice("key:".length);
      } else if (resolver.startsWith("attribute:")) {
        const [, objectTypeId, ...key] = resolver.split(":");
        entry.by = `attribute:${key.join(":")}`;
        entry.object_type_id = objectTypeId;
      }
      // else: no resolver chosen yet -- entry.by stays unset, see docstring.
    }

    columns.push(entry);
  });

  return { target: { kind, type_id: typeId }, columns };
}

/** The mapping is worth sending to the server for a preview. */
export function canPreview({ source, target, mapping }) {
  return Boolean(source && target && mapping?.columns?.length);
}

/** Creating is only offered for a fresh, unblocked preview. */
export function canCreate({ preview, previewIsFresh }) {
  return Boolean(preview && previewIsFresh && !preview.blocked);
}

/** The steps of the guided workflow, in order. */
export const WIZARD_STEPS = ["upload", "target", "map", "preview", "create"];

/**
 * Which workflow steps can be opened right now. A step is available once what it
 * depends on has been provided; presentation only, it never gates the server.
 * Returns {upload, target, map, preview, create} booleans.
 */
export function availableSteps({ source, target, mapping, preview, previewIsFresh }) {
  const hasSource = Boolean(source);
  const hasTarget = hasSource && Boolean(target);

  return {
    upload: true,
    target: hasSource,
    map: hasTarget,
    preview: canPreview({ source, target, mapping }),
    create: canCreate({ preview, previewIsFresh }),
  };
}

/** "92 created, 31 updated, 24 unchanged" for the summary line. */
export function describeSummary(summary) {
  const noun = summary.kind === KINDS.RELATIONSHIP ? "relationships" : "objects";

  return `${summary.creates} ${noun} to create, ${summary.updates} to update, ${summary.no_ops} unchanged`;
}
