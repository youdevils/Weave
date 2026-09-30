/**
 * Explorer rendering: pure functions returning HTML strings.
 *
 * Everything the user typed (object names, attribute values, search text)
 * comes back through here, so every dynamic value is escaped. Behaviour is
 * attached by explorer-boot.js through ``data-action`` attributes; nothing in
 * here has a side effect, which keeps it testable without a DOM.
 */

import { icon } from "./explorer-icons.js";

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const e = escapeHtml;

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function typePill(name) {
  return `<span class="model-explorer-pill">${e(name)}</span>`;
}

function proposedBadge(isProposed) {
  return isProposed ? '<span class="model-explorer-proposed">Proposed</span>' : "";
}

export function formatCardinality(minimum, maximum) {
  return `${minimum}..${maximum == null ? "*" : maximum}`;
}

// ---------------------------------------------------------------------------
// Legend swatches
//
// Each type's swatch is drawn from its *resolved* appearance (the same values
// the graph uses), as a small inline SVG so every shape keeps a correct border.
// ---------------------------------------------------------------------------

function starPoints(cx, cy, outer, inner) {
  const points = [];
  for (let i = 0; i < 10; i += 1) {
    const radius = i % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    points.push(`${(cx + radius * Math.cos(angle)).toFixed(1)},${(cy + radius * Math.sin(angle)).toFixed(1)}`);
  }
  return points.join(" ");
}

// Geometry in a 20 x 16 box, inset so the stroke is never clipped.
const SHAPE_GEOMETRY = {
  box: (a) => `<rect x="1.5" y="3" width="17" height="10" rx="2" ${a}/>`,
  ellipse: (a) => `<ellipse cx="10" cy="8" rx="8.5" ry="5.5" ${a}/>`,
  circle: (a) => `<circle cx="10" cy="8" r="6.5" ${a}/>`,
  database: (a) => `<path d="M2 4.5c0-1.7 3.6-3 8-3s8 1.3 8 3v7c0 1.7-3.6 3-8 3s-8-1.3-8-3z" ${a}/>`,
  dot: (a) => `<circle cx="10" cy="8" r="4" ${a}/>`,
  square: (a) => `<rect x="4" y="2" width="12" height="12" ${a}/>`,
  diamond: (a) => `<polygon points="10,1 18,8 10,15 2,8" ${a}/>`,
  triangle: (a) => `<polygon points="10,1.5 18,14 2,14" ${a}/>`,
  hexagon: (a) => `<polygon points="5.5,2 14.5,2 19,8 14.5,14 5.5,14 1,8" ${a}/>`,
  star: (a) => `<polygon points="${starPoints(10, 8.4, 7.6, 3.2)}" ${a}/>`,
};

function objectSwatch(data) {
  const paint = `fill="${e(data.background)}" stroke="${e(data.border)}" stroke-width="1.5" stroke-linejoin="round"`;

  // An icon replaces the shape: a circle in the type's colours around the glyph,
  // exactly as the graph draws it.
  if (data.icon && data.image) {
    return `<svg class="model-explorer-swatch" data-shape="icon" data-icon="${e(data.icon)}" viewBox="0 0 20 16" role="img" aria-label="${e(data.icon)} icon"><circle cx="10" cy="8" r="7" ${paint}/><image href="${e(data.image)}" x="4.5" y="2.5" width="11" height="11"/></svg>`;
  }

  const shape = Object.hasOwn(SHAPE_GEOMETRY, data.shape) ? data.shape : "box";
  return `<svg class="model-explorer-swatch" data-shape="${e(shape)}" viewBox="0 0 20 16" role="img" aria-label="${e(shape)}">${SHAPE_GEOMETRY[shape](paint)}</svg>`;
}

function swatch(kind, data) {
  if (!data) return "";
  if (kind === "object") return objectSwatch(data);
  return `<span class="model-explorer-line-swatch" data-line="${e(data.lineStyle)}" style="border-top-color: ${e(data.colour)};"></span>`;
}

