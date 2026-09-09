document.addEventListener("DOMContentLoaded", function () {

    /*
     * ---------------------------------------------------------
     * Model overview editing
     * ---------------------------------------------------------
     *
     * Working proposal state is persisted by Django.
     *
     * Save:
     *   POST field + value
     *
     * Discard:
     *   POST field + discard action
     *
     * The canonical Model is never modified by this UI.
     * ---------------------------------------------------------
     */


    const overview = document.querySelector(".model-overview");

    if (!overview) {
        return;
    }


    /*
     * ---------------------------------------------------------
     * Edit
     * ---------------------------------------------------------
     */

    document.querySelectorAll(".model-edit-button").forEach(function (button) {

        button.addEventListener("click", function () {

            const fieldName = button.dataset.editField;
            const field = button.closest(".model-overview-field");

            if (!field) {
                return;
            }

            const display = field.querySelector(
                `[data-field="${fieldName}"]`
            );

            const editor = field.querySelector(
                `[data-editor="${fieldName}"]`
            );

            if (!display || !editor) {
                return;
            }

            const textarea = editor.querySelector("textarea");

            if (!textarea) {
                return;
            }

            display.hidden = true;
            editor.hidden = false;
            button.hidden = true;

            textarea.focus();
        });

    });


    /*
     * ---------------------------------------------------------
     * Save
     * ---------------------------------------------------------
     */

    document.querySelectorAll(".model-save-button").forEach(function (button) {

        button.addEventListener("click", async function () {

            const fieldName = button.dataset.saveField;
            const field = button.closest(".model-overview-field");

            if (!field) {
                return;
            }

            const display = field.querySelector(
                `[data-field="${fieldName}"]`
            );

            const editor = field.querySelector(
                `[data-editor="${fieldName}"]`
            );

            const editButton = field.querySelector(
                `[data-edit-field="${fieldName}"]`
            );

            const proposedIndicator = field.querySelector(
                `[data-proposed-indicator="${fieldName}"]`
            );

            const discardButton = field.querySelector(
                `[data-discard-field="${fieldName}"]`
            );

            if (!display || !editor) {
                return;
            }

            const textarea = editor.querySelector("textarea");

            if (!textarea) {
                return;
            }

            const value = textarea.value;

            /*
             * Prevent duplicate submissions while the request
             * is in progress.
             */
            button.disabled = true;

            const updateUrl = overview.dataset.updateUrl;
            const csrfToken = overview.querySelector(
                "[name=csrfmiddlewaretoken]"
            );

            if (!updateUrl || !csrfToken) {
                button.disabled = false;
                alert("Unable to save: update URL or CSRF token is missing.");
                return;
            }

            try {

                const response = await fetch(updateUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken.value,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body: new URLSearchParams({
                        field: fieldName,
                        value: value,
                    }),
                });

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "Unable to save proposed change."
                    );
                }

                /*
                 * Django returns the persisted proposed value.
                 */
                renderFieldValue(display, data.value);

                display.hidden = false;
                editor.hidden = true;

                if (editButton) {
                    editButton.hidden = false;
                }

                if (proposedIndicator) {
                    proposedIndicator.hidden = false;
                }

                if (discardButton) {
                    discardButton.hidden = false;
                }

                /*
                 * Keep the textarea aligned with the persisted
                 * proposal value.
                 */
                textarea.value = data.value;

            } catch (error) {

                console.error(error);

                alert(error.message);

            } finally {

                button.disabled = false;

            }

        });

    });


    /*
     * ---------------------------------------------------------
     * Cancel
     * ---------------------------------------------------------
     *
     * Cancel does not modify the proposal.
     * It simply closes the editor.
     *
     * The textarea already contains the current effective
     * value because the page loads the proposed value when
     * one exists.
     * ---------------------------------------------------------
     */

    document.querySelectorAll(".model-cancel-button").forEach(function (button) {

        button.addEventListener("click", function () {

            const fieldName = button.dataset.cancelField;
            const field = button.closest(".model-overview-field");

            if (!field) {
                return;
            }

            const display = field.querySelector(
                `[data-field="${fieldName}"]`
            );

            const editor = field.querySelector(
                `[data-editor="${fieldName}"]`
            );

            const editButton = field.querySelector(
                `[data-edit-field="${fieldName}"]`
            );

            if (!display || !editor) {
                return;
            }

            display.hidden = false;
            editor.hidden = true;

            if (editButton) {
                editButton.hidden = false;
            }

        });

    });


    /*
     * ---------------------------------------------------------
     * Discard proposed change
     * ---------------------------------------------------------
     */

    document.querySelectorAll(".model-discard-button").forEach(function (button) {

        button.addEventListener("click", async function () {

            const fieldName = button.dataset.discardField;
            const field = button.closest(".model-overview-field");

            if (!field) {
                return;
            }

            const display = field.querySelector(
                `[data-field="${fieldName}"]`
            );

            const editor = field.querySelector(
                `[data-editor="${fieldName}"]`
            );

            const editButton = field.querySelector(
                `[data-edit-field="${fieldName}"]`
            );

            const proposedIndicator = field.querySelector(
                `[data-proposed-indicator="${fieldName}"]`
            );

            if (!display || !editor) {
                return;
            }

            button.disabled = true;

            const updateUrl = overview.dataset.updateUrl;
            const csrfToken = overview.querySelector(
                "[name=csrfmiddlewaretoken]"
            );

            if (!updateUrl || !csrfToken) {
                button.disabled = false;
                alert("Unable to discard: update URL or CSRF token is missing.");
                return;
            }

            try {

                const response = await fetch(updateUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken.value,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body: new URLSearchParams({
                        field: fieldName,
                        action: "discard",
                    }),
                });

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "Unable to discard proposed change."
                    );
                }

                /*
                 * Django returns the canonical value after the
                 * proposal change has been discarded.
                 */
                renderFieldValue(display, data.value);

                const textarea = editor.querySelector("textarea");

                if (textarea) {
                    textarea.value = data.value;
                }

                display.hidden = false;
                editor.hidden = true;

                if (editButton) {
                    editButton.hidden = false;
                }

                if (proposedIndicator) {
                    proposedIndicator.hidden = true;
                }

                button.hidden = true;

            } catch (error) {

                console.error(error);

                alert(error.message);

            } finally {

                button.disabled = false;

            }

        });

    });


    /*
     * ---------------------------------------------------------
     * Render field value
     * ---------------------------------------------------------
     *
     * Safely renders the value as text rather than HTML.
     * ---------------------------------------------------------
     */

    function renderFieldValue(element, value) {

        element.replaceChildren();

        const paragraph = document.createElement("p");

        if (value.trim() === "") {
            paragraph.className = "model-field-empty";
            paragraph.textContent = "Not defined";
        } else {
            paragraph.textContent = value;
        }

        element.appendChild(paragraph);
    }

});