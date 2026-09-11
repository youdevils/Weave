
document.addEventListener("DOMContentLoaded", function () {

    /*
     * ============================================================
     * Weave proposal-aware editing
     * ============================================================
     *
     * Supports:
     *
     *   - ObjectType field editing
     *   - ObjectType lifecycle
     *   - AttributeDefinition editing
     *   - AttributeDefinition lifecycle
     *   - AttributeDefinition creation
     *   - Proposal discard
     *   - ObjectType index proposal discard
     *
     * All persistence goes through proposal-aware Django views.
     * Canonical model records are never directly modified here.
     * ============================================================
     */


    /*
     * ============================================================
     * CSRF
     * ============================================================
     */

    function getCsrfToken() {

        const input =
            document.querySelector(
                '[name="csrfmiddlewaretoken"]'
            );

        if (
            input
            && input.value
        ) {
            return input.value;
        }


        const cookiePrefix =
            "csrftoken=";

        const cookies =
            document.cookie.split(";");


        for (
            let cookie of cookies
        ) {

            cookie =
                cookie.trim();


            if (
                cookie.indexOf(
                    cookiePrefix
                ) === 0
            ) {

                return decodeURIComponent(
                    cookie.substring(
                        cookiePrefix.length
                    )
                );

            }

        }


        return null;

    }


    /*
     * ============================================================
     * ObjectType index
     * ============================================================
     *
     * This exists outside .proposal-editor, so it gets its own
     * delegated click handler.
     * ============================================================
     */

    document.addEventListener(
        "click",
        function (event) {

            const discardButton =
                event.target.closest(
                    "[data-discard-object-type]"
                );

            if (!discardButton) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();

            discardObjectTypeProposal(
                discardButton
            );

        }
    );


    /*
     * ============================================================
     * Proposal editors
     * ============================================================
     */

    document.querySelectorAll(
        ".proposal-editor"
    ).forEach(
        function (root) {

            initialiseProposalEditor(
                root
            );

        }
    );


    /*
     * ============================================================
     * Initialise proposal editor
     * ============================================================
     */

    function initialiseProposalEditor(
        root
    ) {

        const updateUrl =
            root.dataset.updateUrl;

        if (!updateUrl) {

            console.error(
                "Proposal editor: data-update-url is missing."
            );

            return;

        }


        /*
         * --------------------------------------------------------
         * Delegated clicks
         * --------------------------------------------------------
         */

        root.addEventListener(
            "click",
            function (event) {

                /*
                 * Generic field edit
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
                        openField(
                            field
                        );
                    }

                    return;

                }


                /*
                 * Generic field cancel
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
                        cancelField(
                            field
                        );
                    }

                    return;

                }


                /*
                 * Generic field save
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
                            field,
                            saveButton
                        );

                    }

                    return;

                }


                /*
                 * Generic field discard
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
                            field,
                            discardFieldButton
                        );

                    }

                    return;

                }


                /*
                 * ObjectType lifecycle toggle
                 */

                const objectTypeStatusButton =
                    event.target.closest(
                        "[data-status-toggle]"
                    );

                if (objectTypeStatusButton) {

                    setObjectTypeStatus(
                        root,
                        objectTypeStatusButton
                    );

                    return;

                }


                /*
                 * ObjectType lifecycle proposal discard
                 */

                const objectTypeLifecycleDiscard =
                    event.target.closest(
                        "[data-lifecycle-discard]"
                    );

                if (objectTypeLifecycleDiscard) {

                    discardObjectTypeStatus(
                        root,
                        objectTypeLifecycleDiscard
                    );

                    return;

                }


                /*
                 * Attribute edit
                 */

                const attributeEditButton =
                    event.target.closest(
                        "[data-edit-attribute]"
                    );

                if (attributeEditButton) {

                    const attribute =
                        attributeEditButton.closest(
                            ".model-object-type-attribute"
                        );

                    if (attribute) {
                        openAttribute(
                            attribute
                        );
                    }

                    return;

                }


                /*
                 * Attribute cancel
                 */

                const attributeCancelButton =
                    event.target.closest(
                        "[data-cancel-attribute]"
                    );

                if (attributeCancelButton) {

                    const attribute =
                        attributeCancelButton.closest(
                            ".model-object-type-attribute"
                        );

                    if (attribute) {
                        closeAttribute(
                            attribute
                        );
                    }

                    return;

                }


                /*
                 * Attribute save
                 */

                const attributeSaveButton =
                    event.target.closest(
                        "[data-save-attribute]"
                    );

                if (attributeSaveButton) {

                    saveAttribute(
                        root,
                        attributeSaveButton
                    );

                    return;

                }


                /*
                 * Attribute proposal discard
                 */

                const attributeDiscardButton =
                    event.target.closest(
                        "[data-discard-attribute]"
                    );

                if (attributeDiscardButton) {

                    discardAttribute(
                        root,
                        attributeDiscardButton
                    );

                    return;

                }


                /*
                 * Attribute lifecycle
                 */

                const attributeStatusButton =
                    event.target.closest(
                        "[data-attribute-status-toggle]"
                    );

                if (attributeStatusButton) {

                    setAttributeStatus(
                        root,
                        attributeStatusButton
                    );

                    return;

                }


                /*
                 * New attribute editor
                 */

                const addAttributeButton =
                    event.target.closest(
                        "[data-add-attribute]"
                    );

                if (addAttributeButton) {

                    openNewAttribute(
                        root
                    );

                    return;

                }


                const cancelNewAttributeButton =
                    event.target.closest(
                        "[data-cancel-new-attribute]"
                    );

                if (cancelNewAttributeButton) {

                    closeNewAttribute(
                        root
                    );

                    return;

                }


                const saveNewAttributeButton =
                    event.target.closest(
                        "[data-save-new-attribute]"
                    );

                if (saveNewAttributeButton) {

                    saveNewAttribute(
                        root,
                        saveNewAttributeButton
                    );

                }

            }
        );


        /*
         * --------------------------------------------------------
         * Escape closes open editors
         * --------------------------------------------------------
         */

        root.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key !== "Escape"
                ) {
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
                        cancelField(
                            field
                        );
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
                        closeAttribute(
                            attribute
                        );
                    }

                }

            }
        );

    }


    /*
     * ============================================================
     * GENERIC OBJECTTYPE FIELD EDITING
     * ============================================================
     */

    function getFieldInput(
        field
    ) {

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


    function openField(
        field
    ) {

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


        /*
         * Only one ordinary field editor open at once.
         */

        const root =
            field.closest(
                ".proposal-editor"
            );

        if (root) {

            root.querySelectorAll(
                ".proposal-editor-field"
            ).forEach(
                function (otherField) {

                    if (
                        otherField === field
                    ) {
                        return;
                    }

                    const otherDisplay =
                        otherField.querySelector(
                            "[data-field-display]"
                        );

                    const otherEditor =
                        otherField.querySelector(
                            "[data-field-editor]"
                        );

                    const otherEditButton =
                        otherField.querySelector(
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

                }
            );

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
            getFieldInput(
                field
            );

        if (input) {
            input.focus();
        }

    }


    function cancelField(
        field
    ) {

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


        clearFieldError(
            field
        );

    }


    async function saveField(
        root,
        field,
        button
    ) {

        const fieldName =
            field.dataset.field;

        const input =
            getFieldInput(
                field
            );

        if (
            !fieldName
            || !input
        ) {
            return;
        }


        clearFieldError(
            field
        );


        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {

            showFieldError(
                field,
                "Unable to save: CSRF token is unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
                    {
                        field:
                            fieldName,

                        value:
                            readInputValue(
                                input
                            )
                    }
                );


            writeInputValue(
                input,
                data.value
            );


            updateFieldDisplay(
                field,
                data.value
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
        field,
        button
    ) {

        const fieldName =
            field.dataset.field;

        if (!fieldName) {
            return;
        }


        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {

            showFieldError(
                field,
                "Unable to discard: CSRF token is unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
                    {
                        field:
                            fieldName,

                        action:
                            "discard"
                    }
                );


            const input =
                getFieldInput(
                    field
                );


            if (input) {

                writeInputValue(
                    input,
                    data.value
                );

            }


            updateFieldDisplay(
                field,
                data.value
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
        value
    ) {

        const display =
            field.querySelector(
                "[data-field-display]"
            );

        if (!display) {
            return;
        }


        display.replaceChildren();


        /*
         * is_active isn't rendered as literal true/false.
         */

        if (
            field.dataset.field ===
            "is_active"
        ) {

            display.textContent =
                normaliseValue(
                    value
                ) === "true"
                    ? "Active"
                    : "Retired";

            return;

        }


        const text =
            normaliseValue(
                value
            );


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


    /*
     * ============================================================
     * OBJECTTYPE LIFECYCLE
     * ============================================================
     */

    async function setObjectTypeStatus(
        root,
        button
    ) {

        const control =
            root.querySelector(
                "[data-object-type-lifecycle]"
            );

        if (!control) {
            return;
        }


        const current =
            control.dataset.active ===
            "true";


        const desired =
            !current;


        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {
            console.error(
                "ObjectType status: CSRF token unavailable."
            );
            return;
        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
                    {
                        action:
                            "set_object_type_status",

                        is_active:
                            desired
                                ? "true"
                                : "false"
                    }
                );


            updateObjectTypeStatus(
                root,
                data.value,
                data.proposed
            );

        } catch (error) {

            console.error(
                "ObjectType status update failed:",
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    async function discardObjectTypeStatus(
        root,
        button
    ) {

        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {
            console.error(
                "ObjectType lifecycle discard: CSRF token unavailable."
            );
            return;
        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
                    {
                        action:
                            "discard_object_type_status"
                    }
                );


            updateObjectTypeStatus(
                root,
                data.value,
                false
            );

        } catch (error) {

            console.error(
                "ObjectType lifecycle discard failed:",
                error
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function updateObjectTypeStatus(
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

        const pill =
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


        if (pill) {

            pill.className =
                "model-status-pill "
                + (
                    active
                        ? "model-status-active"
                        : "model-status-retired"
                );


            pill.replaceChildren();


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
     * ATTRIBUTE EDITOR
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


        const firstInput =
            editor.querySelector(
                "input:not([type=hidden]), textarea, select"
            );


        if (firstInput) {
            firstInput.focus();
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


    async function saveAttribute(
        root,
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

        const editor =
            attribute.querySelector(
                "[data-attribute-editor]"
            );


        if (
            !attributeId
            || !editor
        ) {
            return;
        }


        clearAttributeError(
            attribute
        );


        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {

            showAttributeError(
                attribute,
                "Unable to save: CSRF token is unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const values =
                collectAttributeForm(
                    editor
                );


            values.action =
                "save_attribute";

            values.attribute_id =
                attributeId;


            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
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


            if (
                data.created !== undefined
            ) {

                attribute.dataset
                    .attributeCreated =
                    data.created
                        ? "true"
                        : "false";

            }

        } catch (error) {

            showAttributeError(
                attribute,
                error.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    async function discardAttribute(
        root,
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


        const csrfToken =
            getCsrfToken();

        if (!csrfToken) {

            showAttributeError(
                attribute,
                "Unable to discard: CSRF token is unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
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
                attribute,
                error.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    async function setAttributeStatus(
        root,
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


        /*
         * Store the effective current state on the element.
         */

        let current =
            attribute.dataset.attributeActive;


        /*
         * Older pages may not provide data-attribute-active.
         * Infer it from the visible button.
         */

        if (
            current !== "true"
            && current !== "false"
        ) {

            current =
                button.textContent
                    .trim()
                    .toLowerCase()
                    === "activate"
                        ? "false"
                        : "true";

        }


        const desired =
            current !== "true";


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showAttributeError(
                attribute,
                "Unable to update status: CSRF token is unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    root.dataset.updateUrl,
                    csrfToken,
                    {
                        action:
                            "set_attribute_status",

                        attribute_id:
                            attributeId,

                        is_active:
                            desired
                                ? "true"
                                : "false"
                    }
                );


            updateAttributeStatus(
                attribute,
                data.value
            );


            updateAttributeProposedState(
                attribute,
                data.proposed_fields,
                data.proposed
            );

        } catch (error) {

            showAttributeError(
                attribute,
                error.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function updateAttributeStatus(
        attribute,
        value
    ) {

        const active =
            normaliseValue(
                value
            ) === "true";


        attribute.dataset.attributeActive =
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


        const status =
            attribute.querySelector(
                "[data-attribute-editor-status]"
            );


        if (status) {

            status.replaceChildren();


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


            status.appendChild(
                pill
            );

        }

    }


    /*
     * ============================================================
     * ATTRIBUTE FORM
     * ============================================================
     */

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
                normaliseValue(
                    values.required
                ) === "true";

        }


        if (nullable) {

            nullable.checked =
                normaliseValue(
                    values.nullable
                ) === "true";

        }


        const active =
            normaliseValue(
                values.is_active
            ) === "true";


        attribute.dataset.attributeActive =
            active
                ? "true"
                : "false";


        /*
         * Display
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
                normaliseValue(
                    values.required
                ) === "true"
                    ? "Required"
                    : "Optional";

        }


        if (nullableDisplay) {

            nullableDisplay.textContent =
                normaliseValue(
                    values.nullable
                ) === "true"
                    ? "Nullable"
                    : "Not nullable";

        }


        if (descriptionDisplay) {

            descriptionDisplay.textContent =
                values.description
                || "";

            descriptionDisplay.hidden =
                !values.description;

        }


        updateAttributeStatus(
            attribute,
            values.is_active
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


        attribute.dataset.attributeProposed =
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


        /*
         * Put Discard alongside the proposal indicator,
         * not beside Edit / Retire.
         */

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


            if (indicator) {

                indicator.appendChild(
                    document.createTextNode(
                        " "
                    )
                );

                indicator.appendChild(
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

            text:
                "Text",

            number:
                "Number",

            boolean:
                "Boolean",

            date:
                "Date",

            datetime:
                "Date & time",

            choice:
                "Choice"

        };


        return labels[value]
            || value
            || "";

    }


    /*
     * ============================================================
     * NEW ATTRIBUTE
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


        const name =
            editor.querySelector(
                '[name="attribute_name"]'
            );


        if (name) {
            name.focus();
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


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showElementError(
                error,
                "Unable to save: CSRF token is unavailable."
            );

            return;

        }


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
                    csrfToken,
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

                throw new Error(
                    "Attribute list not found."
                );

            }


            const empty =
                list.querySelector(
                    "[data-attribute-empty]"
                );


            if (empty) {
                empty.remove();
            }


            const newEditor =
                list.querySelector(
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

            showElementError(
                error,
                errorValue.message
            );

        } finally {

            button.disabled =
                false;

        }

    }


    function createAttributeElement(
        data
    ) {

        const attribute =
            document.createElement(
                "article"
            );


        attribute.className =
            "model-object-type-attribute";


        attribute.dataset.attributeId =
            data.attribute_id;


        attribute.dataset.attributeCreated =
            "true";


        attribute.dataset.attributeProposed =
            "true";


        attribute.dataset.attributeActive =
            normaliseValue(
                data.values.is_active
            ) === "true"
                ? "true"
                : "false";


        attribute.innerHTML = `
            <div
                class="model-object-type-attribute-display"
                data-attribute-display
            >

                <div
                    class="model-object-type-attribute-main"
                >

                    <h3
                        class="model-object-type-attribute-name"
                    ></h3>


                    <div
                        class="model-object-type-attribute-meta"
                    >

                        <span
                            data-attribute-key
                        ></span>

                        <span
                            data-attribute-data-type
                        ></span>

                        <span
                            data-attribute-required
                        ></span>

                        <span
                            data-attribute-nullable
                        ></span>

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

                        <label>
                            Name
                        </label>

                        <input
                            type="text"
                            name="attribute_name"
                            class="form-control"
                            maxlength="100"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>
                            Key
                        </label>

                        <input
                            type="text"
                            name="attribute_key"
                            class="form-control"
                            maxlength="100"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>
                            Data type
                        </label>

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

                        <label>
                            Description
                        </label>

                        <textarea
                            name="attribute_description"
                            class="form-control"
                            rows="3"
                        ></textarea>

                    </div>


                    <div class="model-editor-field">

                        <label>
                            Default value
                        </label>

                        <input
                            type="text"
                            name="attribute_default_value"
                            class="form-control"
                        >

                    </div>


                    <div class="model-editor-field">

                        <label>
                            Sort order
                        </label>

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
            attribute,
            data.values
        );


        return attribute;

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


            element.dataset.attributeEmpty =
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
     * OBJECTTYPE INDEX PROPOSAL DISCARD
     * ============================================================
     */

    async function discardObjectTypeProposal(
        button
    ) {

        const objectTypeId =
            button.dataset.objectTypeId;


        if (!objectTypeId) {

            console.error(
                "ObjectType proposal discard: object type ID is missing."
            );

            return;

        }


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            console.error(
                "ObjectType proposal discard: CSRF token unavailable."
            );

            return;

        }


        button.disabled =
            true;


        try {

            const data =
                await postForm(
                    window.location.href,
                    csrfToken,
                    {
                        action:
                            "discard_object_type_proposal",

                        object_type_id:
                            objectTypeId
                    }
                );


            if (!data.success) {

                throw new Error(
                    data.error
                    || "Unable to discard object type proposal."
                );

            }


            window.location.reload();

        } catch (error) {

            console.error(
                "ObjectType proposal discard failed:",
                error
            );

            button.disabled =
                false;

        }

    }


    /*
     * ============================================================
     * REQUEST HELPERS
     * ============================================================
     */

    async function postForm(
        url,
        csrfToken,
        values
    ) {

        if (!csrfToken) {

            throw new Error(
                "CSRF token is unavailable."
            );

        }


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
                            "application/x-www-form-urlencoded; charset=UTF-8",

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

            /*
             * Include a useful status in the error.
             */

            throw new Error(
                "The server returned an unexpected response "
                + `(${response.status}).`
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
     * ERROR HELPERS
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

        clearElementError(
            field.querySelector(
                "[data-proposal-error]"
            )
        );

    }


    function showAttributeError(
        attribute,
        error
    ) {

        const element =
            attribute.querySelector(
                "[data-attribute-error]"
            );


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

        clearElementError(
            attribute.querySelector(
                "[data-attribute-error]"
            )
        );

    }


    function showElementError(
        element,
        message
    ) {

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