// ---------------------------------------------------------------------------
// Search results
// ---------------------------------------------------------------------------

export function renderResults(response) {
  if (!response || response.query === "") return "";

  if (response.total === 0) {
    return `<p class="model-explorer-empty-note">No objects match &ldquo;${e(response.query)}&rdquo;.</p>`;
  }

  const items = response.results
    .map((result) => {
      const detail = result.match
        ? `<span class="model-explorer-result-detail">${e(result.match.field)}: ${e(result.match.snippet)}</span>`
        : result.subtitle
          ? `<span class="model-explorer-result-detail">${e(result.subtitle)}</span>`
          : "";
      const hidden =
        result.inView === false ? '<span class="model-explorer-hidden-tag" title="Not in the current view">not in view</span>' : "";
      return `
        <li>
          <button type="button" class="model-explorer-result" data-action="pick-result" data-id="${e(result.id)}">
            <span class="model-explorer-result-main">
              <span class="model-explorer-result-name">${e(result.name)}</span>
              ${typePill(result.typeName)}${proposedBadge(result.isProposed)}${hidden}
            </span>
            ${detail}
          </button>
        </li>`;
    })
    .join("");

  const footer = response.truncated
    ? `<p class="model-explorer-result-footer">Showing ${response.results.length} of ${response.total}. Refine your search to narrow these down.</p>`
    : `<p class="model-explorer-result-footer">${response.total} ${response.total === 1 ? "match" : "matches"}</p>`;

  return `<ul class="model-explorer-result-list">${items}</ul>${footer}`;
}

// ---------------------------------------------------------------------------
// Details panel
// ---------------------------------------------------------------------------

export function renderEmptyDetails() {
  return `
    <div class="model-explorer-empty-state">
      ${icon("cursor")}
      <p><strong>Nothing selected</strong></p>
      <p>Select an object or relationship in the graph, or search for one, to see its attributes and connections.</p>
    </div>`;
}

export function renderDetailsError(message) {
  return `
    <div class="model-explorer-empty-state" role="status">
      ${icon("slash-circle")}
      <p><strong>Selection cleared</strong></p>
      <p>${e(message)}</p>
    </div>`;
}

/**
 * The href for a URL attribute value, or null when it must not become a link.
 *
 * This is presentation safety, not validation: a model may store any string in
 * a ``url`` attribute, but only absolute http(s) URLs are ever rendered as
 * clickable. Anything else (``javascript:``, ``data:``, relative or malformed
 * values) is shown as plain text. Parsing first means leading whitespace or
 * control characters cannot smuggle a scheme past the check.
 */
export function safeUrlHref(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  // The stored value is the link target, not the parser's normalised form.
  return parsed.protocol === "http:" || parsed.protocol === "https:" ? trimmed : null;
}

function renderUrlValue(display) {
  const href = safeUrlHref(display);
  if (!href) return e(display);
  return `<a class="model-explorer-url" href="${e(href)}" target="_blank" rel="noopener noreferrer nofollow">${e(display)}</a>`;
}

// The one place an attribute's datatype decides how its value is presented.
// Anything not listed is shown as plain escaped text.
const VALUE_RENDERERS = {
  url: renderUrlValue,
};

function renderAttributeValue(attribute) {
  if (!attribute.display) return "Not set";
  const render = Object.hasOwn(VALUE_RENDERERS, attribute.dataType) ? VALUE_RENDERERS[attribute.dataType] : e;
  return render(attribute.display);
}

function renderAttributes(attributes) {
  const rows = attributes
    .map(
      (a) => `
        <div class="model-explorer-attribute">
          <dt>${e(a.label)}</dt>
          <dd${a.display ? "" : ' class="model-explorer-muted"'}>${renderAttributeValue(a)}</dd>
        </div>`,
    )
    .join("");
  return rows ? `<dl class="model-explorer-attributes">${rows}</dl>` : "";
}

