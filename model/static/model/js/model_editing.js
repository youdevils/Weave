document.addEventListener("DOMContentLoaded", function () {

    const editors = document.querySelectorAll(".proposal-editor");

    if (!editors.length) {
        return;
    }

    /*
     * ============================================================
     * Initialise each editor
     * ============================================================
     */

    editors.forEach(function (editorRoot) {

        const updateUrl = editorRoot.dataset.updateUrl;

        if (!updateUrl) {
            console.error(
                "Proposal editor: data-update-url is missing."
            );
            return;
        }


        /*
         * --------------------------------------------------------
         * CSRF
         * --------------------------------------------------------
         */

        const csrfToken = (
            editorRoot.querySelector(
                "[name=csrfmiddlewaretoken]"
            )
            || document.querySelector(
                "[name=csrfmiddlewaretoken]"
            )
        );

        if (!csrfToken) {
            console.error(
                "Proposal editor: CSRF token is missing."
            );
            return;
        }


        /*
         * --------------------------------------------------------
         * Edit
         * --------------------------------------------------------
         */

        editorRoot.addEventListener(
            "click",
            function (event) {

                const button = event.target.closest(
                    '[data-proposal-action="edit"]'
                );

                if (!button) {
                    return;
                }

                const field = getFieldContainer(button);

                if (!field) {
                    return;
                }

                openField(field);

            }
        );


        /*
         * --------------------------------------------------------
         * Cancel
         * --------------------------------------------------------
         */

        editorRoot.addEventListener(
            "click",
            function (event) {

                const button = event.target.closest(
                    '[data-proposal-action="cancel"]'
                );

                if (!button) {
                    return;
                }

                const field = getFieldContainer(button);

                if (!field) {
                    return;
                }

                cancelField(field);

            }
        );


        /*
         * --------------------------------------------------------
         * Save
         * --------------------------------------------------------
         */

        editorRoot.addEventListener(
            "click",
            async function (event) {

                const button = event.target.closest(
                    '[data-proposal-action="save"]'
                );

                if (!button) {
                    return;
                }

                const field = getFieldContainer(button);

                if (!field) {
                    return;
                }

                await saveField(
                    editorRoot,
                    csrfToken,
                    field,
                    button,
                );

            }
        );


        /*
         * --------------------------------------------------------
         * Discard
         * --------------------------------------------------------
         */

        editorRoot.addEventListener(
            "click",
            async function (event) {

                const button = event.target.closest(
                    '[data-proposal-action="discard"]'
                );

                if (!button) {
                    return;
                }

                const field = getFieldContainer(button);

                if (!field) {
                    return;
                }

                await discardField(
                    editorRoot,
                    csrfToken,
                    field,
                    button,
                );

            }
        );


        /*
         * --------------------------------------------------------
         * Escape closes the currently edited field.
         * --------------------------------------------------------
         *
         * Escape is intentionally equivalent to Cancel.
         *
         * It does not discard a proposal.
         */

        editorRoot.addEventListener(
            "keydown",
            function (event) {

                if (event.key !== "Escape") {
                    return;
                }

                const editor = event.target.closest(
                    "[data-field-editor]"
                );

                if (!editor) {
                    return;
                }

                const field = editor.closest(
                    ".proposal-editor-field"
                );

                if (!field) {
                    return;
                }

                cancelField(field);

            }
        );

    });


    /*
     * ============================================================
     * Field helpers
     * ============================================================
     */


    function getFieldContainer(element) {

        return element.closest(
            ".proposal-editor-field"
        );

    }


    function getFieldName(field) {

        return field.dataset.field || null;

    }


    function getDisplay(field) {

        const fieldName = getFieldName(field);

        if (!fieldName) {
            return null;
        }

        return field.querySelector(
            `[data-field-display="${CSS.escape(fieldName)}"]`
        );

    }


    function getEditor(field) {

        const fieldName = getFieldName(field);

        if (!fieldName) {
            return null;
        }

        return field.querySelector(
            `[data-field-editor="${CSS.escape(fieldName)}"]`
        );

    }


    function getEditButton(field) {

        return field.querySelector(
            '[data-proposal-action="edit"]'
        );

    }


    function getSaveButton(field) {

        return field.querySelector(
            '[data-proposal-action="save"]'
        );

    }


    function getCancelButton(field) {

        return field.querySelector(
            '[data-proposal-action="cancel"]'
        );

    }


    function getDiscardButton(field) {

        return field.querySelector(
            '[data-proposal-action="discard"]'
        );

    }


    function getProposalIndicator(field) {

        return field.querySelector(
            "[data-proposal-indicator]"
        );

    }


    function getInput(editor) {

        return editor.querySelector(
            "input:not([type=hidden]):not([type=submit]), " +
            "textarea, " +
            "select"
        );

    }


    /*
     * ============================================================
     * Open field
     * ============================================================
     */

    function openField(field) {

        const display = getDisplay(field);
        const editor = getEditor(field);
        const editButton = getEditButton(field);

        if (!display || !editor) {
            return;
        }

        const input = getInput(editor);

        if (!input) {
            return;
        }

        /*
         * Only one field on the same editor should be actively
         * edited at a time.
         */

        const root = field.closest(".proposal-editor");

        if (root) {
            closeOtherFields(root, field);
        }

        display.hidden = true;
        editor.hidden = false;

        if (editButton) {
            editButton.hidden = true;
        }

        input.focus();

        /*
         * For text controls, place the cursor at the end.
         */

        if (
            input instanceof HTMLInputElement
            || input instanceof HTMLTextAreaElement
        ) {
            try {
                input.setSelectionRange(
                    input.value.length,
                    input.value.length
                );
            } catch (error) {
                /*
                 * Some input types do not support selection ranges.
                 * Nothing needs to be done.
                 */
            }
        }

    }


    /*
     * ============================================================
     * Close other fields
     * ============================================================
     */

    function closeOtherFields(root, currentField) {

        root.querySelectorAll(
            ".proposal-editor-field"
        ).forEach(function (field) {

            if (field === currentField) {
                return;
            }

            const editor = getEditor(field);
            const display = getDisplay(field);

            if (!editor || !display) {
                return;
            }

            /*
             * Do not destroy edited values here.
             *
             * This function merely closes another field.
             * The authoritative value remains in the input until
             * the user explicitly saves or cancels it.
             */

            editor.hidden = true;
            display.hidden = false;

            const editButton = getEditButton(field);

            if (editButton) {
                editButton.hidden = false;
            }

        });

    }


    /*
     * ============================================================
     * Cancel field
     * ============================================================
     */

    function cancelField(field) {

        const display = getDisplay(field);
        const editor = getEditor(field);
        const editButton = getEditButton(field);

        if (!display || !editor) {
            return;
        }

        editor.hidden = true;
        display.hidden = false;

        if (editButton) {
            editButton.hidden = false;
        }

    }


    /*
     * ============================================================
     * Save field
     * ============================================================
     */

    async function saveField(
        root,
        csrfToken,
        field,
        button,
    ) {

        const fieldName = getFieldName(field);

        if (!fieldName) {
            return;
        }

        const display = getDisplay(field);
        const editor = getEditor(field);

        if (!display || !editor) {
            return;
        }

        const input = getInput(editor);

        if (!input) {
            return;
        }

        const value = readInputValue(input);

        /*
         * Prevent duplicate requests.
         */

        button.disabled = true;

        try {

            const response = await fetch(
                root.dataset.updateUrl,
                {
                    method: "POST",

                    headers: {
                        "X-CSRFToken": csrfToken.value,
                        "Content-Type":
                            "application/x-www-form-urlencoded",
                        "X-Requested-With":
                            "XMLHttpRequest",
                    },

                    body: new URLSearchParams({
                        field: fieldName,
                        value: value,
                    }),
                }
            );


            const data = await parseJsonResponse(response);


            if (!response.ok || !data.success) {
                throw new Error(
                    data.error
                    || "Unable to save proposed change."
                );
            }


            /*
             * The server's returned value is authoritative.
             *
             * This matters for normalisation, trimming, coercion,
             * or future field-specific processing.
             */

            const persistedValue = normaliseValue(
                data.value
            );


            writeInputValue(
                input,
                persistedValue
            );


            renderDisplayValue(
                display,
                persistedValue,
                input
            );


            /*
             * Close the editor.
             */

            editor.hidden = true;
            display.hidden = false;


            const editButton = getEditButton(field);

            if (editButton) {
                editButton.hidden = false;
            }


            /*
             * A successful save means there is now a proposal for
             * this field.
             */

            const proposalIndicator =
                getProposalIndicator(field);

            if (proposalIndicator) {
                proposalIndicator.hidden = false;
            }


            const discardButton =
                getDiscardButton(field);

            if (discardButton) {
                discardButton.hidden = false;
            }

        } catch (error) {

            console.error(
                "Proposal editor save failed:",
                error
            );

            showError(
                field,
                error.message
            );

        } finally {

            button.disabled = false;

        }

    }


    /*
     * ============================================================
     * Discard field
     * ============================================================
     */

    async function discardField(
        root,
        csrfToken,
        field,
        button,
    ) {

        const fieldName = getFieldName(field);

        if (!fieldName) {
            return;
        }

        const display = getDisplay(field);
        const editor = getEditor(field);

        if (!display || !editor) {
            return;
        }

        const input = getInput(editor);

        if (!input) {
            return;
        }

        button.disabled = true;


        try {

            const response = await fetch(
                root.dataset.updateUrl,
                {
                    method: "POST",

                    headers: {
                        "X-CSRFToken": csrfToken.value,
                        "Content-Type":
                            "application/x-www-form-urlencoded",
                        "X-Requested-With":
                            "XMLHttpRequest",
                    },

                    body: new URLSearchParams({
                        field: fieldName,
                        action: "discard",
                    }),
                }
            );


            const data = await parseJsonResponse(response);


            if (!response.ok || !data.success) {
                throw new Error(
                    data.error
                    || "Unable to discard proposed change."
                );
            }


            /*
             * The discard response contains the canonical value.
             */

            const canonicalValue = normaliseValue(
                data.value
            );


            writeInputValue(
                input,
                canonicalValue
            );


            renderDisplayValue(
                display,
                canonicalValue,
                input
            );


            /*
             * Close editor.
             */

            editor.hidden = true;
            display.hidden = false;


            const editButton = getEditButton(field);

            if (editButton) {
                editButton.hidden = false;
            }


            /*
             * The proposal indicator disappears because there is
             * no longer a proposed value for this field.
             */

            const proposalIndicator =
                getProposalIndicator(field);

            if (proposalIndicator) {
                proposalIndicator.hidden = true;
            }


            button.hidden = true;

        } catch (error) {

            console.error(
                "Proposal editor discard failed:",
                error
            );

            showError(
                field,
                error.message
            );

        } finally {

            button.disabled = false;

        }

    }


    /*
     * ============================================================
     * Input handling
     * ============================================================
     */


    function readInputValue(input) {

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {
            return input.checked ? "true" : "false";
        }

        return input.value;

    }


    function writeInputValue(
        input,
        value,
    ) {

        const stringValue = normaliseValue(value);

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {
            input.checked = (
                stringValue === "true"
                || stringValue === "1"
                || stringValue === "yes"
                || stringValue === "on"
            );

            return;
        }


        input.value = stringValue;

    }


    function normaliseValue(value) {

        if (value === null || value === undefined) {
            return "";
        }

        return String(value);

    }


    /*
     * ============================================================
     * Display rendering
     * ============================================================
     *
     * Values are always rendered using textContent.
     *
     * This deliberately prevents proposed model data from becoming
     * executable HTML.
     */

    function renderDisplayValue(
        display,
        value,
        input,
    ) {

        const stringValue = normaliseValue(value);

        display.replaceChildren();


        /*
         * Checkbox
         */

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {

            const paragraph =
                document.createElement("p");

            paragraph.textContent = (
                input.checked
                    ? "Yes"
                    : "No"
            );

            display.appendChild(paragraph);

            return;

        }


        /*
         * Select
         */

        if (input instanceof HTMLSelectElement) {

            const paragraph =
                document.createElement("p");

            const selectedOption =
                input.options[input.selectedIndex];

            if (
                !stringValue.trim()
                || !selectedOption
            ) {

                paragraph.className =
                    "proposal-editor-field-empty";

                paragraph.textContent =
                    "Not defined";

            } else {

                paragraph.textContent =
                    selectedOption.textContent;

            }

            display.appendChild(paragraph);

            return;

        }


        /*
         * Text / textarea
         */

        const paragraph =
            document.createElement("p");


        if (!stringValue.trim()) {

            paragraph.className =
                "proposal-editor-field-empty";

            paragraph.textContent =
                "Not defined";

        } else {

            paragraph.textContent =
                stringValue;

        }


        display.appendChild(paragraph);

    }


    /*
     * ============================================================
     * JSON handling
     * ============================================================
     */

    async function parseJsonResponse(response) {

        const contentType =
            response.headers.get("content-type")
            || "";

        if (
            !contentType.includes(
                "application/json"
            )
        ) {

            throw new Error(
                "The server returned an unexpected response."
            );

        }

        try {

            return await response.json();

        } catch (error) {

            throw new Error(
                "The server returned invalid JSON."
            );

        }

    }


    /*
     * ============================================================
     * Error display
     * ============================================================
     *
     * A field-local message is preferred over alert().
     *
     * The template can provide:
     *
     * <div data-proposal-error hidden></div>
     *
     * When absent, we fall back to console.error rather than using
     * intrusive browser alerts.
     */

    function showError(
        field,
        message,
    ) {

        const errorElement =
            field.querySelector(
                "[data-proposal-error]"
            );

        if (errorElement) {

            errorElement.textContent = message;
            errorElement.hidden = false;

            return;

        }


        console.error(
            "Proposal editor:",
            message
        );

    }

});

    /*
     * ============================================================
     * Attributes
     * ============================================================

     */


