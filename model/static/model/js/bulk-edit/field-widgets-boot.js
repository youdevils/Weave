/**
 * DOM wiring for the bulk-edit page: enabling/disabling each field's
 * value control based on its mode select, and invalidating a successful
 * Preview the moment any field changes afterward (a UX safeguard only --
 * the backend's fingerprint check and full re-validation on Apply are
 * the actual guarantee).
 */

import { widgetState } from "./field-widgets.js";

export function initBulkFieldWidgets(form) {
  if (!form) return;

  const modeSelects = Array.from(form.querySelectorAll("[data-bulk-mode-select]"));
  const applyButton = form.querySelector("[data-bulk-apply]");

  function syncValueControl(select) {
    const targetId = select.dataset.valueTarget;
    if (!targetId) return;
    const control = form.querySelector(`#${targetId}`);
    if (!control) return;
    control.disabled = !widgetState(select.value);
  }

  modeSelects.forEach((select) => syncValueControl(select));

  function invalidatePreview() {
    if (!applyButton) return;
    applyButton.disabled = true;
    applyButton.setAttribute("aria-disabled", "true");
    form.dataset.previewed = "false";
  }

  form.addEventListener("change", (event) => {
    const select = event.target.closest("[data-bulk-mode-select]");
    if (select) syncValueControl(select);
    invalidatePreview();
  });

  form.addEventListener("input", (event) => {
    if (event.target.closest("[data-bulk-value-wrapper]")) {
      invalidatePreview();
    }
  });
}

if (typeof document !== "undefined") {
  document
    .querySelectorAll("[data-bulk-edit-form]")
    .forEach((form) => initBulkFieldWidgets(form));
}