function hiddenNotice(kind, inView) {
  if (inView !== false) return "";
  return `
    <div class="model-explorer-notice" role="status">
      This ${kind} is hidden by the current filters.
      <button type="button" class="model-explorer-link" data-action="show-selection">Show in graph</button>
    </div>`;
}

function objectButton(ref) {
  const hidden = ref.inView === false ? ' <span class="model-explorer-hidden-tag">not in view</span>' : "";
  return `<button type="button" class="model-explorer-link" data-action="select-object" data-id="${e(ref.id)}">${e(ref.name)}</button> ${typePill(ref.typeName)}${proposedBadge(ref.isProposed)}${hidden}`;
}

/**
 * A collapsible Details section (Attributes / Connections / History) for hosts that opt in via
 * `sectioned: true`. Owns the heading and the toggle button; `bodyHtml` must be body content only
 * -- never something that already renders its own heading/section wrapper.
 */
function renderDetailSection({ id, title, count, defaultOpen, bodyHtml }) {
  const countBadge = count != null ? ` <span class="model-explorer-count">${count}</span>` : "";
  return `
    <section class="model-explorer-detail-section" data-section="${e(id)}">
      <button type="button" class="model-explorer-detail-section-toggle" data-action="toggle-details-section" aria-expanded="${defaultOpen ? "true" : "false"}">
        <svg class="onyxjar-icon model-explorer-detail-section-chevron" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 6l4 4 4-4"/></svg>
        <h4>${e(title)}${countBadge}</h4>
      </button>
      <div class="model-explorer-detail-section-body${defaultOpen ? "" : " collapsed"}">${bodyHtml}</div>
    </section>`;
}

function renderCopyButton(canCopy) {
  if (!canCopy) return "";
  return `<button type="button" class="btn btn-outline-secondary btn-sm" data-action="copy-details">${icon("copy")} Copy</button>`;
}

function renderEditButton(editHref) {
  if (!editHref) return "";
  return `<a class="btn btn-outline-secondary btn-sm model-explorer-edit-link" href="${e(editHref)}">${icon("edit")} Edit</a>`;
}

function renderObjectDetails(details, canCopy, editHref, sectioned = false) {
  const groups = details.relationships
    .map((group) => {
      const items = group.items
        .map((item) => {
          const arrow = item.direction === "outgoing" ? "&rarr;" : "&larr;";
          const attributes = item.attributes.length
            ? `<span class="model-explorer-muted"> (${item.attributes.map((a) => `${e(a.label)}: ${renderAttributeValue(a)}`).join(", ")})</span>`
            : "";
          const faded = item.inView === false ? " model-explorer-faded" : "";
          return `
            <li class="model-explorer-connection${faded}">
              <span class="model-explorer-arrow" title="${item.direction === "outgoing" ? "Outgoing" : "Incoming"}">${arrow}</span>
              ${objectButton(item.counterpart)}${attributes}
              <button type="button" class="model-explorer-link model-explorer-link-quiet" data-action="select-relationship" data-id="${e(item.relationshipId)}" title="Inspect this relationship">details</button>
            </li>`;
        })
        .join("");
      return `
        <section class="model-explorer-group">
          <h4>${e(group.type.name)} <span class="model-explorer-count">${group.items.length}</span></h4>
          <ul>${items}</ul>
        </section>`;
    })
    .join("");

  const hiddenCount = details.hiddenConnectionIds.length;
  const expand =
    hiddenCount > 0
      ? `<button type="button" class="btn btn-outline-secondary btn-sm" data-action="include-connected" data-ids="${e(details.hiddenConnectionIds.join(","))}">Show ${hiddenCount} hidden ${hiddenCount === 1 ? "connection" : "connections"}</button>`
      : "";
  const connectionsBody = `${expand}${groups || '<p class="model-explorer-muted">This object has no relationships.</p>'}`;

  const attributesHtml = renderAttributes(details.attributes);
  const attributesBlock =
    sectioned && attributesHtml
      ? renderDetailSection({ id: "attributes", title: "Attributes", defaultOpen: true, bodyHtml: attributesHtml })
      : attributesHtml;

  const connectionsBlock = sectioned
    ? renderDetailSection({
        id: "connections",
        title: "Connections",
        count: details.connectionCount,
        defaultOpen: true,
        bodyHtml: connectionsBody,
      })
    : `
    <div class="model-explorer-connections-header">
      <h4>Connections <span class="model-explorer-count">${details.connectionCount}</span></h4>
      ${expand}
    </div>
    ${groups || '<p class="model-explorer-muted">This object has no relationships.</p>'}`;

  const historyBlock = sectioned
    ? details.provenance
      ? renderDetailSection({
          id: "history",
          title: "History",
          count: details.provenance.entries.length,
          defaultOpen: false,
          bodyHtml: renderProvenanceBody(details.provenance, "object"),
        })
      : ""
    : renderProvenance(details.provenance, "object");

  return `
    <header class="model-explorer-details-header">
      <div class="model-explorer-details-heading-row">
        <h3>${e(details.name)}</h3>
        ${renderCopyButton(canCopy)}${renderEditButton(editHref)}
      </div>
      <div>${typePill(details.type.name)}${proposedBadge(details.isProposed)}</div>
    </header>
    ${hiddenNotice("object", details.inView)}
    ${details.description ? `<p class="model-explorer-description">${e(details.description)}</p>` : ""}
    ${attributesBlock}
    ${connectionsBlock}
    ${historyBlock}`;
}