document.querySelectorAll(
        "[data-edit-attribute]"
    ).forEach(function (button) {

        button.addEventListener(
            "click",
            function () {

                const attribute =
                    button.closest(
                        ".model-object-type-attribute"
                    );

                if (!attribute) {
                    return;
                }

                const display =
                    attribute.querySelector(
                        ".model-object-type-attribute-display"
                    );

                const editor =
                    attribute.querySelector(
                        "[data-attribute-editor]"
                    );

                if (!display || !editor) {
                    return;
                }

                display.hidden = true;
                editor.hidden = false;

                const input =
                    editor.querySelector(
                        "input, textarea, select"
                    );

                if (input) {
                    input.focus();
                }

            }
        );

    });


    document.querySelectorAll(
        "[data-cancel-attribute]"
    ).forEach(function (button) {

        button.addEventListener(
            "click",
            function () {

                const attribute =
                    button.closest(
                        ".model-object-type-attribute"
                    );

                if (!attribute) {
                    return;
                }

                const display =
                    attribute.querySelector(
                        ".model-object-type-attribute-display"
                    );

                const editor =
                    attribute.querySelector(
                        "[data-attribute-editor]"
                    );

                if (!display || !editor) {
                    return;
                }

                editor.hidden = true;
                display.hidden = false;

            }
        );

    });

    /*
 * ============================================================
 * AttributeDefinition save
 * ============================================================
 *
 * The attribute editor is currently a compound editor:
 * one Save attribute action may produce several field-level
 * ProposalChange records.
 * ============================================================
 */

