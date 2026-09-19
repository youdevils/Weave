/**
 * Explorer rendering: pure functions returning HTML strings.
 *
 * Everything the user typed (object names, attribute values, search text)
 * comes back through here, so every dynamic value is escaped. Behaviour is
 * attached by explorer-boot.js through ``data-action`` attributes; nothing in
 * here has a side effect, which keeps it testable without a DOM.
 */

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

function swatch(kind, data) {
  if (!data) return "";
  if (kind === "object") {
    return `<span class="model-explorer-swatch" data-shape="${e(data.shape)}" style="background: ${e(data.background)}; border-color: ${e(data.border)};"></span>`;
  }
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
      <i class="bi bi-cursor"></i>
      <p><strong>Nothing selected</strong></p>
      <p>Select an object or relationship in the graph, or search for one, to see its attributes and connections.</p>
    </div>`;
}

export function renderDetailsError(message) {
  return `
    <div class="model-explorer-empty-state" role="status">
      <i class="bi bi-slash-circle"></i>
      <p><strong>Selection cleared</strong></p>
      <p>${e(message)}</p>
    </div>`;
}

function renderAttributes(attributes) {
  const rows = attributes
    .map(
      (a) => `
        <div class="model-explorer-attribute">
          <dt>${e(a.label)}</dt>
          <dd${a.display ? "" : ' class="model-explorer-muted"'}>${a.display ? e(a.display) : "Not set"}</dd>
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

function renderObjectDetails(details) {
  const groups = details.relationships
    .map((group) => {
      const items = group.items
        .map((item) => {
          const arrow = item.direction === "outgoing" ? "&rarr;" : "&larr;";
          const attributes = item.attributes.length
            ? `<span class="model-explorer-muted"> (${item.attributes.map((a) => `${e(a.label)}: ${e(a.display)}`).join(", ")})</span>`
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

  return `
    <header class="model-explorer-details-header">
      <h3>${e(details.name)}</h3>
      <div>${typePill(details.type.name)}${proposedBadge(details.isProposed)}</div>
    </header>
    ${hiddenNotice("object", details.inView)}
    ${details.description ? `<p class="model-explorer-description">${e(details.description)}</p>` : ""}
    ${renderAttributes(details.attributes)}
    <div class="model-explorer-connections-header">
      <h4>Connections <span class="model-explorer-count">${details.connectionCount}</span></h4>
      ${expand}
    </div>
    ${groups || '<p class="model-explorer-muted">This object has no relationships.</p>'}`;
}

function renderRelationshipDetails(details) {
  const cardinality = details.cardinality
    ? `<p class="model-explorer-muted">Allowed: ${e(details.source.typeName)} ${formatCardinality(details.cardinality.subject.minimum, details.cardinality.subject.maximum)} &rarr; ${formatCardinality(details.cardinality.object.minimum, details.cardinality.object.maximum)} ${e(details.target.typeName)}</p>`
    : "";
  const validity =
    details.validFrom || details.validTo
      ? `<p class="model-explorer-muted">Valid ${details.validFrom ? `from ${e(details.validFrom)}` : ""} ${details.validTo ? `to ${e(details.validTo)}` : ""}</p>`
      : "";
  return `
    <header class="model-explorer-details-header">
      <h3>${e(details.type.name)}</h3>
      <div>${typePill("Relationship")}${proposedBadge(details.isProposed)}</div>
    </header>
    ${hiddenNotice("relationship", details.inView)}
    <div class="model-explorer-endpoints">
      <div><span class="model-explorer-label">From</span> ${objectButton(details.source)}</div>
      <div><span class="model-explorer-label">To</span> ${objectButton(details.target)}</div>
    </div>
    ${renderAttributes(details.attributes)}
    ${validity}
    ${cardinality}`;
}

export function renderDetails(details) {
  if (!details) return renderEmptyDetails();
  return details.kind === "object" ? renderObjectDetails(details) : renderRelationshipDetails(details);
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

export function renderTypeFilters(facets, state) {
  const objectRows = facets.objectTypes
    .map((type) => {
      const checked = !state.hiddenObjectTypes.includes(type.id);
      return `
        <label class="model-explorer-check">
          <input type="checkbox" data-action="toggle-object-type" data-id="${e(type.id)}" ${checked ? "checked" : ""}>
          ${swatch("object", type.swatch)}
          <span class="model-explorer-check-name">${e(type.name)}${proposedBadge(type.isProposed)}</span>
          <span class="model-explorer-count">${type.count}</span>
        </label>`;
    })
    .join("");

  const relationshipRows = facets.relationshipTypes
    .map((type) => {
      const checked = !state.hiddenRelationshipTypes.includes(type.id);
      return `
        <label class="model-explorer-check">
          <input type="checkbox" data-action="toggle-relationship-type" data-id="${e(type.id)}" ${checked ? "checked" : ""}>
          ${swatch("relationship", type.swatch)}
          <span class="model-explorer-check-name">${e(type.name)}${proposedBadge(type.isProposed)}</span>
          <span class="model-explorer-count">${type.count}</span>
        </label>`;
    })
    .join("");

  return `
    <h4>Object types</h4>
    ${objectRows || '<p class="model-explorer-muted">No object types.</p>'}
    <h4>Relationship types</h4>
    ${relationshipRows || '<p class="model-explorer-muted">No relationship types.</p>'}`;
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
