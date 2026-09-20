/*
 * ---------------------------------------------------------
 * Model navigation
 * ---------------------------------------------------------
 *
 * This file owns model sidebar navigation only.
 * It must not contain model overview editing behaviour.
 *
 * Only the child groups (Object Types, Relationship Types, Object,
 * Relationships) collapse; the top-level section headings are always
 * expanded and have no toggle.
 *
 * Click handling is delegated to `document` (rather than bound to
 * each `.model-nav-toggle` at load time) because the sidebar markup
 * can be replaced wholesale after a proposal-editing AJAX save
 * (see model_editing.js's `postForm`), which would otherwise leave
 * freshly-inserted toggles without listeners.
 * ---------------------------------------------------------
 */

document.addEventListener("click", function (event) {
  const toggle = event.target.closest(".model-nav-toggle");

  if (!toggle) {
    return;
  }

  const container = toggle.closest(".model-nav-group");

  if (!container) {
    return;
  }

  const children = container.querySelector(":scope > .model-nav-children");

  if (!children) {
    return;
  }

  const label = container.querySelector(".model-nav-parent span");

  const sectionName = label ? label.textContent.trim() : "section";

  const expanded = toggle.getAttribute("aria-expanded") === "true";

  toggle.setAttribute("aria-expanded", expanded ? "false" : "true");

  toggle.setAttribute(
    "aria-label",
    expanded ? `Expand ${sectionName}` : `Collapse ${sectionName}`,
  );

  children.classList.toggle("collapsed", expanded);
});