function renderRelationshipDetails(details, editHref, sectioned = false) {
  const cardinality = details.cardinality
    ? `<p class="model-explorer-muted">Allowed: ${e(details.source.typeName)} ${formatCardinality(details.cardinality.subject.minimum, details.cardinality.subject.maximum)} &rarr; ${formatCardinality(details.cardinality.object.minimum, details.cardinality.object.maximum)} ${e(details.target.typeName)}</p>`
    : "";
  const validity =
    details.validFrom || details.validTo
      ? `<p class="model-explorer-muted">Valid ${details.validFrom ? `from ${e(details.validFrom)}` : ""} ${details.validTo ? `to ${e(details.validTo)}` : ""}</p>`
      : "";

  const attributesHtml = renderAttributes(details.attributes);
  const attributesBlock =
    sectioned && attributesHtml
      ? renderDetailSection({ id: "attributes", title: "Attributes", defaultOpen: true, bodyHtml: attributesHtml })
      : attributesHtml;

  const historyBlock = sectioned
    ? details.provenance
      ? renderDetailSection({
          id: "history",
          title: "History",
          count: details.provenance.entries.length,
          defaultOpen: false,
          bodyHtml: renderProvenanceBody(details.provenance, "relationship"),
        })
      : ""
    : renderProvenance(details.provenance, "relationship");

  return `
    <header class="model-explorer-details-header">
      <div class="model-explorer-details-heading-row">
        <h3>${e(details.type.name)}</h3>
        ${renderEditButton(editHref)}
      </div>
      <div>${typePill("Relationship")}${proposedBadge(details.isProposed)}</div>
    </header>
    ${hiddenNotice("relationship", details.inView)}
    <div class="model-explorer-endpoints">
      <div><span class="model-explorer-label">From</span> ${objectButton(details.source)}</div>
      <div><span class="model-explorer-label">To</span> ${objectButton(details.target)}</div>
    </div>
    ${attributesBlock}
    ${validity}
    ${cardinality}
    ${historyBlock}`;
}

// ---------------------------------------------------------------------------
// Provenance ("History")
//
// The server derives the chain from committed proposals and has already turned
// each stored change into a statement about this record ("Renamed", "Set Owner",
// "Deactivated"); this only presents it. Proposals are referred to by revision
// and are not links: there is no proposal navigation from the Explorer.
// ---------------------------------------------------------------------------

