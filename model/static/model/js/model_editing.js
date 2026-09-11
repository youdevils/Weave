
document.addEventListener("DOMContentLoaded", function () {

    /*
     * ============================================================
     * Generic proposal editor
     * ============================================================
     *
     * Shared by:
     *
     *   Model
     *   ObjectType
     *   Object
     *   Relationship
     *   etc.
     *
     * Server contract:
     *
     *   Save:
     *       POST field + value
     *
     *   Discard:
     *       POST field + action=discard
     *
     * Canonical state is never modified by this client code.
     * ============================================================
     */

    const proposalEditors =
        document.querySelectorAll(
            ".proposal-editor"
        );

    proposalEditors.forEach(
        function (editorRoot) {

            const updateUrl =
                editorRoot.dataset.updateUrl;

            if (!updateUrl) {
                console.error(
                    "Proposal editor: update URL is missing."
                );
                return;
            }

            const csrfToken =
                editorRoot.querySelector(
                    "[name=csrfmiddlewaretoken]"
                )
                || document.querySelector(
                    "[name=csrfmiddlewaretoken]"
                );

            if (!csrfToken) {
                console.error(
                    "Proposal editor: CSRF token is missing."
                );
                return;
            }

            /*
             * --------------------------------------------------------
             * ObjectType field actions
             * --------------------------------------------------------
             */

            editorRoot.addEventListener(
                "click",
                function (event) {

                    const editButton =
                        event.target.closest(
                            '[data-proposal-action="edit"]'
                        );

                    if (editButton) {

                        const field =
                            getFieldContainer(
                                editButton
                            );

                        if (field) {
                            openField(field);
                        }

                        return;
                    }


                    const cancelButton =
                        event.target.closest(
                            '[data-proposal-action="cancel"]'
                        );

                    if (cancelButton) {

                        const field =
                            getFieldContainer(
                                cancelButton
                            );

                        if (field) {
                            cancelField(field);
                        }

                        return;
                    }


                    const saveButton =
                        event.target.closest(
                            '[data-proposal-action="save"]'
                        );

                    if (saveButton) {

                        const field =
                            getFieldContainer(
                                saveButton
                            );

                        if (field) {

                            saveField(
                                editorRoot,
                                csrfToken,
                                field,
                                saveButton
                            );
                        }

                        return;
                    }


                    const discardButton =
                        event.target.closest(
                            '[data-proposal-action="discard"]'
                        );

                    if (discardButton) {

                        const field =
                            getFieldContainer(
                                discardButton
                            );

                        if (field) {

                            discardField(
                                editorRoot,
                                csrfToken,
                                field,
                                discardButton
                            );
                        }
                    }

                }
            );


            /*
             * --------------------------------------------------------
             * Escape closes an ObjectType field editor.
             * --------------------------------------------------------
             */

            editorRoot.addEventListener(
                "keydown",
                function (event) {

                    if (event.key !== "Escape") {
                        return;
                    }

                    const editor =
                        event.target.closest(
                            "[data-field-editor]"
                        );

                    if (!editor) {
                        return;
                    }

                    const field =
                        editor.closest(
                            ".proposal-editor-field"
                        );

                    if (!field) {
                        return;
                    }

                    cancelField(field);

                }
            );


            /*
             * --------------------------------------------------------
             * Attribute actions
             * --------------------------------------------------------
             *
             * Delegated from proposal-editor so dynamically-added
             * proposed attributes work automatically.
             */

            editorRoot.addEventListener(
                "click",
                function (event) {

                    const editButton =
                        event.target.closest(
                            "[data-edit-attribute]"
                        );

                    if (editButton) {

                        openAttribute(
                            editButton.closest(
                                ".model-object-type-attribute"
                            )
                        );

                        return;
                    }


                    const cancelButton =
                        event.target.closest(
                            "[data-cancel-attribute]"
                        );

                    if (cancelButton) {

                        closeAttribute(
                            cancelButton.closest(
                                ".model-object-type-attribute"
                            )
                        );

                        return;
                    }


                    const saveButton =
                        event.target.closest(
                            "[data-save-attribute]"
                        );

                    if (saveButton) {

                        saveAttribute(
                            editorRoot,
                            csrfToken,
                            saveButton
                        );

                        return;
                    }


                    const discardButton =
                        event.target.closest(
                            "[data-discard-attribute]"
                        );

                    if (discardButton) {

                        discardAttribute(
                            editorRoot,
                            csrfToken,
                            discardButton
                        );

                        return;
                    }


                    const addButton =
                        event.target.closest(
                            "[data-add-attribute]"
                        );

                    if (addButton) {

                        openNewAttribute(
                            editorRoot
                        );

                        return;
                    }


                    const cancelNewButton =
                        event.target.closest(
                            "[data-cancel-new-attribute]"
                        );

                    if (cancelNewButton) {

                        closeNewAttribute(
                            editorRoot
                        );

                        return;
                    }


                    const saveNewButton =
                        event.target.closest(
                            "[data-save-new-attribute]"
                        );

                    if (saveNewButton) {

                        saveNewAttribute(
                            editorRoot,
                            csrfToken,
                            saveNewButton
                        );

                    }

                }
            );

        }
    );


    /*
     * ============================================================
     * ObjectType field helpers
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

        const fieldName =
            getFieldName(field);

        if (!fieldName) {
            return null;
        }

        return field.querySelector(
            `[data-field-display="${CSS.escape(fieldName)}"]`
        );

    }


    function getEditor(field) {

        const fieldName =
            getFieldName(field);

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


    function getInput(editor) {

        return editor.querySelector(
            "input:not([type=hidden]):not([type=submit]), " +
            "textarea, " +
            "select"
        );

    }


    function getProposalIndicator(field) {

        return field.querySelector(
            "[data-proposal-indicator]"
        );

    }


    function getDiscardButton(field) {

        return field.querySelector(
            '[data-proposal-action="discard"]'
        );

    }


    function openField(field) {

        const display =
            getDisplay(field);

        const editor =
            getEditor(field);

        const editButton =
            getEditButton(field);

        if (!display || !editor) {
            return;
        }

        const input =
            getInput(editor);

        if (!input) {
            return;
        }

        const root =
            field.closest(
                ".proposal-editor"
            );

        if (root) {
            closeOtherFields(
                root,
                field
            );
        }

        display.hidden = true;
        editor.hidden = false;

        if (editButton) {
            editButton.hidden = true;
        }

        input.focus();

    }


    function closeOtherFields(
        root,
        currentField
    ) {

        root.querySelectorAll(
            ".proposal-editor-field"
        ).forEach(
            function (field) {

                if (field === currentField) {
                    return;
                }

                const editor =
                    getEditor(field);

                const display =
                    getDisplay(field);

                if (!editor || !display) {
                    return;
                }

                editor.hidden = true;
                display.hidden = false;

                const editButton =
                    getEditButton(field);

                if (editButton) {
                    editButton.hidden = false;
                }

            }
        );

    }


    function cancelField(field) {

        const display =
            getDisplay(field);

        const editor =
            getEditor(field);

        const editButton =
            getEditButton(field);

        if (!display || !editor) {
            return;
        }

        editor.hidden = true;
        display.hidden = false;

        if (editButton) {
            editButton.hidden = false;
        }

    }


    async function saveField(
        root,
        csrfToken,
        field,
        button
    ) {

        const fieldName =
            getFieldName(field);

        if (!fieldName) {
            return;
        }

        const display =
            getDisplay(field);

        const editor =
            getEditor(field);

        if (!display || !editor) {
            return;
        }

        const input =
            getInput(editor);

        if (!input) {
            return;
        }

        const value =
            readInputValue(input);

        clearError(field);

        button.disabled = true;

        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        field: fieldName,
                        value: value
                    }
                );

            writeInputValue(
                input,
                data.value
            );

            renderDisplayValue(
                display,
                data.value,
                input
            );

            editor.hidden = true;
            display.hidden = false;

            const editButton =
                getEditButton(field);

            if (editButton) {
                editButton.hidden = false;
            }

            const indicator =
                getProposalIndicator(field);

            const discardButton =
                getDiscardButton(field);

            if (data.proposed) {

                if (indicator) {
                    indicator.hidden = false;
                }

                if (discardButton) {
                    discardButton.hidden = false;
                }

            } else {

                if (indicator) {
                    indicator.hidden = true;
                }

                if (discardButton) {
                    discardButton.hidden = true;
                }

            }

        } catch (error) {

            showError(
                field,
                error.message
            );

        } finally {

            button.disabled = false;

        }

    }


    async function discardField(
        root,
        csrfToken,
        field,
        button
    ) {

        const fieldName =
            getFieldName(field);

        if (!fieldName) {
            return;
        }

        const display =
            getDisplay(field);

        const editor =
            getEditor(field);

        const input =
            editor
                ? getInput(editor)
                : null;

        button.disabled = true;

        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        field: fieldName,
                        action: "discard"
                    }
                );

            if (input) {
                writeInputValue(
                    input,
                    data.value
                );
            }

            if (display) {
                renderDisplayValue(
                    display,
                    data.value,
                    input
                );
            }

            if (editor) {
                editor.hidden = true;
            }

            if (display) {
                display.hidden = false;
            }

            const editButton =
                getEditButton(field);

            if (editButton) {
                editButton.hidden = false;
            }

            const indicator =
                getProposalIndicator(field);

            if (indicator) {
                indicator.hidden = true;
            }

            button.hidden = true;

        } catch (error) {

            showError(
                field,
                error.message
            );

        } finally {

            button.disabled = false;

        }

    }


    function readInputValue(input) {

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {
            return input.checked
                ? "true"
                : "false";
        }

        return input.value;

    }


    function writeInputValue(
        input,
        value
    ) {

        if (!input) {
            return;
        }

        const stringValue =
            normaliseValue(value);

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {

            input.checked =
                stringValue === "true"
                || stringValue === "1"
                || stringValue === "yes"
                || stringValue === "on";

            return;
        }

        input.value =
            stringValue;

    }


    function renderDisplayValue(
        display,
        value,
        input
    ) {

        if (!display) {
            return;
        }

        const stringValue =
            normaliseValue(value);

        display.replaceChildren();

        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {

            display.textContent =
                input.checked
                    ? "Active"
                    : "Inactive";

            return;
        }

        if (
            !stringValue.trim()
        ) {

            const empty =
                document.createElement(
                    "span"
                );

            empty.className =
                "model-field-empty";

            empty.textContent =
                "Not defined";

            display.appendChild(
                empty
            );

            return;
        }

        display.textContent =
            stringValue;

    }


    /*
     * ============================================================
     * Attribute editors
     * ============================================================
     */


    function openAttribute(attribute) {

        if (!attribute) {
            return;
        }

        const display =
            attribute.querySelector(
                "[data-attribute-display]"
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
                "input:not([type=hidden]), textarea, select"
            );

        if (input) {
            input.focus();
        }

    }


    function closeAttribute(attribute) {

        if (!attribute) {
            return;
        }

        const display =
            attribute.querySelector(
                "[data-attribute-display]"
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


    async function saveAttribute(
        root,
        csrfToken,
        button
    ) {

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

        const errorElement =
            attribute.querySelector(
                "[data-attribute-error]"
            );

        if (!editor) {
            return;
        }

        clearAttributeError(
            errorElement
        );

        button.disabled = true;

        try {

            const form =
                collectAttributeForm(
                    editor
                );

            form.action =
                "save_attribute";

            form.attribute_id =
                attributeId;

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    form
                );

            applyAttributeValues(
                attribute,
                data.values
            );

            setAttributeProposedState(
                attribute,
                data.proposed_fields
            );

            closeAttribute(
                attribute
            );

        } catch (error) {

            showAttributeError(
                errorElement,
                error
            );

        } finally {

            button.disabled = false;

        }

    }


    async function discardAttribute(
        root,
        csrfToken,
        button
    ) {

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

        button.disabled = true;

        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        action:
                            "discard_attribute",

                        attribute_id:
                            attributeId
                    }
                );

            if (data.removed) {

                attribute.remove();

                updateAttributeEmptyState(
                    root
                );

                return;
            }

            applyAttributeValues(
                attribute,
                data.values
            );

            setAttributeProposedState(
                attribute,
                null
            );

            closeAttribute(
                attribute
            );

        } catch (error) {

            const errorElement =
                attribute.querySelector(
                    "[data-attribute-error]"
                );

            showAttributeError(
                errorElement,
                error
            );

        } finally {

            button.disabled = false;

        }

    }


    function collectAttributeForm(
        editor
    ) {

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

        return {
            attribute_name:
                nameInput
                    ? nameInput.value
                    : "",

            attribute_key:
                keyInput
                    ? keyInput.value
                    : "",

            attribute_data_type:
                dataTypeInput
                    ? dataTypeInput.value
                    : "text",

            attribute_description:
                descriptionInput
                    ? descriptionInput.value
                    : "",

            attribute_default_value:
                defaultValueInput
                    ? defaultValueInput.value
                    : "",

            attribute_sort_order:
                sortOrderInput
                    ? sortOrderInput.value
                    : "0",

            attribute_required:
                requiredInput
                    && requiredInput.checked
                    ? "on"
                    : ""
        };

    }


    function applyAttributeValues(
        attribute,
        values
    ) {

        const nameInput =
            attribute.querySelector(
                '[name="attribute_name"]'
            );

        const keyInput =
            attribute.querySelector(
                '[name="attribute_key"]'
            );

        const dataTypeInput =
            attribute.querySelector(
                '[name="attribute_data_type"]'
            );

        const descriptionInput =
            attribute.querySelector(
                '[name="attribute_description"]'
            );

        const defaultValueInput =
            attribute.querySelector(
                '[name="attribute_default_value"]'
            );

        const sortOrderInput =
            attribute.querySelector(
                '[name="attribute_sort_order"]'
            );

        const requiredInput =
            attribute.querySelector(
                '[name="attribute_required"]'
            );


        writeInputValue(
            nameInput,
            values.name
        );

        writeInputValue(
            keyInput,
            values.key
        );

        writeInputValue(
            dataTypeInput,
            values.data_type
        );

        writeInputValue(
            descriptionInput,
            values.description
        );

        writeInputValue(
            defaultValueInput,
            values.default_value
        );

        writeInputValue(
            sortOrderInput,
            values.sort_order
        );

        if (requiredInput) {
            requiredInput.checked =
                values.required === "true";
        }


        const nameDisplay =
            attribute.querySelector(
                ".model-object-type-attribute-name"
            );

        const keyDisplay =
            attribute.querySelector(
                "[data-attribute-key]"
            );

        const typeDisplay =
            attribute.querySelector(
                "[data-attribute-data-type]"
            );

        const requiredDisplay =
            attribute.querySelector(
                "[data-attribute-required]"
            );

        const descriptionDisplay =
            attribute.querySelector(
                "[data-attribute-description]"
            );


        if (nameDisplay) {
            nameDisplay.textContent =
                values.name || "Not defined";
        }

        if (keyDisplay) {
            keyDisplay.textContent =
                values.key || "";
        }

        if (typeDisplay) {
            typeDisplay.textContent =
                formatDataType(
                    values.data_type
                );
        }

        if (requiredDisplay) {
            requiredDisplay.textContent =
                values.required === "true"
                    ? "Required"
                    : "Optional";
        }

        if (descriptionDisplay) {

            if (values.description) {
                descriptionDisplay.textContent =
                    values.description;

                descriptionDisplay.hidden =
                    false;

            } else {

                descriptionDisplay.textContent =
                    "";

                descriptionDisplay.hidden =
                    true;
            }

        }

    }


    function setAttributeProposedState(
        attribute,
        proposedFields
    ) {

        const proposed =
            proposedFields === null
                ? false
                : Object.values(
                    proposedFields
                ).some(
                    Boolean
                );

        attribute.dataset.attributeProposed =
            proposed
                ? "true"
                : "false";

        const indicator =
            attribute.querySelector(
                "[data-attribute-proposal-indicator]"
            );

        if (indicator) {
            indicator.hidden =
                !proposed;
        }

        let discardButton =
            attribute.querySelector(
                "[data-discard-attribute]"
            );

        if (proposed && !discardButton) {

            discardButton =
                document.createElement(
                    "button"
                );

            discardButton.type =
                "button";

            discardButton.className =
                "btn btn-sm btn-outline-secondary";

            discardButton.dataset
                .discardAttribute =
                "";

            discardButton.textContent =
                "Discard";

            const actions =
                attribute.querySelector(
                    ".model-object-type-attribute-actions"
                );

            if (actions) {
                actions.appendChild(
                    discardButton
                );
            }

        }

        if (discardButton) {
            discardButton.hidden =
                !proposed;
        }

    }


    function formatDataType(
        value
    ) {

        if (value === "text") {
            return "Text";
        }

        if (value === "number") {
            return "Number";
        }

        return value || "";

    }


    /*
     * ============================================================
     * New attribute creation
     * ============================================================
     */


    function openNewAttribute(
        root
    ) {

        const editor =
            root.querySelector(
                "[data-new-attribute-editor]"
            );

        if (!editor) {
            return;
        }

        editor.hidden = false;

        const nameInput =
            editor.querySelector(
                '[name="attribute_name"]'
            );

        if (nameInput) {
            nameInput.focus();
        }

    }


    function closeNewAttribute(
        root
    ) {

        const editor =
            root.querySelector(
                "[data-new-attribute-editor]"
            );

        if (!editor) {
            return;
        }

        editor.hidden = true;

        clearNewAttributeForm(
            editor
        );

    }


    async function saveNewAttribute(
        root,
        csrfToken,
        button
    ) {

        const editor =
            root.querySelector(
                "[data-new-attribute-editor]"
            );

        if (!editor) {
            return;
        }

        const errorElement =
            editor.querySelector(
                "[data-new-attribute-error]"
            );

        if (errorElement) {
            errorElement.hidden = true;
            errorElement.textContent = "";
        }

        button.disabled = true;

        try {

            const form =
                collectAttributeForm(
                    editor
                );

            form.action =
                "create_attribute";

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    form
                );

            const attribute =
                createAttributeElement(
                    data
                );

            const list =
                root.querySelector(
                    "[data-attribute-list]"
                );

            const emptyState =
                root.querySelector(
                    "[data-attribute-empty]"
                );

            const newEditor =
                root.querySelector(
                    "[data-new-attribute-editor]"
                );


            if (emptyState) {
                emptyState.remove();
            }


            if (newEditor) {

                list.insertBefore(
                    attribute,
                    newEditor
                );

            } else {

                list.appendChild(
                    attribute
                );

            }


            closeNewAttribute(
                root
            );

        } catch (error) {

            showAttributeError(
                errorElement,
                error
            );

        } finally {

            button.disabled = false;

        }

    }


    function createAttributeElement(
        data
    ) {

        const article =
            document.createElement(
                "article"
            );

        article.className =
            "model-object-type-attribute";

        article.dataset.attributeId =
            data.attribute_id;

        article.dataset.attributeCreated =
            "true";

        article.dataset.attributeProposed =
            "true";


        article.innerHTML = `
            <div
                class="model-object-type-attribute-display"
                data-attribute-display
            >

                <div class="model-object-type-attribute-main">

                    <h3
                        class="model-object-type-attribute-name"
                    ></h3>

                    <div class="model-object-type-attribute-meta">

                        <span data-attribute-key></span>

                        <span data-attribute-data-type></span>

                        <span data-attribute-required></span>

                    </div>

                    <div
                        class="model-object-type-attribute-description"
                        data-attribute-description
                    ></div>

                </div>

                <div
                    class="model-object-type-attribute-actions"
                >

                    <button
                        type="button"
                        class="btn btn-sm btn-outline-secondary"
                        data-edit-attribute
                    >
                        Edit
                    </button>

                    <button
                        type="button"
                        class="btn btn-sm btn-outline-secondary"
                        data-discard-attribute
                    >
                        Discard
                    </button>

                </div>

            </div>


            <div
                class="model-proposed-indicator"
                data-attribute-proposal-indicator
            >
                <i class="bi bi-pencil-square"></i>
                Proposed change
            </div>


            <div
                class="model-object-type-attribute-editor"
                data-attribute-editor
                hidden
            >

                <div class="model-editor-fields">

                    <div class="model-editor-field">

                        <label>Name</label>

                        <input
                            type="text"
                            name="attribute_name"
                            class="form-control"
                            maxlength="100"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>Key</label>

                        <input
                            type="text"
                            name="attribute_key"
                            class="form-control"
                            maxlength="100"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>Data type</label>

                        <select
                            name="attribute_data_type"
                            class="form-select"
                        >

                            <option value="text">
                                Text
                            </option>

                            <option value="number">
                                Number
                            </option>

                        </select>

                    </div>


                    <div class="model-editor-field">

                        <label>Description</label>

                        <textarea
                            name="attribute_description"
                            class="form-control"
                            rows="3"
                        ></textarea>

                    </div>


                    <div class="model-editor-field">

                        <label>Default value</label>

                        <input
                            type="text"
                            name="attribute_default_value"
                            class="form-control"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>Sort order</label>

                        <input
                            type="number"
                            name="attribute_sort_order"
                            class="form-control"
                            value="0"
                            min="0"
                        >

                    </div>


                    <div class="model-editor-checkboxes">

                        <label class="form-check">

                            <input
                                type="checkbox"
                                name="attribute_required"
                                class="form-check-input"
                            >

                            <span class="form-check-label">
                                Required
                            </span>

                        </label>

                    </div>


                    <div
                        class="model-editor-field-error"
                        data-attribute-error
                        hidden
                    ></div>

                </div>


                <div class="model-editor-actions">

                    <button
                        type="button"
                        class="btn btn-sm btn-outline-secondary"
                        data-cancel-attribute
                    >
                        Cancel
                    </button>

                    <button
                        type="button"
                        class="btn btn-sm btn-primary"
                        data-save-attribute
                    >
                        Save attribute
                    </button>

                </div>

            </div>
        `;


        applyAttributeValues(
            article,
            data.values
        );

        return article;

    }


    function clearNewAttributeForm(
        editor
    ) {

        const inputs =
            editor.querySelectorAll(
                "input, textarea, select"
            );

        inputs.forEach(
            function (input) {

                if (
                    input.type === "checkbox"
                ) {

                    input.checked =
                        false;

                } else if (
                    input.name ===
                    "attribute_data_type"
                ) {

                    input.value =
                        "text";

                } else if (
                    input.name ===
                    "attribute_sort_order"
                ) {

                    input.value =
                        "0";

                } else {

                    input.value =
                        "";
                }

            }
        );

    }


    function updateAttributeEmptyState(
        root
    ) {

        const list =
            root.querySelector(
                "[data-attribute-list]"
            );

        if (!list) {
            return;
        }

        const attributes =
            list.querySelectorAll(
                ".model-object-type-attribute:not([data-new-attribute-editor])"
            );

        const existingEmpty =
            list.querySelector(
                "[data-attribute-empty]"
            );

        if (
            attributes.length === 0
            && !existingEmpty
        ) {

            const empty =
                document.createElement(
                    "div"
                );

            empty.className =
                "model-editor-empty";

            empty.dataset.attributeEmpty =
                "";

            empty.innerHTML = `
                <div class="model-editor-empty-icon">
                    <i class="bi bi-list-ul"></i>
                </div>

                <div>
                    <h3>No attributes yet</h3>
                    <p>
                        Add attributes to define the information
                        stored against objects of this type.
                    </p>
                </div>
            `;

            const newEditor =
                list.querySelector(
                    "[data-new-attribute-editor]"
                );

            if (newEditor) {
                list.insertBefore(
                    empty,
                    newEditor
                );
            } else {
                list.appendChild(
                    empty
                );
            }

        }

    }


    /*
     * ============================================================
     * Request helpers
     * ============================================================
     */


    async function post(
        url,
        csrfToken,
        values
    ) {

        return postForm(
            url,
            csrfToken,
            values
        );

    }


    async function postForm(
        url,
        csrfToken,
        values
    ) {

        const response =
            await fetch(
                url,
                {
                    method: "POST",

                    headers: {
                        "X-CSRFToken":
                            csrfToken,

                        "Content-Type":
                            "application/x-www-form-urlencoded",

                        "X-Requested-With":
                            "XMLHttpRequest"
                    },

                    body:
                        new URLSearchParams(
                            values
                        )
                }
            );


        const contentType =
            response.headers.get(
                "content-type"
            )
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


        let data;

        try {

            data =
                await response.json();

        } catch (error) {

            throw new Error(
                "The server returned invalid JSON."
            );

        }


        if (
            !response.ok
            || !data.success
        ) {

            const errorMessage =
                data.error
                || (
                    data.errors
                    ? Object.values(
                        data.errors
                    ).join(" ")
                    : null
                )
                || "Unable to save the proposed change.";

            throw new Error(
                errorMessage
            );

        }

        return data;

    }


    function showError(
        field,
        message
    ) {

        const element =
            field.querySelector(
                "[data-proposal-error]"
            );

        if (!element) {
            console.error(
                message
            );
            return;
        }

        element.textContent =
            message;

        element.hidden =
            false;

    }


    function clearError(
        field
    ) {

        const element =
            field.querySelector(
                "[data-proposal-error]"
            );

        if (!element) {
            return;
        }

        element.textContent =
            "";

        element.hidden =
            true;

    }


    function showAttributeError(
        element,
        error
    ) {

        if (!element) {
            console.error(
                error.message
            );
            return;
        }

        element.textContent =
            error.message;

        element.hidden =
            false;

    }


    function clearAttributeError(
        element
    ) {

        if (!element) {
            return;
        }

        element.textContent =
            "";

        element.hidden =
            true;

    }


    function normaliseValue(
        value
    ) {

        if (
            value === null
            || value === undefined
        ) {
            return "";
        }

        return String(value);

    }

});

