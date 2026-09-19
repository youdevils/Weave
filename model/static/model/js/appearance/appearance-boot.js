/**
 * Boots every appearance form on the page (Customise page, Object Type editor,
 * Relationship Type editor). One save refreshes all forms and previews, since a
 * model-level change (e.g. the accent) alters what other fields inherit.
 *
 * After a save, listeners can react to the ``appearance:updated`` event on
 * ``document`` (the Customise page uses it to refresh its live graph).
 */

import {
  applyGroups,
  collectValues,
  groupsForScope,
  initAppearanceForm,
  previewFor,
} from "./appearance-form.js";

const roots = Array.from(document.querySelectorAll("[data-appearance-form]"));

function inheritedLabelFor(root) {
  return root.dataset.inheritedLabel || "Default";
}

function valuesFromDom(root) {
  const values = {};
  for (const wrapper of root.querySelectorAll("[data-appearance-field]")) {
    const control = wrapper.querySelector("[data-appearance-control]");
    if (control) values[wrapper.dataset.appearanceField] = control.value;
  }
  return values;
}

function renderPreview(root, values) {
  const host = root.querySelector("[data-appearance-preview]");
  if (!host) return;

  const preview = previewFor(host.dataset.kind, values);

  if (preview.kind === "object_type") {
    const node = host.querySelector("[data-preview-node]");
    node.dataset.shape = preview.shape;
    Object.assign(node.style, preview.style);
    const icon = host.querySelector("[data-preview-icon]");
    icon.textContent = preview.icon;
    icon.hidden = !preview.icon;
    return;
  }

  const line = host.querySelector("[data-preview-line]");
  line.dataset.arrows = preview.arrows;
  Object.assign(line.style, preview.style);
  Object.assign(host.querySelector("[data-preview-label]").style, preview.labelStyle);
}

/** Re-render every form and preview from a save response. */
export function applyResponse(data) {
  for (const root of roots) {
    const groups = groupsForScope(root.dataset.scope || "", data.form);
    if (groups.length === 0) continue;
    applyGroups(root, groups, { inheritedLabel: inheritedLabelFor(root) });
    renderPreview(root, collectValues(groups));
  }
  document.dispatchEvent(new CustomEvent("appearance:updated", { detail: data }));
}

function initialGroups(root) {
  const script = root.querySelector('script[type="application/json"]');
  if (!script) return null;
  try {
    return JSON.parse(script.textContent);
  } catch (_error) {
    return null;
  }
}

for (const root of roots) {
  const groups = initialGroups(root);
  if (groups) {
    applyGroups(root, groups, { inheritedLabel: inheritedLabelFor(root) });
    renderPreview(root, collectValues(groups));
  } else {
    renderPreview(root, valuesFromDom(root));
  }
  initAppearanceForm(root, { onSaved: applyResponse });
}