/** "12 Mar 2026" in the viewer's time zone, or "" when the value is not a date. */
export function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function renderEvidenceSource(source) {
  const href = safeUrlHref(source);
  if (!href) return `<span class="model-explorer-evidence-source">${e(source)}</span>`;
  return `<a class="model-explorer-url model-explorer-evidence-source" href="${e(href)}" target="_blank" rel="noopener noreferrer nofollow">${e(source)}</a>`;
}

function renderEvidence(evidence) {
  if (!evidence || evidence.length === 0) return "";
  const items = evidence
    .map(
      (item) => `
        <li class="model-explorer-evidence-item">
          ${icon("paperclip")}
          ${renderEvidenceSource(item.source)}
          ${item.locator ? `<span class="model-explorer-muted">${e(item.locator)}</span>` : ""}
          ${item.note ? `<span class="model-explorer-evidence-note">${e(item.note)}</span>` : ""}
        </li>`,
    )
    .join("");
  return `<ul class="model-explorer-evidence">${items}</ul>`;
}

function renderChangeValues(change) {
  const hasBefore = change.before != null;
  const hasAfter = change.after != null;
  let values = "";

  if (hasBefore && hasAfter) values = `${e(change.before)} &rarr; ${e(change.after)}`;
  else if (hasAfter) values = e(change.after);
  else if (hasBefore) values = `${e(change.before)} &rarr; not set`;

  if (values && change.currentNames) values += " (current names)";
  return values ? ` <span class="model-explorer-muted">${values}</span>` : "";
}

function renderInitialValues(initial) {
  if (!initial || initial.length === 0) return "";
  const parts = initial.map((item) => `${e(item.label)}: ${e(item.value)}`).join(", ");
  return `<div class="model-explorer-muted">${parts}</div>`;
}

function renderProvenanceChange(change) {
  return `
    <li class="model-explorer-provenance-change" data-kind="${e(change.kind)}">
      <span class="model-explorer-provenance-summary">${e(change.summary)}</span>${renderChangeValues(change)}
      ${renderInitialValues(change.initial)}
      ${renderEvidence(change.evidence)}
    </li>`;
}

function renderProvenanceEntry(entry) {
  const revision = entry.revision?.after != null ? `Revision ${e(entry.revision.after)}` : "Earlier revision";
  const title = entry.title ? ` <span class="model-explorer-muted">${e(entry.title)}</span>` : "";
  const ai = entry.source === "ai" ? ' <span class="model-explorer-pill">AI</span>' : "";

  const submitted = formatDate(entry.submittedAt);
  const committed = formatDate(entry.committedAt);
  const dates = [
    submitted ? `Submitted ${e(submitted)}` : "",
    committed ? `Validated &amp; committed ${e(committed)}` : "",
  ]
    .filter(Boolean)
    .join(" &middot; ");

  return `
    <li class="model-explorer-provenance-entry">
      <div class="model-explorer-provenance-head"><strong>${revision}</strong>${title}</div>
      <div class="model-explorer-muted">Proposed by ${e(entry.proposer)}${ai}${dates ? ` &middot; ${dates}` : ""}</div>
      ${entry.changeNote ? `<p class="model-explorer-provenance-note">${e(entry.changeNote)}</p>` : ""}
      <ul class="model-explorer-provenance-changes">${entry.changes.map(renderProvenanceChange).join("")}</ul>
    </li>`;
}

/** The record's history body -- no heading, no wrapping `<section>`; see `renderProvenance`. */
export function renderProvenanceBody(provenance, kind = "object") {
  if (provenance.entries.length === 0) {
    return `<p class="model-explorer-muted">No approved proposals have changed this ${e(kind)}.</p>`;
  }

  const older = provenance.truncated
    ? '<p class="model-explorer-muted">Older history is not shown.</p>'
    : "";

  return `${older}<ol class="model-explorer-provenance-list">${provenance.entries.map(renderProvenanceEntry).join("")}</ol>`;
}

