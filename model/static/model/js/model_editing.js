document.addEventListener("DOMContentLoaded", function () {

    /*
     * ---------------------------------------------------------
     * Model overview editing
     * ---------------------------------------------------------
     *
     * Temporary client-side proposal stub.
     *
     * This deliberately does not persist anything to Django.
     * The proposedValues object represents the future working
     * proposal state until the Proposal model/service exists.
     *
     * This file owns model overview editing only.
     * Sidebar navigation is handled by sidebar.js.
     * ---------------------------------------------------------
     */

    const proposedValues = {};


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

            /*
             * If this field already has a proposed value,
             * edit that value rather than reverting to the
             * canonical value.
             */
            if (Object.prototype.hasOwnProperty.call(
                proposedValues,
                fieldName
            )) {
                textarea.value = proposedValues[fieldName];
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

        button.addEventListener("click", function () {

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
             * Store the proposed value in the temporary
             * proposal state.
             *
             * This will later become a ProposalChange.
             */
            proposedValues[fieldName] = value;

            renderFieldValue(display, value);

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
        });

    });


    /*
     * ---------------------------------------------------------
     * Cancel
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

        button.addEventListener("click", function () {

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

            const textarea = editor
                ? editor.querySelector("textarea")
                : null;

            if (!display || !editor || !textarea) {
                return;
            }

            /*
             * Remove the temporary proposed value.
             */
            delete proposedValues[fieldName];

            /*
             * Restore the canonical value.
             *
             * Until proposals are persisted, the initial
             * textarea value represents the canonical model
             * value.
             */
            const canonicalValue = textarea.defaultValue;

            textarea.value = canonicalValue;

            renderFieldValue(display, canonicalValue);

            display.hidden = false;
            editor.hidden = true;

            if (editButton) {
                editButton.hidden = false;
            }

            if (proposedIndicator) {
                proposedIndicator.hidden = true;
            }

            button.hidden = true;
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
