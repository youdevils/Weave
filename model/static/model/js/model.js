document.addEventListener("DOMContentLoaded", function () {

    document.querySelectorAll(".model-nav-toggle").forEach(function (toggle) {

        toggle.addEventListener("click", function () {

            const group = toggle.closest(".model-nav-group");
            const children = group.querySelector(".model-nav-children");

            const sectionName = group
                .querySelector(".model-nav-parent span")
                .textContent
                .trim();

            const expanded =
                toggle.getAttribute("aria-expanded") === "true";

            toggle.setAttribute(
                "aria-expanded",
                expanded ? "false" : "true"
            );

            toggle.setAttribute(
                "aria-label",
                expanded
                    ? `Expand ${sectionName}`
                    : `Collapse ${sectionName}`
            );

            children.classList.toggle("collapsed", expanded);
        });

    });

});