/**
 * The record's history, oldest first, in its own `<section>` with its own heading. Renders
 * nothing when the response carried no provenance at all, and an explicit empty state when
 * there is none to show. Used by unsectioned (flat) Details rendering; sectioned rendering
 * instead wraps `renderProvenanceBody` in a `renderDetailSection` so the heading is not doubled.
 */
export function renderProvenance(provenance, kind = "object") {
  if (!provenance) return "";
  return `
    <section class="model-explorer-provenance">
      <h4>History${provenance.entries.length ? ` <span class="model-explorer-count">${provenance.entries.length}</span>` : ""}</h4>
      ${renderProvenanceBody(provenance, kind)}
    </section>`;
}

export function renderDetails(details, { canCopy = false, editHref = null, sectioned = false } = {}) {
  if (!details) return renderEmptyDetails();
  return details.kind === "object"
    ? renderObjectDetails(details, canCopy, editHref, sectioned)
    : renderRelationshipDetails(details, editHref, sectioned);
}

// ---------------------------------------------------------------------------
// State bar
// ---------------------------------------------------------------------------

const plural = (n, one, many) => `${n.toLocaleString("en")} ${n === 1 ? one : many}`;

export function renderCounts(summary) {
  const objects = `${summary.shownObjects.toLocaleString("en")} of ${plural(summary.totalObjects, "object", "objects")}`;
  const relationships = `${summary.shownRelationships.toLocaleString("en")} of ${plural(summary.totalRelationships, "relationship", "relationships")}`;
  return `${objects} &middot; ${relationships}`;
}

export function renderChips(chips) {
  return chips
    .map(
      (chip) => `
        <span class="model-explorer-chip">
          ${e(chip.label)}
          <button type="button" class="model-explorer-chip-remove" data-action="remove-chip" data-chip-kind="${e(chip.kind)}" data-chip-key="${e(chip.key)}" aria-label="Remove: ${e(chip.label)}">&times;</button>
        </span>`,
    )
    .join("");
}

export function renderSelectionChip(label) {
  if (!label) return "";
  return `<span class="model-explorer-chip model-explorer-chip-selection">Selected: ${e(label)}<button type="button" class="model-explorer-chip-remove" data-action="clear-selection" aria-label="Clear selection">&times;</button></span>`;
}

/** Why the graph looks the way it does, when that is not obvious. */
export function renderNotices(summary, { hasNarrowing }) {
  const notices = [];

  if (summary.totalObjects === 0) {
    notices.push("This model has no objects yet.");
  } else if (summary.shownObjects === 0) {
    notices.push(
      hasNarrowing
        ? 'No objects match the current filters. <button type="button" class="model-explorer-link" data-action="clear-filters">Clear filters</button>'
        : "There is nothing to show.",
    );
  }

  if (summary.truncated) {
    notices.push(
      `Showing the ${summary.shownObjects.toLocaleString("en")} best-connected of ${summary.matchingObjects.toLocaleString("en")} matching objects. Narrow the view with filters or search to see the rest.`,
    );
  }

  return notices.map((n) => `<p class="model-explorer-notice" role="status">${n}</p>`).join("");
}

// ---------------------------------------------------------------------------
// Filter panel
// ---------------------------------------------------------------------------

// Which style property(ies) can be attribute-driven, per kind, and where to
// read the source/attribute/resolved-colour for each from.
const OBJECT_COLOUR_PROPERTIES = [
  { sourceKey: "backgroundSource", attributeKey: "backgroundAttribute", styleKey: "background" },
  { sourceKey: "borderSource", attributeKey: "borderAttribute", styleKey: "border" },
];
const RELATIONSHIP_COLOUR_PROPERTIES = [{ sourceKey: "colourSource", attributeKey: "colourAttribute", styleKey: "colour" }];

