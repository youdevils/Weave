/** Pure logic for the bulk-edit page's mode/value field widgets. */

/** Whether a field's value control should be enabled, given its mode. */
export function widgetState(mode) {
  return mode === "set";
}