document.querySelectorAll(
    "[data-save-attribute]"
).forEach(function (button) {

    button.addEventListener(
        "click",
        async function () {

            const attribute =
                button.closest(
                    ".model-object-type-attribute"
                );

            if (!attribute) {
                return;
            }

            const attributeId =
                attribute.dataset.attributeId;

            if (!attributeId) {
                return;
            }

            const editor =
                attribute.querySelector(
                    "[data-attribute-editor]"
                );

            if (!editor) {
                return;
            }

            const errorElement =
                attribute.querySelector(
                    "[data-attribute-error]"
                );

            const root =
                attribute.closest(
                    ".proposal-editor"
                );

            if (!root) {
                return;
            }

            const updateUrl =
                root.dataset.updateUrl;

            const csrfToken =
                root.querySelector(
                    "[name=csrfmiddlewaretoken]"
                );

            if (!updateUrl || !csrfToken) {
                return;
            }

            /*
             * Clear previous error.
             */

            if (errorElement) {
                errorElement.hidden = true;
                errorElement.textContent = "";
            }

            button.disabled = true;

            try {

                const formData =
                    new URLSearchParams();

                formData.set(
                    "action",
                    "save_attribute"
                );

                formData.set(
                    "attribute_id",
                    attributeId
                );

                const nameInput =
                    editor.querySelector(
                        '[name="attribute_name"]'
                    );

                const keyInput =
                    editor.querySelector(
                        '[name="attribute_key"]'
                    );

                const dataTypeInput =
                    editor.querySelector(
                        '[name="attribute_data_type"]'
                    );

                const descriptionInput =
                    editor.querySelector(
                        '[name="attribute_description"]'
                    );

                const defaultValueInput =
                    editor.querySelector(
                        '[name="attribute_default_value"]'
                    );

                const sortOrderInput =
                    editor.querySelector(
                        '[name="attribute_sort_order"]'
                    );

                const requiredInput =
                    editor.querySelector(
                        '[name="attribute_required"]'
                    );

                formData.set(
                    "attribute_name",
                    nameInput
                        ? nameInput.value
                        : ""
                );

                formData.set(
                    "attribute_key",
                    keyInput
                        ? keyInput.value
                        : ""
                );

                formData.set(
                    "attribute_data_type",
                    dataTypeInput
                        ? dataTypeInput.value
                        : ""
                );

                formData.set(
                    "attribute_description",
                    descriptionInput
                        ? descriptionInput.value
                        : ""
                );

                formData.set(
                    "attribute_default_value",
                    defaultValueInput
                        ? defaultValueInput.value
                        : ""
                );

                formData.set(
                    "attribute_sort_order",
                    sortOrderInput
                        ? sortOrderInput.value
                        : "0"
                );

                if (requiredInput) {
                    formData.set(
                        "attribute_required",
                        requiredInput.checked
                            ? "on"
                            : ""
                    );
                }


                const response = await fetch(
                    updateUrl,
                    {
                        method: "POST",

                        headers: {
                            "X-CSRFToken":
                                csrfToken.value,

                            "Content-Type":
                                "application/x-www-form-urlencoded",

                            "X-Requested-With":
                                "XMLHttpRequest",
                        },

                        body: formData,
                    }
                );


                const data =
                    await response.json();


                if (!response.ok || !data.success) {

                    if (
                        errorElement
                        && data.errors
                    ) {

                        const messages =
                            Object.values(
                                data.errors
                            );

                        errorElement.textContent =
                            messages.join(" ");

                        errorElement.hidden = false;

                    } else if (errorElement) {

                        errorElement.textContent =
                            data.error
                            || "Unable to save attribute.";

                        errorElement.hidden = false;

                    }

                    return;
                }


                /*
                 * Keep the editor inputs aligned with the
                 * persisted proposal values.
                 */

                if (nameInput) {
                    nameInput.value =
                        data.values.name;
                }

                if (keyInput) {
                    keyInput.value =
                        data.values.key;
                }

                if (dataTypeInput) {
                    dataTypeInput.value =
                        data.values.data_type;
                }

                if (descriptionInput) {
                    dataTypeInput.value =
                        data.values.data_type;

                    descriptionInput.value =
                        data.values.description;
                }

                if (defaultValueInput) {
                    defaultValueInput.value =
                        data.values.default_value;
                }

                if (sortOrderInput) {
                    sortOrderInput.value =
                        data.values.sort_order;
                }

                if (requiredInput) {
                    requiredInput.checked =
                        data.values.required
                        === "true";
                }


                /*
                 * Update the visible attribute display.
                 */

                const nameDisplay =
                    attribute.querySelector(
                        ".model-object-type-attribute-name"
                    );

                const metaDisplay =
                    attribute.querySelector(
                        ".model-object-type-attribute-meta"
                    );

                const descriptionDisplay =
                    attribute.querySelector(
                        ".model-object-type-attribute-description"
                    );


                if (nameDisplay) {
                    nameDisplay.textContent =
                        data.values.name;
                }


                if (descriptionDisplay) {

                    if (
                        data.values.description
                    ) {

                        descriptionDisplay.textContent =
                            data.values.description;

                        descriptionDisplay.hidden =
                            false;

                    } else {

                        descriptionDisplay.textContent =
                            "";

                        descriptionDisplay.hidden =
                            true;
                    }

                }


                if (metaDisplay) {

                    const spans =
                        metaDisplay.querySelectorAll(
                            "span"
                        );

                    if (spans.length >= 3) {

                        spans[0].textContent =
                            data.values.key;

                        spans[1].textContent =
                            data.values.data_type;

                        spans[2].textContent =
                            data.values.required
                            === "true"
                                ? "Required"
                                : "Optional";

                    }

                }


                /*
                 * Close editor.
                 */

                editor.hidden = true;

                const display =
                    attribute.querySelector(
                        ".model-object-type-attribute-display"
                    );

                if (display) {
                    display.hidden = false;
                }


                /*
                 * This attribute now has proposal changes.
                 */

                attribute.dataset.proposed = "true";

            } catch (error) {

                console.error(
                    "Attribute save failed:",
                    error
                );

                if (errorElement) {
                    errorElement.textContent =
                        "Unable to save attribute.";

                    errorElement.hidden = false;
                }

            } finally {

                button.disabled = false;

            }

        }
    );

});