function isAttributeDriven(kind, type) {
  const properties = kind === "object" ? OBJECT_COLOUR_PROPERTIES : RELATIONSHIP_COLOUR_PROPERTIES;
  return Boolean(type.swatch) && properties.some((p) => type.swatch[p.sourceKey] === "attribute" && type.swatch[p.attributeKey]);
}

/**
 * Groups of a type's currently-rendered items (nodes or edges) by their
 * *resolved* colour tuple -- never a second colour resolution, just reading
 * back what the graph already compiled, so the legend cannot disagree with
 * it. Each group's label lists every distinct value (per attribute-driven
 * property) that produced that colour, so two values sharing one configured
 * colour are not misattributed to just one of them.
 */
export function attributeLegendGroups(kind, type, items) {
  const properties = kind === "object" ? OBJECT_COLOUR_PROPERTIES : RELATIONSHIP_COLOUR_PROPERTIES;
  const active = properties.filter((p) => type.swatch && type.swatch[p.sourceKey] === "attribute" && type.swatch[p.attributeKey]);
  if (active.length === 0) return [];

  const attributeKeys = [...new Set(active.map((p) => type.swatch[p.attributeKey]))];
  const groups = new Map();

  for (const item of items) {
    const style = item.style || {};
    const tupleKey = active.map((p) => style[p.styleKey] ?? "").join("\u0000");
    let group = groups.get(tupleKey);
    if (!group) {
      group = { style, valuesByAttribute: new Map(attributeKeys.map((key) => [key, new Set()])) };
      groups.set(tupleKey, group);
    }
    for (const key of attributeKeys) {
      const raw = item.data && item.data.attributes ? item.data.attributes[key] : undefined;
      if (raw !== undefined) group.valuesByAttribute.get(key).add(String(raw));
    }
  }

  return [...groups.values()].map((group) => ({
    style: group.style,
    label: attributeKeys
      .map((key) => {
        const values = [...group.valuesByAttribute.get(key)].sort();
        return values.length > 0 ? values.join(", ") : "No value";
      })
      .join(" · "),
  }));
}

function attributeLegendRow(kind, type, group) {
  // Colour comes from the resolved group; shape stays the type's own, so only
  // the property that actually varies (colour) differs between rows. An icon
  // is skipped here: its glyph is pre-rendered in the *type's* fixed border,
  // so it cannot reflect a resolved-per-group border without a second render.
  const data =
    kind === "object"
      ? { shape: type.swatch && type.swatch.shape, background: group.style.background, border: group.style.border }
      : { colour: group.style.colour, lineStyle: group.style.lineStyle || (type.swatch && type.swatch.lineStyle) || "solid" };
  return `
    <div class="model-explorer-legend-subrow">
      ${swatch(kind, data)}
      <span class="model-explorer-legend-subrow-label">${e(group.label)}</span>
    </div>`;
}

/** A neutral placeholder swatch for a type whose colour varies by attribute -- never one implied colour. */
function variesSwatch(kind) {
  return `<span class="model-explorer-swatch-varies" data-kind="${kind}" role="img" aria-label="Colour varies by attribute"></span>`;
}

function renderTypeRows(list, hiddenList, action, emptyLabel, items) {
  if (list.length === 0) return `<p class="model-explorer-muted">${emptyLabel}</p>`;
  const kind = action === "toggle-object-type" ? "object" : "relationship";
  return list
    .map((type) => {
      const checked = !hiddenList.includes(type.id);
      const driven = isAttributeDriven(kind, type);
      const typeItems =
        kind === "object"
          ? (items || []).filter((n) => n.data.object_type_id === type.id)
          : (items || []).filter((edge) => edge.data.relationship_type_id === type.id);
      const groups = driven ? attributeLegendGroups(kind, type, typeItems) : [];
      const subrows = groups.map((group) => attributeLegendRow(kind, type, group)).join("");
      return `
        <label class="model-explorer-check">
          <input type="checkbox" data-action="${action}" data-id="${e(type.id)}" ${checked ? "checked" : ""}>
          ${driven ? variesSwatch(kind) : swatch(kind, type.swatch)}
          <span class="model-explorer-check-name">${e(type.name)}${proposedBadge(type.isProposed)}</span>
          <span class="model-explorer-count">${type.count}</span>
        </label>
        ${subrows ? `<div class="model-explorer-legend-subrows">${subrows}</div>` : ""}`;
    })
    .join("");
}

