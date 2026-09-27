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
      { group: "Identity", value: "identity.id", label: "OnyxJar Relationship ID" },
      { group: "Endpoints", value: "endpoint.subject", label: "Source object" },
      { group: "Endpoints", value: "endpoint.object", label: "Target object" },
      { group: "Built-in fields", value: "field.is_active", label: "Active" },
      ...attributes,
    ];
  }

  return [
    { group: "Identity", value: "identity.id", label: "OnyxJar Object ID" },
    { group: "Built-in fields", value: "field.name", label: "Name" },
    { group: "Built-in fields", value: "field.description", label: "Description" },
    { group: "Built-in fields", value: "field.is_active", label: "Active" },
    ...attributes,
  ];
}

/** Ways an endpoint can be identified: by OnyxJar Object ID, or by an object type's attribute. */
export function endpointResolvers(objectTypes) {
  const resolvers = [{ value: "id", label: "OnyxJar Object ID" }];

  for (const type of objectTypes ?? []) {
    for (const attribute of type.attributes ?? []) {
      if (attribute.identity_eligible) {
        resolvers.push({
          value: `attribute:${type.type_id}:${attribute.key}`,
          label: `${type.name}: ${attribute.name}`,
        });
      }
    }
  }

  return resolvers;
}

const HEADER_SYNONYMS = {
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
  target: "endpoint.object",
  to: "endpoint.object",
  object: "endpoint.object",
  targetobject: "endpoint.object",
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
export const emptyRow = () => ({ field: "", match: false, resolver: "id" });

/**
 * The mapping document from the page's per-column rows (`rows[columnIndex]`).
 * Columns with no field are unmapped and omitted.
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
      const resolver = row.resolver || "id";

      if (resolver === "id") {
        entry.by = "id";
      } else {
        const [, objectTypeId, ...key] = resolver.split(":");
        entry.by = `attribute:${key.join(":")}`;
        entry.object_type_id = objectTypeId;
      }
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
