/**
 * Publishing page rendering: pure functions returning HTML strings. Every
 * dynamic value (object names, titles, notices) is escaped; behaviour is
 * attached by publish-boot.js through ``data-action`` attributes.
 */

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const e = escapeHtml;
const number = (n) => Number(n).toLocaleString("en");
const plural = (n, one, many) => `${number(n)} ${n === 1 ? one : many}`;

/** The removable scope chips (same look as the Explorer's filter chips). */
export function renderScopeChips(chips) {
  return chips
    .map(
      (chip) => `
        <span class="model-explorer-chip">
          ${e(chip.label)}
          <button type="button" class="model-explorer-chip-remove" data-action="remove-scope-chip" data-chip-kind="${e(chip.kind)}" data-chip-key="${e(chip.key)}" aria-label="Remove: ${e(chip.label)}">&times;</button>
        </span>`,
    )
    .join("");
}

/** Shown on a type that is selected but has nothing in the current result (it is not an exclusion, and not "inactive"). */
export const EMPTY_TYPE_TITLE = "No matching data in the current result";

/** The Object filters section's note when nothing narrows objects by attribute. */
export function renderFilterNote(filterCount) {
  return filterCount === 0
    ? `<p class="model-explorer-muted publish-hint">No object filters applied. Every object that passes the rest of the scope is included.</p>`
    : "";
}

/** Starting points and how far to follow their connections. */
export function renderTraversal(roots, rootNames, depth, limits) {
  if (roots.length === 0) {
    return `<p class="model-explorer-muted publish-hint">No starting point set: the publication starts from the whole model.</p>`;
  }

  const list = roots
    .map((id) => {
      const named = rootNames?.[id];
      return `<li class="publish-root">
        <span class="publish-root-name">${e(named?.name ?? "Object")}</span>
        ${named ? `<span class="model-explorer-pill">${e(named.typeName)}</span>` : ""}
        <button type="button" class="model-explorer-chip-remove" data-action="remove-root" data-id="${e(id)}" aria-label="Remove starting point ${e(named?.name ?? "")}">&times;</button>
      </li>`;
    })
    .join("");

  const options = [];
  for (let hops = 0; hops <= limits.max; hops += 1) {
    const label = hops === 0 ? "Only the starting objects" : `Up to ${plural(hops, "step", "steps")} away`;
    options.push(`<option value="${hops}" ${depth === hops ? "selected" : ""}>${label}</option>`);
  }
  options.push(`<option value="all" ${depth === null ? "selected" : ""}>Everything connected</option>`);

  return `
    <ul class="publish-roots">${list}</ul>
    <label class="publish-field">
      <span class="publish-label">Include what is connected</span>
      <select class="form-select form-select-sm" data-action="set-depth" aria-label="How many steps from the starting objects to include">${options.join("")}</select>
    </label>`;
}

/** The results of finding an object to use as a starting point. */
export function renderLocatorResults(response, startingIds) {
  if (!response || response.query === "") return "";
  if (response.total === 0) {
    return `<p class="model-explorer-empty-note">No objects match &ldquo;${e(response.query)}&rdquo;.</p>`;
  }

  const items = response.results
    .map((result) => {
      const already = startingIds.includes(result.id);
      const detail = result.match
        ? `<span class="model-explorer-result-detail">${e(result.match.field)}: ${e(result.match.snippet)}</span>`
        : result.subtitle
          ? `<span class="model-explorer-result-detail">${e(result.subtitle)}</span>`
          : "";
      return `
        <li>
          <button type="button" class="model-explorer-result" data-action="pick-result" data-id="${e(result.id)}" ${already ? "disabled" : ""}>
            <span class="model-explorer-result-main">
              <span class="model-explorer-result-name">${e(result.name)}</span>
              <span class="model-explorer-pill">${e(result.typeName)}</span>
              ${already ? '<span class="model-explorer-hidden-tag">starting point</span>' : ""}
            </span>
            ${detail}
          </button>
        </li>`;
    })
    .join("");

  const footer = response.truncated
    ? `Showing ${response.results.length} of ${response.total}. Refine your search to narrow these down.`
    : plural(response.total, "match", "matches");
  return `<p class="model-explorer-muted publish-hint">Choose an object to start from.</p>
    <ul class="model-explorer-result-list">${items}</ul>
    <p class="model-explorer-result-footer">${footer}</p>`;
}

/** "Publishing 412 of 1,930 objects · 655 of 1,900 relationships (revision 14)". */
export function renderSummary(summary, revision) {
  const objects = `${number(summary.objects)} of ${plural(summary.totalObjects, "object", "objects")}`;
  const relationships = `${number(summary.relationships)} of ${plural(summary.totalRelationships, "relationship", "relationships")}`;
  return `Publishing ${objects} &middot; ${relationships} <span class="publish-revision">revision ${e(revision)}</span>`;
}

/** Settings reconciled against the current model (or against the previous publication). */
export function renderNotices(notices) {
  if (!notices || notices.length === 0) return "";
  const items = notices.map((n) => `<li>${e(n.message)}</li>`).join("");
  return `<div class="model-explorer-notice" role="status"><strong>Some saved settings no longer apply and were removed.</strong><ul>${items}</ul></div>`;
}

/** A banner for the outcome of publishing (plain text). ``kind`` is one of success, error, changed. */
export function renderBanner(kind, message) {
  if (!message) return "";
  const role = kind === "success" ? "status" : "alert";
  return `<div class="publish-banner publish-banner-${e(kind)}" role="${role}">${e(message)}</div>`;
}

/** The success banner after a publish: what was created, and where to go next. */
export function renderPublishSuccess(publication, urls) {
  return `
    <div class="publish-banner publish-banner-success" role="status">
      <p>Published revision ${e(publication.revision)} as publication #${e(publication.sequence)}.</p>
      <div class="publish-success-actions">
        <a href="${e(urls.view)}" class="btn btn-sm btn-primary">View this publication</a>
        <a href="${e(urls.index)}" class="btn btn-sm btn-outline-secondary">View Publications</a>
        <a href="${e(urls.download)}" class="btn btn-sm btn-outline-secondary">Download</a>
      </div>
    </div>`;
}

export function renderPreviousNote(previous) {
  if (!previous) return `This is the first publication of this model, so these settings are the defaults.`;
  return `Started from publication #${e(previous.sequence)} (&ldquo;${e(previous.title)}&rdquo;, revision ${e(previous.revision)}). That publication is not changed.`;
}

export function renderOpeningViewSummary(active, selectionLabel) {
  if (!active) return "Readers open on the whole publication.";
  return `Readers open on your chosen view${selectionLabel ? `, with ${e(selectionLabel)} selected` : ""}.`;
}