export function renderObjectTypeRows(objectTypes, hiddenObjectTypes, nodes) {
  return renderTypeRows(objectTypes, hiddenObjectTypes, "toggle-object-type", "No object types.", nodes);
}

export function renderRelationshipTypeRows(relationshipTypes, hiddenRelationshipTypes, edges) {
  return renderTypeRows(relationshipTypes, hiddenRelationshipTypes, "toggle-relationship-type", "No relationship types.", edges);
}

/** Combined legend used by consumers without collapsible sections (e.g. the publish scope panel). */
export function renderTypeFilters(facets, state) {
  return `
    <h4>Object types</h4>
    ${renderObjectTypeRows(facets.objectTypes, state.hiddenObjectTypes)}
    <h4>Relationship types</h4>
    ${renderRelationshipTypeRows(facets.relationshipTypes, state.hiddenRelationshipTypes)}`;
}

/** The attribute-filter builder for the chosen type/attribute (either may be empty). */
export function renderFilterBuilder(facets, draft) {
  const typesWithAttributes = facets.objectTypes.filter((t) => t.attributes.length > 0);
  if (typesWithAttributes.length === 0) {
    return '<p class="model-explorer-muted">No filterable attributes yet.</p>';
  }

  const type = typesWithAttributes.find((t) => t.id === draft.typeId) ?? typesWithAttributes[0];
  const attribute = type.attributes.find((a) => a.key === draft.key) ?? type.attributes[0];

  const typeOptions = typesWithAttributes
    .map((t) => `<option value="${e(t.id)}" ${t.id === type.id ? "selected" : ""}>${e(t.name)}</option>`)
    .join("");
  const attributeOptions = type.attributes
    .map((a) => `<option value="${e(a.key)}" ${a.key === attribute.key ? "selected" : ""}>${e(a.name)}</option>`)
    .join("");

  return `
    <div class="model-explorer-builder" data-type-id="${e(type.id)}" data-key="${e(attribute.key)}" data-op="${e(attribute.op)}">
      <select class="form-select form-select-sm" data-action="builder-type" aria-label="Object type">${typeOptions}</select>
      <select class="form-select form-select-sm" data-action="builder-attribute" aria-label="Attribute">${attributeOptions}</select>
      ${renderBuilderValue(attribute)}
      <button type="button" class="btn btn-outline-secondary btn-sm" data-action="add-filter">Add filter</button>
    </div>`;
}

function renderBuilderValue(attribute) {
  if (attribute.op === "in") {
    const options = attribute.values
      .map(
        (v) => `
          <label class="model-explorer-check">
            <input type="checkbox" data-builder-value="${e(v.value)}">
            <span class="model-explorer-check-name">${e(v.label ?? v.value)}</span>
            <span class="model-explorer-count">${v.count}</span>
          </label>`,
      )
      .join("");
    return `<div class="model-explorer-builder-values">${options}</div>`;
  }
  if (attribute.op === "contains") {
    return '<input type="text" class="form-control form-control-sm" data-builder-text placeholder="Contains&hellip;" aria-label="Text to match">';
  }
  const inputType = attribute.dataType === "number" ? "number" : attribute.dataType === "datetime" ? "datetime-local" : "date";
  return `
    <div class="model-explorer-builder-range">
      <input type="${inputType}" class="form-control form-control-sm" data-builder-min aria-label="From">
      <input type="${inputType}" class="form-control form-control-sm" data-builder-max aria-label="To">
    </div>`;
}
