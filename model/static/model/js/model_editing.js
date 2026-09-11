
document.addEventListener("DOMContentLoaded", function () {

    /*
     * ============================================================
     * Weave proposal-aware model editing
     * ============================================================
     *
     * Supports:
     *
     *   ObjectType index
     *   ObjectType property editing
     *   ObjectType lifecycle
     *   AttributeDefinition property editing
     *   AttributeDefinition lifecycle
     *   AttributeDefinition creation
     *   Proposal discard
     *
     * Nothing here modifies canonical model state directly.
     * All writes go through proposal-aware Django endpoints.
     * ============================================================
     */


    /* ============================================================
       CSRF
       ============================================================ */

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


        const cookies =
            document.cookie.split(";");


        for (
            let cookie of cookies
        ) {

            cookie =
                cookie.trim();


            if (
                cookie.startsWith(
                    "csrftoken="
                )
            ) {

                return decodeURIComponent(
                    cookie.substring(
                        "csrftoken=".length
                    )
                );

            }

        }


        return null;
    }


    /* ============================================================
       Global delegated click handling
       ============================================================ */

    document.addEventListener(
        "click",
        function (event) {

            /*
             * ----------------------------------------------------
             * ObjectType index discard
             * ----------------------------------------------------
             */

            const discardObjectType =
                event.target.closest(
                    "[data-discard-object-type]"
                );

            if (discardObjectType) {

                event.preventDefault();
                event.stopPropagation();

                discardObjectTypeProposal(
                    discardObjectType
                );

                return;
            }


            /*
             * ----------------------------------------------------
             * Find containing proposal editor.
             * ----------------------------------------------------
             */

            const root =
                event.target.closest(
                    ".proposal-editor"
                );

            if (!root) {
                return;
            }


            /*
             * ----------------------------------------------------
             * ObjectType property editing
             * ----------------------------------------------------
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
             * ----------------------------------------------------
             * ObjectType lifecycle
             * ----------------------------------------------------
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
             * ----------------------------------------------------
             * Attribute editing
             * ----------------------------------------------------
             */

            const editAttribute =
                event.target.closest(
                    "[data-edit-attribute]"
                );

            if (editAttribute) {

                const attribute =
                    editAttribute.closest(
                        ".model-object-type-attribute"
                    );

                if (attribute) {

                    openAttribute(
                        attribute
                    );

                }

                return;
            }


            const cancelAttribute =
                event.target.closest(
                    "[data-cancel-attribute]"
                );

            if (cancelAttribute) {

                const attribute =
                    cancelAttribute.closest(
                        ".model-object-type-attribute"
                    );

                if (attribute) {

                    closeAttribute(
                        attribute
                    );

                }

                return;
            }


            const saveAttributeButton =
                event.target.closest(
                    "[data-save-attribute]"
                );

            if (saveAttributeButton) {

                saveAttribute(
                    root,
                    saveAttributeButton
                );

                return;
            }


            const discardAttributeButton =
                event.target.closest(
                    "[data-discard-attribute]"
                );

            if (discardAttributeButton) {

                discardAttribute(
                    root,
                    discardAttributeButton
                );

                return;
            }


            /*
             * ----------------------------------------------------
             * Attribute lifecycle
             * ----------------------------------------------------
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
             * ----------------------------------------------------
             * New Attribute
             * ----------------------------------------------------
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


    /* ============================================================
       Escape handling
       ============================================================ */

    document.addEventListener(
        "keydown",
        function (event) {

            if (
                event.key !== "Escape"
            ) {
                return;
            }


            const root =
                event.target.closest(
                    ".proposal-editor"
                );

            if (!root) {
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


    /* ============================================================
       ObjectType field helpers
       ============================================================ */

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


    function readInputValue(
        input
    ) {

        if (!input) {
            return "";
        }


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


        if (
            input instanceof HTMLInputElement
            && input.type === "checkbox"
        ) {

            const normalised =
                normaliseValue(
                    value
                );


            input.checked =
                normalised === "true"
                || normalised === "1"
                || normalised === "yes"
                || normalised === "on";

            return;
        }


        input.value =
            normaliseValue(
                value
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


        if (
            !display
            || !editor
        ) {
            return;
        }


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

                    const otherEdit =
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

                        if (otherEdit) {
                            otherEdit.hidden =
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


        if (
            !display
            || !editor
        ) {
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


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showFieldError(
                field,
                "Unable to save: CSRF token unavailable."
            );

            return;
        }


        clearFieldError(
            field
        );


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


            setFieldProposalState(
                field,
                Boolean(
                    data.proposed
                )
            );

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
                "Unable to discard: CSRF token unavailable."
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


            setFieldProposalState(
                field,
                false
            );

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


    function setFieldProposalState(
        field,
        proposed
    ) {

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
                !proposed;
        }


        if (discard) {
            discard.hidden =
                !proposed;
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


    /* ============================================================
       ObjectType lifecycle
       ============================================================ */

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
                "ObjectType lifecycle: CSRF unavailable."
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


            updateObjectTypeStatusUI(
                root,
                data.value,
                data.proposed
            );

        } catch (error) {

            console.error(
                "ObjectType lifecycle update failed:",
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
                "ObjectType lifecycle discard: CSRF unavailable."
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


            updateObjectTypeStatusUI(
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


    /* ============================================================
       Attribute helpers
       ============================================================ */

    function openAttribute(
        attribute
    ) {

        const display =
            attribute.querySelector(
                "[data-attribute-display]"
            );

        const editor =
            attribute.querySelector(
                "[data-attribute-editor]"
            );


        if (
            !display
            || !editor
        ) {
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

        const display =
            attribute.querySelector(
                "[data-attribute-display]"
            );

        const editor =
            attribute.querySelector(
                "[data-attribute-editor]"
            );


        if (
            !display
            || !editor
        ) {
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


    function collectAttributeValues(
        editor
    ) {

        const read =
            function (
                name,
                fallback
            ) {

                const input =
                    editor.querySelector(
                        `[name="${name}"]`
                    );

                return input
                    ? input.value
                    : fallback;

            };


        const checked =
            function (
                name
            ) {

                const input =
                    editor.querySelector(
                        `[name="${name}"]`
                    );

                return (
                    input
                    && input.checked
                )
                    ? "on"
                    : "";

            };


        return {

            attribute_name:
                read(
                    "attribute_name",
                    ""
                ),

            attribute_key:
                read(
                    "attribute_key",
                    ""
                ),

            attribute_data_type:
                read(
                    "attribute_data_type",
                    "text"
                ),

            attribute_description:
                read(
                    "attribute_description",
                    ""
                ),

            attribute_default_value:
                read(
                    "attribute_default_value",
                    ""
                ),

            attribute_sort_order:
                read(
                    "attribute_sort_order",
                    "0"
                ),

            attribute_required:
                checked(
                    "attribute_required"
                ),

            attribute_nullable:
                checked(
                    "attribute_nullable"
                )

        };

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


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showAttributeError(
                attribute,
                "Unable to save: CSRF token unavailable."
            );

            return;
        }


        clearAttributeError(
            attribute
        );


        button.disabled =
            true;


        try {

            const values =
                collectAttributeValues(
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


            updateAttributeProposalState(
                attribute,
                data.proposed_fields,
                data.proposed
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
                "Unable to discard: CSRF token unavailable."
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


            updateAttributeProposalState(
                attribute,
                data.proposed_fields,
                data.proposed
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


        const current =
            attribute.dataset.attributeActive ===
            "true";


        const desired =
            !current;


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showAttributeError(
                attribute,
                "Unable to update status: CSRF token unavailable."
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


            updateAttributeStatusUI(
                attribute,
                data.value
            );


            updateAttributeProposalState(
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


    function updateAttributeStatusUI(
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


        const editorStatus =
            attribute.querySelector(
                "[data-attribute-editor-status]"
            );


        if (editorStatus) {

            editorStatus.replaceChildren();


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


            editorStatus.appendChild(
                pill
            );

        }

    }


    function applyAttributeValues(
        attribute,
        values
    ) {

        const input =
            function (
                name
            ) {

                return attribute.querySelector(
                    `[name="${name}"]`
                );

            };


        const name =
            input(
                "attribute_name"
            );

        const key =
            input(
                "attribute_key"
            );

        const dataType =
            input(
                "attribute_data_type"
            );

        const description =
            input(
                "attribute_description"
            );

        const defaultValue =
            input(
                "attribute_default_value"
            );

        const sortOrder =
            input(
                "attribute_sort_order"
            );

        const required =
            input(
                "attribute_required"
            );

        const nullable =
            input(
                "attribute_nullable"
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


        updateAttributeStatusUI(
            attribute,
            values.is_active
        );


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

    }


    function updateAttributeProposalState(
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


        const discard =
            attribute.querySelector(
                "[data-discard-attribute]"
            );


        if (indicator) {

            indicator.hidden =
                !isProposed;

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


    /* ============================================================
       New Attribute
       ============================================================ */

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


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            showElementError(
                error,
                "Unable to save: CSRF token unavailable."
            );

            return;

        }


        clearElementError(
            error
        );


        button.disabled =
            true;


        try {

            const values =
                collectAttributeValues(
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


            /*
             * Remove the empty state if present.
             */

            const empty =
                root.querySelector(
                    "[data-attribute-empty]"
                );


            if (empty) {
                empty.remove();
            }


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
                                Date &amp; time
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


    /* ============================================================
       ObjectType index discard
       ============================================================ */

    async function discardObjectTypeProposal(
        button
    ) {

        const objectTypeId =
            button.dataset.objectTypeId;


        if (!objectTypeId) {

            console.error(
                "ObjectType proposal discard: ID missing."
            );

            return;
        }


        const csrfToken =
            getCsrfToken();


        if (!csrfToken) {

            console.error(
                "ObjectType proposal discard: CSRF unavailable."
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


    /* ============================================================
       Request
       ============================================================ */

    async function postForm(
        url,
        csrfToken,
        values
    ) {

        if (!csrfToken) {

            throw new Error(
                "CSRF token unavailable."
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

            throw new Error(
                `Unexpected server response (${response.status}).`
            );

        }


        const data =
            await response.json();


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
                    Object.entries(
                        data.errors
                    )
                    .map(
                        function (
                            [
                                field,
                                error
                            ]
                        ) {

                            return `${field}: ${error}`;

                        }
                    )
                    .join(
                        " "
                    );

            }


            throw new Error(
                message
                || "The proposed change could not be saved."
            );

        }


        return data;

    }


    /* ============================================================
       Error helpers
       ============================================================ */

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


    function clearAttributeError(
        attribute
    ) {

        clearElementError(
            attribute.querySelector(
                "[data-attribute-error]"
            )
        );

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

