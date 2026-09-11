
document.addEventListener("DOMContentLoaded", function () {

    /*
     * ============================================================
     * Weave proposal-aware editing
     * ============================================================
     *
     * Generic ObjectType / Model field editing
     * AttributeDefinition compound editing
     * Retire / Activate lifecycle proposals
     * Proposal discard
     *
     * Canonical model state is never modified by this JavaScript.
     * All persistence goes through the proposal endpoint supplied
     * by the page.
     * ============================================================
     */


    document.querySelectorAll(
        ".proposal-editor"
    ).forEach(function (root) {

        const updateUrl =
            root.dataset.updateUrl;

        if (!updateUrl) {
            console.error(
                "Proposal editor: update URL is missing."
            );
            return;
        }


        const csrfToken =
            root.querySelector(
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
         * ========================================================
         * Click delegation
         * ========================================================
         */

        root.addEventListener(
            "click",
            function (event) {


                /*
                 * ------------------------------------------------
                 * ObjectType field edit
                 * ------------------------------------------------
                 */

                const editButton =
                    event.target.closest(
                        '[data-proposal-action="edit"]'
                    );

                if (editButton) {

                    const field =
                        editButton.closest(
                            ".proposal-editor-field"
                        );

                    if (field) {
                        openField(field);
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * ObjectType field cancel
                 * ------------------------------------------------
                 */

                const cancelButton =
                    event.target.closest(
                        '[data-proposal-action="cancel"]'
                    );

                if (cancelButton) {

                    const field =
                        cancelButton.closest(
                            ".proposal-editor-field"
                        );

                    if (field) {
                        cancelField(field);
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * ObjectType field save
                 * ------------------------------------------------
                 */

                const saveButton =
                    event.target.closest(
                        '[data-proposal-action="save"]'
                    );

                if (saveButton) {

                    const field =
                        saveButton.closest(
                            ".proposal-editor-field"
                        );

                    if (field) {
                        saveField(
                            root,
                            csrfToken,
                            field,
                            saveButton
                        );
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * ObjectType field discard
                 * ------------------------------------------------
                 */

                const discardFieldButton =
                    event.target.closest(
                        '[data-proposal-action="discard"]'
                    );

                if (discardFieldButton) {

                    const field =
                        discardFieldButton.closest(
                            ".proposal-editor-field"
                        );

                    if (field) {
                        discardField(
                            root,
                            csrfToken,
                            field,
                            discardFieldButton
                        );
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * ObjectType Retire / Activate
                 * ------------------------------------------------
                 */

                const statusToggle =
                    event.target.closest(
                        "[data-status-toggle]"
                    );

                if (statusToggle) {

                    setObjectTypeStatus(
                        root,
                        csrfToken,
                        statusToggle
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * ObjectType lifecycle discard
                 * ------------------------------------------------
                 */

                const lifecycleDiscard =
                    event.target.closest(
                        "[data-lifecycle-discard]"
                    );

                if (lifecycleDiscard) {

                    discardObjectTypeStatus(
                        root,
                        csrfToken,
                        lifecycleDiscard
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Attribute edit
                 * ------------------------------------------------
                 */

                const attributeEdit =
                    event.target.closest(
                        "[data-edit-attribute]"
                    );

                if (attributeEdit) {

                    const attribute =
                        attributeEdit.closest(
                            ".model-object-type-attribute"
                        );

                    if (attribute) {
                        openAttribute(attribute);
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Attribute cancel
                 * ------------------------------------------------
                 */

                const attributeCancel =
                    event.target.closest(
                        "[data-cancel-attribute]"
                    );

                if (attributeCancel) {

                    const attribute =
                        attributeCancel.closest(
                            ".model-object-type-attribute"
                        );

                    if (attribute) {
                        closeAttribute(attribute);
                    }

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Attribute save
                 * ------------------------------------------------
                 */

                const attributeSave =
                    event.target.closest(
                        "[data-save-attribute]"
                    );

                if (attributeSave) {

                    saveAttribute(
                        root,
                        csrfToken,
                        attributeSave
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Attribute proposal discard
                 * ------------------------------------------------
                 */

                const attributeDiscard =
                    event.target.closest(
                        "[data-discard-attribute]"
                    );

                if (attributeDiscard) {

                    discardAttribute(
                        root,
                        csrfToken,
                        attributeDiscard
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Attribute Retire / Activate
                 * ------------------------------------------------
                 */

                const attributeStatus =
                    event.target.closest(
                        "[data-attribute-status-toggle]"
                    );

                if (attributeStatus) {

                    setAttributeStatus(
                        root,
                        csrfToken,
                        attributeStatus
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Add attribute
                 * ------------------------------------------------
                 */

                const addAttribute =
                    event.target.closest(
                        "[data-add-attribute]"
                    );

                if (addAttribute) {

                    openNewAttribute(
                        root
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Cancel new attribute
                 * ------------------------------------------------
                 */

                const cancelNewAttribute =
                    event.target.closest(
                        "[data-cancel-new-attribute]"
                    );

                if (cancelNewAttribute) {

                    closeNewAttribute(
                        root
                    );

                    return;
                }


                /*
                 * ------------------------------------------------
                 * Save new attribute
                 * ------------------------------------------------
                 */

                const saveNewAttributeButton =
                    event.target.closest(
                        "[data-save-new-attribute]"
                    );

                if (saveNewAttributeButton) {

                    saveNewAttribute(
                        root,
                        csrfToken,
                        saveNewAttributeButton
                    );

                }

            }
        );


        /*
         * ========================================================
         * Escape
         * ========================================================
         */

        root.addEventListener(
            "keydown",
            function (event) {

                if (event.key !== "Escape") {
                    return;
                }


                const fieldEditor =
                    event.target.closest(
                        "[data-field-editor]"
                    );

                if (fieldEditor) {

                    const field =
                        fieldEditor.closest(
                            ".proposal-editor-field"
                        );

                    if (field) {
                        cancelField(field);
                    }

                    return;
                }


                const attributeEditor =
                    event.target.closest(
                        "[data-attribute-editor]"
                    );

                if (attributeEditor) {

                    const attribute =
                        attributeEditor.closest(
                            ".model-object-type-attribute"
                        );

                    if (attribute) {
                        closeAttribute(attribute);
                    }

                }

            }
        );

    });


    /*
     * ============================================================
     * Generic ObjectType fields
     * ============================================================
     */

    function getFieldInput(field) {

        const editor =
            field.querySelector(
                "[data-field-editor]"
            );

        if (!editor) {
            return null;
        }

        return editor.querySelector(
            "input:not([type=hidden]), textarea, select"
        );
    }


    function openField(field) {

        const display =
            field.querySelector(
                "[data-field-display]"
            );

        const editor =
            field.querySelector(
                "[data-field-editor]"
            );

        const editButton =
            field.querySelector(
                '[data-proposal-action="edit"]'
            );

        if (!display || !editor) {
            return;
        }

        const root =
            field.closest(
                ".proposal-editor"
            );

        if (root) {

            root.querySelectorAll(
                ".proposal-editor-field"
            ).forEach(function (other) {

                if (other === field) {
                    return;
                }

                const otherDisplay =
                    other.querySelector(
                        "[data-field-display]"
                    );

                const otherEditor =
                    other.querySelector(
                        "[data-field-editor]"
                    );

                const otherEditButton =
                    other.querySelector(
                        '[data-proposal-action="edit"]'
                    );

                if (
                    otherDisplay
                    && otherEditor
                ) {

                    otherDisplay.hidden =
                        false;

                    otherEditor.hidden =
                        true;

                    if (otherEditButton) {
                        otherEditButton.hidden =
                            false;
                    }

                }

            });

        }


        display.hidden =
            true;

        editor.hidden =
            false;

        if (editButton) {
            editButton.hidden =
                true;
        }


        const input =
            getFieldInput(field);

        if (input) {
            input.focus();
        }

    }


    function cancelField(field) {

        const display =
            field.querySelector(
                "[data-field-display]"
            );

        const editor =
            field.querySelector(
                "[data-field-editor]"
            );

        const editButton =
            field.querySelector(
                '[data-proposal-action="edit"]'
            );

        if (!display || !editor) {
            return;
        }

        editor.hidden =
            true;

        display.hidden =
            false;

        if (editButton) {
            editButton.hidden =
                false;
        }

        clearFieldError(field);

    }


    async function saveField(
        root,
        csrfToken,
        field,
        button
    ) {

        const fieldName =
            field.dataset.field;

        const input =
            getFieldInput(field);

        if (
            !fieldName
            || !input
        ) {
            return;
        }


        clearFieldError(field);

        button.disabled =
            true;


        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        field:
                            fieldName,

                        value:
                            readInputValue(input)
                    }
                );


            writeInputValue(
                input,
                data.value
            );


            updateFieldDisplay(
                field,
                data.value,
                input
            );


            const display =
                field.querySelector(
                    "[data-field-display]"
                );

            const editor =
                field.querySelector(
                    "[data-field-editor]"
                );

            const editButton =
                field.querySelector(
                    '[data-proposal-action="edit"]'
                );

            const indicator =
                field.querySelector(
                    "[data-proposal-indicator]"
                );

            const discard =
                field.querySelector(
                    '[data-proposal-action="discard"]'
                );


            if (editor) {
                editor.hidden =
                    true;
            }

            if (display) {
                display.hidden =
                    false;
            }

            if (editButton) {
                editButton.hidden =
                    false;
            }


            if (data.proposed) {

                if (indicator) {
                    indicator.hidden =
                        false;
                }

                if (discard) {
                    discard.hidden =
                        false;
                }

            } else {

                if (indicator) {
                    indicator.hidden =
                        true;
                }

                if (discard) {
                    discard.hidden =
                        true;
                }

            }

        } catch (error) {

            showFieldError(
                field,
                error.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    async function discardField(
        root,
        csrfToken,
        field,
        button
    ) {

        const fieldName =
            field.dataset.field;

        if (!fieldName) {
            return;
        }

        button.disabled =
            true;

        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        field:
                            fieldName,

                        action:
                            "discard"
                    }
                );


            const input =
                getFieldInput(field);

            if (input) {

                writeInputValue(
                    input,
                    data.value
                );

            }


            updateFieldDisplay(
                field,
                data.value,
                input
            );


            cancelField(
                field
            );


            const indicator =
                field.querySelector(
                    "[data-proposal-indicator]"
                );

            const discard =
                field.querySelector(
                    '[data-proposal-action="discard"]'
                );


            if (indicator) {
                indicator.hidden =
                    true;
            }

            if (discard) {
                discard.hidden =
                    true;
            }

        } catch (error) {

            showFieldError(
                field,
                error.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function updateFieldDisplay(
        field,
        value,
        input
    ) {

        const display =
            field.querySelector(
                "[data-field-display]"
            );

        if (!display) {
            return;
        }


        display.replaceChildren();


        const text =
            normaliseValue(value);


        if (!text.trim()) {

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
            text;

    }


    function readInputValue(
        input
    ) {

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


        const normalised =
            normaliseValue(value);


        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {

            input.checked =
                normalised === "true"
                || normalised === "1"
                || normalised === "yes"
                || normalised === "on";

            return;
        }


        input.value =
            normalised;

    }


    /*
     * ============================================================
     * ObjectType lifecycle
     * ============================================================
     */

    async function setObjectTypeStatus(
        root,
        csrfToken,
        button
    ) {

        const control =
            root.querySelector(
                "[data-object-type-lifecycle]"
            );

        if (!control) {
            return;
        }


        const currentActive =
            control.dataset.active ===
            "true";


        const desiredActive =
            !currentActive;


        button.disabled =
            true;


        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        action:
                            "set_object_type_status",

                        is_active:
                            desiredActive
                                ? "true"
                                : "false"
                    }
                );


            updateObjectTypeStatusUI(
                root,
                data.value,
                data.proposed
            );

        } catch (error) {

            console.error(
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    async function discardObjectTypeStatus(
        root,
        csrfToken,
        button
    ) {

        button.disabled =
            true;


        try {

            const data =
                await post(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        action:
                            "discard_object_type_status"
                    }
                );


            updateObjectTypeStatusUI(
                root,
                data.value,
                false
            );

        } catch (error) {

            console.error(
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function updateObjectTypeStatusUI(
        root,
        value,
        proposed
    ) {

        const active =
            normaliseValue(
                value
            ) === "true";


        const control =
            root.querySelector(
                "[data-object-type-lifecycle]"
            );

        const status =
            root.querySelector(
                "[data-status-display]"
            );

        const toggle =
            root.querySelector(
                "[data-status-toggle]"
            );

        const indicator =
            root.querySelector(
                "[data-lifecycle-proposal-indicator]"
            );

        const discard =
            root.querySelector(
                "[data-lifecycle-discard]"
            );


        if (control) {

            control.dataset.active =
                active
                    ? "true"
                    : "false";

            control.dataset.proposed =
                proposed
                    ? "true"
                    : "false";

        }


        if (status) {

            status.className =
                "model-status-pill "
                + (
                    active
                        ? "model-status-active"
                        : "model-status-retired"
                );


            status.replaceChildren();


            const icon =
                document.createElement(
                    "i"
                );

            icon.className =
                active
                    ? "bi bi-check-circle"
                    : "bi bi-archive";


            status.appendChild(
                icon
            );


            status.appendChild(
                document.createTextNode(
                    active
                        ? " Active"
                        : " Retired"
                )
            );

        }


        if (toggle) {

            toggle.textContent =
                active
                    ? "Retire"
                    : "Activate";

        }


        if (indicator) {
            indicator.hidden =
                !proposed;
        }

        if (discard) {
            discard.hidden =
                !proposed;
        }

    }


    /*
     * ============================================================
     * Attribute editor
     * ============================================================
     */

    function openAttribute(
        attribute
    ) {

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

        display.hidden =
            true;

        editor.hidden =
            false;


        const input =
            editor.querySelector(
                "input:not([type=hidden]), textarea, select"
            );

        if (input) {
            input.focus();
        }

    }


    function closeAttribute(
        attribute
    ) {

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

        editor.hidden =
            true;

        display.hidden =
            false;

        clearAttributeError(
            attribute
        );

    }


    function collectAttributeForm(
        editor
    ) {

        const name =
            editor.querySelector(
                '[name="attribute_name"]'
            );

        const key =
            editor.querySelector(
                '[name="attribute_key"]'
            );

        const dataType =
            editor.querySelector(
                '[name="attribute_data_type"]'
            );

        const description =
            editor.querySelector(
                '[name="attribute_description"]'
            );

        const defaultValue =
            editor.querySelector(
                '[name="attribute_default_value"]'
            );

        const sortOrder =
            editor.querySelector(
                '[name="attribute_sort_order"]'
            );

        const required =
            editor.querySelector(
                '[name="attribute_required"]'
            );

        const nullable =
            editor.querySelector(
                '[name="attribute_nullable"]'
            );


        return {

            action:
                "save_attribute",

            attribute_name:
                name
                    ? name.value
                    : "",

            attribute_key:
                key
                    ? key.value
                    : "",

            attribute_data_type:
                dataType
                    ? dataType.value
                    : "text",

            attribute_description:
                description
                    ? description.value
                    : "",

            attribute_default_value:
                defaultValue
                    ? defaultValue.value
                    : "",

            attribute_sort_order:
                sortOrder
                    ? sortOrder.value
                    : "0",

            attribute_required:
                required
                && required.checked
                    ? "on"
                    : "",

            attribute_nullable:
                nullable
                && nullable.checked
                    ? "on"
                    : ""
        };

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

        if (!editor) {
            return;
        }

        const error =
            attribute.querySelector(
                "[data-attribute-error]"
            );


        clearAttributeError(
            attribute
        );


        button.disabled =
            true;


        try {

            const values =
                collectAttributeForm(
                    editor
                );

            values.attribute_id =
                attributeId;


            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    values
                );


            applyAttributeValues(
                attribute,
                data.values
            );


            updateAttributeProposedState(
                attribute,
                data.proposed_fields,
                data.proposed
            );


            closeAttribute(
                attribute
            );


            /*
             * Newly-created proposed attributes
             * should no longer be treated as blank.
             */

            attribute.dataset.attributeCreated =
                data.created
                    ? "true"
                    : attribute.dataset.attributeCreated;

        } catch (errorValue) {

            showAttributeError(
                error,
                errorValue
            );

        } finally {

            button.disabled =
                false;

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


        button.disabled =
            true;


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


            updateAttributeProposedState(
                attribute,
                data.proposed_fields,
                false
            );


            closeAttribute(
                attribute
            );

        } catch (error) {

            showAttributeError(
                attribute.querySelector(
                    "[data-attribute-error]"
                ),
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    /*
     * ============================================================
     * Attribute lifecycle
     * ============================================================
     */

    async function setAttributeStatus(
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


        const current =
            (
                attribute.dataset
                    .attributeActive
                === "true"
            );


        /*
         * If the HTML did not provide the cached
         * value, derive it from the visible button.
         */

        const desired =
            !current;


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    {
                        action:
                            "set_attribute_status",

                        attribute_id:
                            attribute.dataset
                                .attributeId,

                        is_active:
                            desired
                                ? "true"
                                : "false"
                    }
                );


            updateAttributeStatusUI(
                attribute,
                data.value,
                data.proposed
            );


            updateAttributeProposedState(
                attribute,
                data.proposed_fields,
                data.proposed
            );

        } catch (error) {

            showAttributeError(
                attribute.querySelector(
                    "[data-attribute-error]"
                ),
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function updateAttributeStatusUI(
        attribute,
        value,
        proposed
    ) {

        const active =
            normaliseValue(
                value
            ) === "true";


        attribute.dataset
            .attributeActive =
            active
                ? "true"
                : "false";


        const button =
            attribute.querySelector(
                "[data-attribute-status-toggle]"
            );

        if (button) {

            button.textContent =
                active
                    ? "Retire"
                    : "Activate";

        }


        const editorStatus =
            attribute.querySelector(
                "[data-attribute-editor-status]"
            );

        if (editorStatus) {

            const pill =
                document.createElement(
                    "span"
                );

            pill.className =
                "model-status-pill "
                + (
                    active
                        ? "model-status-active"
                        : "model-status-retired"
                );


            const icon =
                document.createElement(
                    "i"
                );

            icon.className =
                active
                    ? "bi bi-check-circle"
                    : "bi bi-archive";


            pill.appendChild(
                icon
            );


            pill.appendChild(
                document.createTextNode(
                    active
                        ? " Active"
                        : " Retired"
                )
            );


            editorStatus.replaceChildren(
                pill
            );

        }


        const display =
            attribute.querySelector(
                "[data-attribute-display]"
            );

        if (display) {

            const status =
                display.querySelector(
                    "[data-attribute-status]"
                );

            if (status) {

                status.textContent =
                    active
                        ? "Active"
                        : "Retired";

            }

        }

    }


    /*
     * ============================================================
     * Attribute values
     * ============================================================
     */

    function applyAttributeValues(
        attribute,
        values
    ) {

        const name =
            attribute.querySelector(
                '[name="attribute_name"]'
            );

        const key =
            attribute.querySelector(
                '[name="attribute_key"]'
            );

        const dataType =
            attribute.querySelector(
                '[name="attribute_data_type"]'
            );

        const description =
            attribute.querySelector(
                '[name="attribute_description"]'
            );

        const defaultValue =
            attribute.querySelector(
                '[name="attribute_default_value"]'
            );

        const sortOrder =
            attribute.querySelector(
                '[name="attribute_sort_order"]'
            );

        const required =
            attribute.querySelector(
                '[name="attribute_required"]'
            );

        const nullable =
            attribute.querySelector(
                '[name="attribute_nullable"]'
            );

        const active =
            attribute.querySelector(
                '[name="attribute_is_active"]'
            );


        writeInputValue(
            name,
            values.name
        );

        writeInputValue(
            key,
            values.key
        );

        writeInputValue(
            dataType,
            values.data_type
        );

        writeInputValue(
            description,
            values.description
        );

        writeInputValue(
            defaultValue,
            values.default_value
        );

        writeInputValue(
            sortOrder,
            values.sort_order
        );


        if (required) {

            required.checked =
                values.required ===
                "true";

        }


        if (nullable) {

            nullable.checked =
                values.nullable ===
                "true";

        }


        if (active) {

            active.checked =
                values.is_active ===
                "true";

        }


        /*
         * Display values
         */

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

        const nullableDisplay =
            attribute.querySelector(
                "[data-attribute-nullable]"
            );

        const descriptionDisplay =
            attribute.querySelector(
                "[data-attribute-description]"
            );


        if (nameDisplay) {

            nameDisplay.textContent =
                values.name
                || "Not defined";

        }


        if (keyDisplay) {

            keyDisplay.textContent =
                values.key
                || "";

        }


        if (typeDisplay) {

            typeDisplay.textContent =
                formatDataType(
                    values.data_type
                );

        }


        if (requiredDisplay) {

            requiredDisplay.textContent =
                values.required ===
                "true"
                    ? "Required"
                    : "Optional";

        }


        if (nullableDisplay) {

            nullableDisplay.textContent =
                values.nullable ===
                "true"
                    ? "Nullable"
                    : "Not nullable";

        }


        if (descriptionDisplay) {

            if (values.description) {

                descriptionDisplay.textContent =
                    values.description;

                descriptionDisplay.hidden =
                    false;

            } else {

                descriptionDisplay
                    .textContent = "";

                descriptionDisplay.hidden =
                    true;

            }

        }


        /*
         * Sync lifecycle controls.
         */

        updateAttributeStatusUI(
            attribute,
            values.is_active,
            attribute.dataset
                .attributeProposed
                === "true"
        );

    }


    function updateAttributeProposedState(
        attribute,
        proposedFields,
        proposed
    ) {

        const isProposed =
            Boolean(
                proposed
                || (
                    proposedFields
                    && Object.values(
                        proposedFields
                    ).some(
                        Boolean
                    )
                )
            );


        attribute.dataset
            .attributeProposed =
            isProposed
                ? "true"
                : "false";


        const indicator =
            attribute.querySelector(
                "[data-attribute-proposal-indicator]"
            );

        if (indicator) {
            indicator.hidden =
                !isProposed;
        }


        let discard =
            attribute.querySelector(
                "[data-discard-attribute]"
            );


        if (
            isProposed
            && !discard
        ) {

            discard =
                document.createElement(
                    "button"
                );

            discard.type =
                "button";

            discard.className =
                "model-discard-button";

            discard.dataset
                .discardAttribute =
                "";

            discard.textContent =
                "Discard";


            const indicatorElement =
                attribute.querySelector(
                    "[data-attribute-proposal-indicator]"
                );


            if (indicatorElement) {

                indicatorElement.appendChild(
                    document.createTextNode(
                        " "
                    )
                );

                indicatorElement.appendChild(
                    discard
                );

            }

        }


        if (discard) {

            discard.hidden =
                !isProposed;

        }

    }


    function formatDataType(
        value
    ) {

        const labels = {
            text: "Text",
            number: "Number",
            boolean: "Boolean",
            date: "Date",
            datetime: "Date & time",
            choice: "Choice"
        };


        return labels[value]
            || value
            || "";

    }


    /*
     * ============================================================
     * New attribute
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

        editor.hidden =
            false;


        const input =
            editor.querySelector(
                '[name="attribute_name"]'
            );

        if (input) {
            input.focus();
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

        editor.hidden =
            true;


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


        const error =
            editor.querySelector(
                "[data-new-attribute-error]"
            );


        clearElementError(
            error
        );


        button.disabled =
            true;


        try {

            const values =
                collectAttributeForm(
                    editor
                );

            values.action =
                "create_attribute";


            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken.value,
                    values
                );


            const attribute =
                createAttributeElement(
                    data
                );


            const list =
                root.querySelector(
                    "[data-attribute-list]"
                );

            if (!list) {
                return;
            }


            const empty =
                root.querySelector(
                    "[data-attribute-empty]"
                );

            if (empty) {
                empty.remove();
            }


            const newEditor =
                root.querySelector(
                    "[data-new-attribute-editor]"
                );


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

        } catch (errorValue) {

            showAttributeError(
                error,
                errorValue
            );

        } finally {

            button.disabled =
                false;

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

        article.dataset.attributeActive =
            data.values.is_active ===
            "true"
                ? "true"
                : "false";


        article.innerHTML = `
            <div
                class="model-object-type-attribute-display"
                data-attribute-display
            >

                <div class="model-object-type-attribute-main">

                    <h3
                        class="model-object-type-attribute-name"
                    ></h3>

                    <div
                        class="model-object-type-attribute-meta"
                    >

                        <span data-attribute-key></span>

                        <span data-attribute-data-type></span>

                        <span data-attribute-required></span>

                        <span data-attribute-nullable></span>

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
                        data-attribute-status-toggle
                    >
                        Retire
                    </button>

                </div>

            </div>


            <div
                class="model-proposed-indicator"
                data-attribute-proposal-indicator
            >

                <i class="bi bi-pencil-square"></i>
                Proposed change

                <button
                    type="button"
                    class="model-discard-button"
                    data-discard-attribute
                >
                    Discard
                </button>

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

                            <option value="boolean">
                                Boolean
                            </option>

                            <option value="date">
                                Date
                            </option>

                            <option value="datetime">
                                Date & time
                            </option>

                            <option value="choice">
                                Choice
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
                            min="0"
                            value="0"
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


                        <label class="form-check">

                            <input
                                type="checkbox"
                                name="attribute_nullable"
                                class="form-check-input"
                            >

                            <span class="form-check-label">
                                Nullable
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

        editor.querySelectorAll(
            "input, textarea, select"
        ).forEach(
            function (input) {

                if (
                    input.type ===
                    "checkbox"
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
                ".model-object-type-attribute"
                + ":not([data-new-attribute-editor])"
            );


        const empty =
            list.querySelector(
                "[data-attribute-empty]"
            );


        if (
            attributes.length === 0
            && !empty
        ) {

            const element =
                document.createElement(
                    "div"
                );

            element.className =
                "model-editor-empty";

            element.dataset
                .attributeEmpty =
                "";


            element.innerHTML = `
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
                    element,
                    newEditor
                );

            } else {

                list.appendChild(
                    element
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
                    method:
                        "POST",

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

            let message =
                data.error;


            if (
                !message
                && data.errors
            ) {

                message =
                    Object.values(
                        data.errors
                    ).join(
                        " "
                    );

            }


            throw new Error(
                message
                || "Unable to save the proposed change."
            );

        }


        return data;

    }


    /*
     * ============================================================
     * Errors
     * ============================================================
     */

    function showFieldError(
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


    function clearFieldError(
        field
    ) {

        const element =
            field.querySelector(
                "[data-proposal-error]"
            );

        clearElementError(
            element
        );

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
        attribute
    ) {

        if (!attribute) {
            return;
        }


        clearElementError(
            attribute.querySelector(
                "[data-attribute-error]"
            )
        );

    }


    function clearElementError(
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

        return String(
            value
        );

    }

});

