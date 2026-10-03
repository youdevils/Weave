/**
 * DOM wiring for the data index's row-selection checkboxes and
 * contextual bulk-action bar. Selection is page-local only -- nothing
 * here is persisted across a page (re)load.
 */

import {
  selectionCount,
  syncHeaderCheckboxState,
  toggleSelection,
} from "./selection-state.js";

export function initBulkSelect(form) {
  if (!form) return;

  const checkboxes = Array.from(form.querySelectorAll("[data-bulk-select]"));
  const selectAll = form.querySelector("[data-bulk-select-all]");
  const actionBar = form.querySelector("[data-bulk-actionbar]");
  const countLabel = actionBar
    ? actionBar.querySelector("[data-bulk-count]")
    : null;
  const clearButton = actionBar
    ? actionBar.querySelector("[data-bulk-clear]")
    : null;

  let selectedIds = new Set();

  function visibleIds() {
    return checkboxes.map((checkbox) => checkbox.value);
  }

  function render() {
    const count = selectionCount(selectedIds);

    checkboxes.forEach((checkbox) => {
      const checked = selectedIds.has(checkbox.value);
      checkbox.checked = checked;
      const row = checkbox.closest("[data-bulk-row]");
      if (row) row.dataset.selected = checked ? "true" : "false";
    });

    if (selectAll) {
      const state = syncHeaderCheckboxState(selectedIds, visibleIds());
      selectAll.checked = state.checked;
      selectAll.indeterminate = state.indeterminate;
    }

    if (actionBar) actionBar.hidden = count === 0;
    if (countLabel) {
      countLabel.textContent = `${count} selected`;
    }
  }

  checkboxes.forEach((checkbox) => {
    // The row itself navigates on click (model_editing.js); stop that
    // from firing when the click actually targeted the checkbox.
    checkbox.addEventListener("click", (event) => event.stopPropagation());

    checkbox.addEventListener("change", () => {
      selectedIds = toggleSelection(
        selectedIds,
        checkbox.value,
        checkbox.checked,
      );
      render();
    });
  });

  if (selectAll) {
    selectAll.addEventListener("click", (event) => event.stopPropagation());

    selectAll.addEventListener("change", () => {
      selectedIds = selectAll.checked ? new Set(visibleIds()) : new Set();
      render();
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      selectedIds = new Set();
      render();
    });
  }

  render();
}

if (typeof document !== "undefined") {
  document
    .querySelectorAll("[data-bulk-select-form]")
    .forEach((form) => initBulkSelect(form));
}
