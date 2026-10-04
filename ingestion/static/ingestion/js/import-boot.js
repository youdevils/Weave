/**
 * Data Import page controller.
 *
 *   Upload -> Target -> Map -> Preview -> Create Proposal
 *
 * Presented as a guided workflow that shows one step at a time (`model.step`);
 * moving between steps is presentation only and never discards the person's work.
 *
 * The page holds only what the person has chosen (the staged upload, the target
 * and the per-column mapping). Every interpretation of that choice -- parsing,
 * identity, what would change -- is done by the server, from the persisted
 * source and the canonical model, and the mapping is re-validated there. Any
 * edit to the file, target or mapping discards the current preview, so the
 * proposal that is created is always the one that was previewed.
 */

import { createImportApi } from "./import-api.js";
import * as view from "./import-render.js";
import * as state from "./import-state.js";

export function startImport({ bootstrap, api = createImportApi({ urls: bootstrap.urls }) }) {
  const $ = (id) => document.getElementById(id);
  const el = {
    file: $("import-file"),
    uploadResult: $("import-upload-result"),
    reset: $("import-reset"),
    kind: document.querySelectorAll("input[name=import-kind]"),
    type: $("import-type"),
    mapping: $("import-mapping"),
    previewButton: $("import-preview-button"),
    preview: $("import-preview"),
    createButton: $("import-create-button"),
    status: $("import-status"),
    banner: $("import-banner"),
    steps: document.querySelectorAll("[data-step]"),
    workflow: $("import-workflow"),
    typeLabel: $("import-type-label"),
    progress: document.querySelectorAll("[data-goto]"),
    next: document.querySelectorAll("[data-nav=next]"),
    back: document.querySelectorAll("[data-nav=back]"),
  };

  const model = {
    step: "upload",
    source: null,
    columns: [],
    sampleRows: [],
    warnings: [],
    kind: state.KINDS.OBJECT,
    typeId: "",
    rows: [],
    preview: null,
    fresh: false,
    done: false,
    busy: false,
  };

  const types = () =>
    model.kind === state.KINDS.RELATIONSHIP ? bootstrap.targets.relationship_types : bootstrap.targets.object_types;

  const target = () => types().find((type) => type.type_id === model.typeId) ?? null;

  const mapping = () => state.buildMapping({ kind: model.kind, typeId: model.typeId, rows: model.rows });

  function showBanner(kind, message) {
    el.banner.innerHTML = view.banner(kind, message);
  }

  function setBusy(busy, message = "") {
    model.busy = busy;
    el.status.textContent = message;
    render();
  }

  function invalidatePreview() {
    model.preview = null;
    model.fresh = false;
  }

  function render() {
    const hasSource = Boolean(model.source);
    const hasTarget = hasSource && Boolean(target());
    const mapped = state.canPreview({ source: model.source, target: target(), mapping: mapping() });

    // Only one step is shown at a time; the person's work lives in `model`, so
    // moving between steps never discards it. A step whose prerequisites were
    // undone (say the mapping was edited, discarding the preview) closes again.
    const open = state.availableSteps({
      source: model.source,
      target: target(),
      mapping: mapping(),
      preview: model.preview,
      previewIsFresh: model.fresh,
    });
    const order = state.WIZARD_STEPS;

    if (!open[model.step]) {
      model.step = [...order].reverse().find((name) => open[name] && order.indexOf(name) < order.indexOf(model.step)) ?? "upload";
    }

    const current = order.indexOf(model.step);

    el.workflow.hidden = model.done;
    el.steps.forEach((step) => (step.hidden = step.dataset.step !== model.step));

    el.progress.forEach((button) => {
      const index = order.indexOf(button.dataset.goto);
      button.disabled = !open[button.dataset.goto];
      button.classList.toggle("is-current", index === current);
      button.classList.toggle("is-complete", index !== current && Boolean(open[order[index + 1]]));
      if (index === current) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });

    el.next.forEach((button) => (button.disabled = !open[order[current + 1]]));

    el.reset.hidden = !hasSource && !model.done;

    el.uploadResult.innerHTML = hasSource
      ? view.uploadSummary({
          source: model.source,
          columns: model.columns,
          sampleRows: model.sampleRows,
          warnings: model.warnings,
        })
      : "";

    el.typeLabel.textContent = model.kind === state.KINDS.RELATIONSHIP ? "Relationship type" : "Object type";
    el.type.innerHTML = view.typeOptions(types(), model.typeId);
    el.type.disabled = !hasSource || model.done;
    el.kind.forEach((input) => {
      input.checked = input.value === model.kind;
      input.disabled = !hasSource || model.done;
    });

    el.mapping.innerHTML = hasTarget
      ? view.mappingTable({
          kind: model.kind,
          target: target(),
          columns: model.columns,
          sampleRows: model.sampleRows,
          rows: model.rows,
          objectTypes: bootstrap.targets.object_types,
        })
      : '<p class="import-muted">Choose a destination to map the columns.</p>';

    el.previewButton.disabled = !mapped || model.busy || model.done;
    el.preview.innerHTML = model.preview ? view.previewPanel(model.preview) : "";

    const previewed = state.canCreate({ preview: model.preview, previewIsFresh: model.fresh });
    const noChanges = previewed && model.preview.change_count === 0;

    el.createButton.disabled = !previewed || model.busy || model.done;
    el.createButton.textContent = noChanges ? "Finish (no changes)" : "Create proposal";
  }

  function resetAll() {
    Object.assign(model, {
      step: "upload",
      source: null,
      columns: [],
      sampleRows: [],
      warnings: [],
      kind: state.KINDS.OBJECT,
      typeId: "",
      rows: [],
      preview: null,
      fresh: false,
      done: false,
    });
    el.file.value = "";
    showBanner("", "");
    render();
  }

  function applySuggestions() {
    const options = state.fieldOptions(model.kind, target());
    const suggestion = state.suggestMapping(
      model.columns.map((column) => column.header),
      options,
    );

    model.rows = model.columns.map((column) => {
      const field = suggestion[column.index] ?? "";
      const resolver =
        field === "endpoint.subject"
          ? state.defaultResolver(target(), "subject")
          : field === "endpoint.object"
            ? state.defaultResolver(target(), "object")
            : "";

      return { ...state.emptyRow(), field, resolver };
    });
  }

  // -- Navigation ----------------------------------------------------------

  function goTo(step) {
    model.step = step;
    render();
    document.querySelector(`[data-step="${step}"] .import-step-title`)?.focus();
  }

  el.progress.forEach((button) =>
    button.addEventListener("click", () => {
      if (!button.disabled) goTo(button.dataset.goto);
    }),
  );

  const move = (offset) => () => goTo(state.WIZARD_STEPS[state.WIZARD_STEPS.indexOf(model.step) + offset]);
  el.next.forEach((button) => button.addEventListener("click", move(1)));
  el.back.forEach((button) => button.addEventListener("click", move(-1)));

  // -- Upload --------------------------------------------------------------

  el.file.addEventListener("change", async () => {
    const file = el.file.files?.[0];
    if (!file) return;

    showBanner("", "");

    if (model.source) await api.discard(model.source.id);

    setBusy(true, "Reading the file…");
    const result = await api.upload(file);
    model.busy = false;
    el.status.textContent = "";

    if (!result.ok || !result.data?.success) {
      resetAll();
      showBanner("danger", result.data?.error ?? "The file could not be uploaded.");
      return;
    }

    Object.assign(model, {
      source: result.data.source,
      columns: result.data.columns,
      sampleRows: result.data.sample_rows,
      warnings: result.data.warnings,
      typeId: "",
      rows: result.data.columns.map(() => state.emptyRow()),
    });
    invalidatePreview();
    render();
  });

  el.reset.addEventListener("click", async () => {
    if (model.source) await api.discard(model.source.id);
    resetAll();
  });

  // -- Target --------------------------------------------------------------

  el.kind.forEach((input) =>
    input.addEventListener("change", () => {
      model.kind = input.value;
      model.typeId = "";
      model.rows = model.columns.map(() => state.emptyRow());
      invalidatePreview();
      render();
    }),
  );

  el.type.addEventListener("change", () => {
    model.typeId = el.type.value;
    invalidatePreview();

    if (target()) applySuggestions();
    else model.rows = model.columns.map(() => state.emptyRow());

    render();
  });

  // -- Mapping -------------------------------------------------------------

  el.mapping.addEventListener("change", (event) => {
    const control = event.target;
    const role = control.dataset?.role;
    if (!role) return;

    const column = Number(control.dataset.column);
    const row = model.rows[column];

    if (role === "field") {
      row.field = control.value;
      row.match = false;
      row.resolver =
        control.value === "endpoint.subject"
          ? state.defaultResolver(target(), "subject")
          : control.value === "endpoint.object"
            ? state.defaultResolver(target(), "object")
            : "";
    } else if (role === "match") {
      // At most one match attribute: turning one on turns the others off.
      model.rows.forEach((other) => (other.match = false));
      row.match = control.checked;
    } else if (role === "resolver") {
      row.resolver = control.value;
    }

    invalidatePreview();
    render();
    el.mapping.querySelector(`[data-role="${role}"][data-column="${column}"]`)?.focus();
  });

  // -- Preview -------------------------------------------------------------

  el.previewButton.addEventListener("click", async () => {
    showBanner("", "");
    setBusy(true, "Working out the changes…");
    const result = await api.preview(model.source.id, mapping());
    model.busy = false;
    el.status.textContent = "";

    if (!result.ok || !result.data?.success) {
      invalidatePreview();
      render();
      showBanner("danger", explain(result.data, "The preview could not be built."));
      return;
    }

    model.preview = result.data;
    model.fresh = true;
    render();
  });

  // -- Create --------------------------------------------------------------

  el.createButton.addEventListener("click", async () => {
    showBanner("", "");
    setBusy(true, "Creating the proposal…");
    const result = await api.create(model.source.id, mapping());
    model.busy = false;
    el.status.textContent = "";

    if (result.data?.success && result.data.no_changes) {
      model.done = true;
      model.source = null;
      render();
      showBanner("success", "No changes detected. Every row already matches the model, so no proposal was created.");
      return;
    }

    if (result.data?.success) {
      window.location.assign(result.data.proposal_url);
      return;
    }

    invalidatePreview();
    render();

    if (result.status === 422) {
      el.preview.innerHTML = view.problemsFromError(result.data);
    }

    showBanner("danger", explain(result.data, "The proposal could not be created."));
  });

  function explain(data, fallback) {
    if (data?.messages?.length) return data.messages.join(" ");
    return data?.error ?? fallback;
  }

  render();
}
