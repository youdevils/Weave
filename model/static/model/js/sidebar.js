document.addEventListener("DOMContentLoaded", function () {
  /*
   * ---------------------------------------------------------
   * Model navigation
   * ---------------------------------------------------------
   *
   * This file owns model sidebar navigation only.
   * It must not contain model overview editing behaviour.
   * ---------------------------------------------------------
   */

  document.querySelectorAll(".model-nav-toggle").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      const group = toggle.closest(".model-nav-group");

      if (!group) {
        return;
      }

      const children = group.querySelector(".model-nav-children");

      if (!children) {
        return;
      }

      const parentLabel = group.querySelector(".model-nav-parent span");

      const sectionName = parentLabel
        ? parentLabel.textContent.trim()
        : "section";

      const expanded = toggle.getAttribute("aria-expanded") === "true";

      toggle.setAttribute("aria-expanded", expanded ? "false" : "true");

      toggle.setAttribute(
        "aria-label",
        expanded ? `Expand ${sectionName}` : `Collapse ${sectionName}`,
      );

      children.classList.toggle("collapsed", expanded);
    });
  });
});
