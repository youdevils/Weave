/**
 * Pure selection-state logic for the data index's row checkboxes.
 * Selection is page-local only: nothing here persists across a page
 * (re)load, matching the "select all VISIBLE rows" contract.
 */

/** New selection Set with `id` added or removed. */
export function toggleSelection(selectedIds, id, checked) {
  const next = new Set(selectedIds);
  if (checked) next.add(id);
  else next.delete(id);
  return next;
}

export function selectionCount(selectedIds) {
  return selectedIds.size;
}

/** { checked, indeterminate } for the "select all visible" header checkbox. */
export function syncHeaderCheckboxState(selectedIds, visibleIds) {
  if (visibleIds.length === 0 || selectedIds.size === 0) {
    return { checked: false, indeterminate: false };
  }
  const allSelected = visibleIds.every((id) => selectedIds.has(id));
  if (allSelected) return { checked: true, indeterminate: false };
  const someSelected = visibleIds.some((id) => selectedIds.has(id));
  return { checked: false, indeterminate: someSelected };
}
