/**
 * HTML for the Data Import page.
 *
 * Everything that reaches these functions from a file, a filename or a server
 * message is untrusted, so every dynamic value goes through `escapeHtml` before
 * it is placed in markup. There are no inline handlers and no dynamic
 * attribute names.
 */

import { describeSummary, endpointResolvers, fieldOptions, KINDS } from "./import-state.js";

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

const e = escapeHtml;

/** A cell value for display: blank is shown as an empty marker, not dropped. */
export function displayValue(value) {
  if (value === null || value === undefined || value === "") return '<span class="import-empty">(empty)</span>';
  if (typeof value === "boolean") return e(value ? "true" : "false");
  return e(value);
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function banner(kind, message) {
  if (!message) return "";
  return `<div class="alert alert-${e(kind)} import-banner-message" role="alert">${e(message)}</div>`;
}

export function uploadSummary({ source, columns, sampleRows, warnings }) {
  const head = columns.map((column) => `<th scope="col">${e(column.header)}</th>`).join("");
  const body = sampleRows
    .map((row) => `<tr>${row.map((cell) => `<td>${e(cell)}</td>`).join("")}</tr>`)
    .join("");

  const notes = (warnings ?? []).map((warning) => `<li>${e(warning)}</li>`).join("");

  return `
    <dl class="import-facts">
      <div><dt>File</dt><dd>${e(source.filename)}</dd></div>
      <div><dt>Format</dt><dd>${e(String(source.format).toUpperCase())}</dd></div>
      <div><dt>Size</dt><dd>${e(formatBytes(source.size_bytes))}</dd></div>
      <div><dt>Data rows</dt><dd>${e(source.row_count)}</dd></div>
      <div><dt>Columns</dt><dd>${e(source.column_count)}</dd></div>
    </dl>
    ${notes ? `<ul class="import-notes">${notes}</ul>` : ""}
    <div class="import-sample" tabindex="0" role="region" aria-label="First rows of the file">
      <table class="table table-sm import-sample-table">
        <thead><tr>${head}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

export function typeOptions(types, selectedId) {
  const options = types
    .map(
      (type) =>
        `<option value="${e(type.type_id)}"${type.type_id === selectedId ? " selected" : ""}>${e(type.name)}</option>`,
    )
    .join("");

  return `<option value="">Choose a type&hellip;</option>${options}`;
}

function fieldSelect(options, current, usedElsewhere) {
  const groups = [];

  for (const option of options) {
    let group = groups.find((entry) => entry.name === option.group);
    if (!group) groups.push((group = { name: option.group, items: [] }));
    group.items.push(option);
  }

  const rendered = groups
    .map((group) => {
      const items = group.items
        .map((option) => {
          const taken = usedElsewhere.has(option.value) && option.value !== current;
          const suffix = option.dataType ? ` (${option.dataType})` : "";
          return `<option value="${e(option.value)}"${option.value === current ? " selected" : ""}${
            taken ? " disabled" : ""
          }>${e(option.label + suffix)}</option>`;
        })
        .join("");
      return `<optgroup label="${e(group.name)}">${items}</optgroup>`;
    })
    .join("");

  return `<option value="">Don&rsquo;t import this column</option>${rendered}`;
}

/** One table row per source column: header, sample values, and the mapping controls. */
export function mappingTable({ kind, target, columns, sampleRows, rows, objectTypes }) {
  const options = fieldOptions(kind, target);
  const subjectResolvers = endpointResolvers(objectTypes, target?.subject_type_ids);
  const objectResolvers = endpointResolvers(objectTypes, target?.object_type_ids);
  const used = new Set(rows.map((row) => row?.field).filter(Boolean));

  const body = columns
    .map((column) => {
      const row = rows[column.index] ?? {};
      const option = options.find((candidate) => candidate.value === row.field);
      const samples = sampleRows
        .slice(0, 2)
        .map((sample) => e(sample[column.index] ?? ""))
        .filter(Boolean)
        .join(" &middot; ");

      let extra = "";

      if (row.field === "endpoint.subject" || row.field === "endpoint.object") {
        const resolvers = row.field === "endpoint.subject" ? subjectResolvers : objectResolvers;
        const current = row.resolver || "";
        const placeholder = `<option value=""${current === "" ? " selected" : ""}>Choose&hellip;</option>`;
        const choices = resolvers
          .map(
            (resolver) =>
              `<option value="${e(resolver.value)}"${resolver.value === current ? " selected" : ""}>${e(
                resolver.label,
              )}</option>`,
          )
          .join("");

        extra = `<label class="import-inline">Identified by
          <select class="form-select form-select-sm" data-role="resolver" data-column="${e(column.index)}">${placeholder}${choices}</select>
        </label>`;
      } else if (kind === KINDS.OBJECT && option?.identityEligible) {
        extra = `<label class="import-inline import-check">
          <input type="checkbox" class="form-check-input" data-role="match" data-column="${e(column.index)}"${
            row.match ? " checked" : ""
          }>
          Use to identify existing objects
        </label>`;
      }

      return `<tr>
        <th scope="row" class="import-header-cell">${e(column.header)}</th>
        <td class="import-sample-cell">${samples || '<span class="import-empty">(empty)</span>'}</td>
        <td>
          <select class="form-select form-select-sm" data-role="field" data-column="${e(column.index)}"
                  aria-label="Map ${e(column.header)} to">${fieldSelect(options, row.field ?? "", used)}</select>
          ${extra}
        </td>
      </tr>`;
    })
    .join("");

  return `<table class="table table-sm import-mapping-table">
    <thead><tr><th scope="col">Source column</th><th scope="col">Sample</th><th scope="col">OnyxJar field</th></tr></thead>
    <tbody>${body}</tbody>
  </table>`;
}

function problemList(problems, total) {
  if (!problems?.length) return "";

  const items = problems
    .map(
      (problem) =>
        `<li>${problem.row ? `<strong>Row ${e(problem.row)}:</strong> ` : ""}${e(problem.message)}</li>`,
    )
    .join("");

  const more = total > problems.length ? `<p class="import-muted">&hellip;and ${e(total - problems.length)} more.</p>` : "";

  return `<div class="import-problems" role="alert">
    <h3>These rows cannot be turned into changes</h3>
    <p>Fix the file or the mapping and preview again. Nothing is created until every row can be interpreted.</p>
    <ul>${items}</ul>${more}
  </div>`;
}

function itemList(items) {
  if (!items?.length) return "";

  const cards = items
    .map((item) => {
      const fields = item.fields
        .map(
          (field) => `<tr>
            <th scope="row">${e(field.field)}</th>
            <td>${item.operation === "update" ? displayValue(field.before) : ""}</td>
            <td>${displayValue(field.after)}</td>
          </tr>`,
        )
        .join("");

      const rows = item.rows > 1 ? ` (${e(item.rows)} rows)` : "";

      return `<details class="import-item">
        <summary>
          <span class="import-op import-op-${e(item.operation)}">${e(item.operation === "create" ? "CREATE" : "UPDATE")}</span>
          ${e(item.label)} <span class="import-muted">row ${e(item.row)}${rows}</span>
        </summary>
        <table class="table table-sm import-diff">
          <thead><tr><th scope="col">Field</th><th scope="col">Before</th><th scope="col">After</th></tr></thead>
          <tbody>${fields}</tbody>
        </table>
      </details>`;
    })
    .join("");

  return `<div class="import-items"><h3>First changes</h3>${cards}</div>`;
}

export function previewPanel(preview) {
  const summary = preview.summary;
  const noun = summary.kind === KINDS.RELATIONSHIP ? "Relationships" : "Objects";

  if (preview.blocked) {
    return `<p class="import-muted">${e(summary.rows)} rows</p>${problemList(preview.problems, preview.problem_count)}`;
  }

  const warnings = (summary.warnings ?? [])
    .map((warning) => `<li>${e(warning)}</li>`)
    .join("");

  const duplicates = summary.duplicate_identities
    ? `<div><dt>Duplicate source identities</dt><dd>${e(summary.duplicate_identities)} (across ${e(summary.duplicate_rows)} rows; later rows win)</dd></div>`
    : "";

  const unconverted = summary.unconverted_cells
    ? `<div><dt>Values not readable as their type</dt><dd>${e(summary.unconverted_cells)} (kept as typed; the proposal will flag them)</dd></div>`
    : "";

  const none = preview.change_count === 0
    ? '<p class="import-none"><strong>No changes detected.</strong> Every row already matches the model, so no proposal will be created.</p>'
    : "";

  return `
    <p class="import-total">${e(summary.rows)} rows &mdash; ${e(describeSummary(summary))}</p>
    ${warnings ? `<ul class="import-notes import-warnings">${warnings}</ul>` : ""}
    <dl class="import-facts import-counts">
      <div><dt>${e(noun)}</dt><dd>
        <span class="import-op import-op-create">${e(summary.creates)} CREATE</span>
        <span class="import-op import-op-update">${e(summary.updates)} UPDATE</span>
        <span class="import-op import-op-noop">${e(summary.no_ops)} NO-OP</span>
      </dd></div>
      <div><dt>Field changes</dt><dd>${e(summary.field_changes)}</dd></div>
      ${duplicates}${unconverted}
    </dl>
    ${none}
    ${itemList(preview.items)}
    <p class="import-muted">This shows the changes that would be proposed. They are checked when you review and submit the proposal.</p>`;
}

export function problemsFromError(data) {
  if (!data) return "";
  return problemList(data.problems, data.problem_count ?? data.problems?.length ?? 0);
}
