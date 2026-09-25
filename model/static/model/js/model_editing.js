document.addEventListener("DOMContentLoaded", function () {
  /*
   * ============================================================
   * OnyxJar proposal-aware model editing
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
    const input = document.querySelector('[name="csrfmiddlewaretoken"]');

    if (input && input.value) {
      return input.value;
    }

    const cookies = document.cookie.split(";");

    for (let cookie of cookies) {
      cookie = cookie.trim();

      if (cookie.startsWith("csrftoken=")) {
        return decodeURIComponent(cookie.substring("csrftoken=".length));
      }
    }

    return null;
  }

  /* ============================================================
       Global delegated click handling
       ============================================================ */

  document.addEventListener("click", function (event) {
    /*
     * ----------------------------------------------------
     * ObjectType index discard
     * ----------------------------------------------------
     */

    const discardObjectType = event.target.closest(
      "[data-discard-object-type]",
    );

    if (discardObjectType) {
      event.preventDefault();
      event.stopPropagation();

      discardObjectTypeProposal(discardObjectType);

      return;
    }

    /*
     * ----------------------------------------------------
     * RelationshipType index discard
     * ----------------------------------------------------
     */

    const discardRelationshipType = event.target.closest(
      "[data-discard-relationship-type]",
    );

    if (discardRelationshipType) {
      event.preventDefault();
      event.stopPropagation();

      discardRelationshipTypeProposal(discardRelationshipType);

      return;
    }

    /*
     * ----------------------------------------------------
     * Object data index discard (pending/proposed records)
     * ----------------------------------------------------
     */

    const discardObject = event.target.closest("[data-discard-object]");

    if (discardObject) {
      event.preventDefault();
      event.stopPropagation();

      discardObjectProposal(discardObject);

      return;
    }

    /*
     * ----------------------------------------------------
     * Relationship data index discard (pending/proposed records)
     * ----------------------------------------------------
     */

    const discardRelationship = event.target.closest(
      "[data-discard-relationship]",
    );

    if (discardRelationship) {
      event.preventDefault();
      event.stopPropagation();

      discardRelationshipProposal(discardRelationship);

      return;
    }

    /*
     * ----------------------------------------------------
     * Find containing proposal editor.
     * ----------------------------------------------------
     */

    const root = event.target.closest(".proposal-editor");

    if (!root) {
      return;
    }

    /*
     * ----------------------------------------------------
     * ObjectType property editing
     * ----------------------------------------------------
     */

    const editButton = event.target.closest('[data-proposal-action="edit"]');

    if (editButton) {
      const field = editButton.closest(".proposal-editor-field");

      if (field) {
        openField(field);
      }

      return;
    }

    const cancelButton = event.target.closest(
      '[data-proposal-action="cancel"]',
    );

    if (cancelButton) {
      const field = cancelButton.closest(".proposal-editor-field");

      if (field) {
        cancelField(field);
      }

      return;
    }

    const saveButton = event.target.closest('[data-proposal-action="save"]');

    if (saveButton) {
      const field = saveButton.closest(".proposal-editor-field");

      if (field) {
        saveField(root, field, saveButton);
      }

      return;
    }

    const discardFieldButton = event.target.closest(
      '[data-proposal-action="discard"]',
    );

    if (discardFieldButton) {
      const field = discardFieldButton.closest(".proposal-editor-field");

      if (field) {
        discardField(root, field, discardFieldButton);
      }

      return;
    }

    /*
     * ----------------------------------------------------
     * ObjectType lifecycle
     * ----------------------------------------------------
     */

    const objectTypeStatusButton = event.target.closest("[data-status-toggle]");

    if (objectTypeStatusButton) {
      if (root.querySelector("[data-relationship-type-lifecycle]")) {
        setRelationshipTypeStatus(root, objectTypeStatusButton);
      } else if (root.querySelector("[data-object-lifecycle]")) {
        setObjectStatus(root, objectTypeStatusButton);
      } else if (root.querySelector("[data-relationship-lifecycle]")) {
        setRelationshipStatus(root, objectTypeStatusButton);
      } else {
        setObjectTypeStatus(root, objectTypeStatusButton);
      }

      return;
    }

    const objectTypeLifecycleDiscard = event.target.closest(
      "[data-lifecycle-discard]",
    );

    if (objectTypeLifecycleDiscard) {
      if (root.querySelector("[data-relationship-type-lifecycle]")) {
        discardRelationshipTypeStatus(root, objectTypeLifecycleDiscard);
      } else if (root.querySelector("[data-object-lifecycle]")) {
        discardObjectStatus(root, objectTypeLifecycleDiscard);
      } else if (root.querySelector("[data-relationship-lifecycle]")) {
        discardRelationshipStatus(root, objectTypeLifecycleDiscard);
      } else {
        discardObjectTypeStatus(root, objectTypeLifecycleDiscard);
      }

      return;
    }

    /*
     * ----------------------------------------------------
     * Attribute editing
     * ----------------------------------------------------
     */

    const editAttribute = event.target.closest("[data-edit-attribute]");

    if (editAttribute) {
      const attribute = editAttribute.closest(".model-object-type-attribute");

      if (attribute) {
        openAttribute(attribute);
      }

      return;
    }

    const cancelAttribute = event.target.closest("[data-cancel-attribute]");

    if (cancelAttribute) {
      const attribute = cancelAttribute.closest(".model-object-type-attribute");

      if (attribute) {
        closeAttribute(attribute);
      }

      return;
    }

    const saveAttributeButton = event.target.closest("[data-save-attribute]");

    if (saveAttributeButton) {
      saveAttribute(root, saveAttributeButton);

      return;
    }

    const discardAttributeButton = event.target.closest(
      "[data-discard-attribute]",
    );

    if (discardAttributeButton) {
      discardAttribute(root, discardAttributeButton);

      return;
    }

    /*
     * ----------------------------------------------------
     * Choice attribute — allowed values
     * ----------------------------------------------------
     */

    const addChoiceButton = event.target.closest("[data-add-choice]");

    if (addChoiceButton) {
      const section = addChoiceButton.closest("[data-choice-section]");

      if (section) {
        addChoiceRow(section);
      }

      return;
    }

    const removeChoiceButton = event.target.closest("[data-remove-choice]");

    if (removeChoiceButton) {
      const row = removeChoiceButton.closest("[data-choice-row]");

      if (row) {
        row.remove();
      }

      return;
    }

    /*
     * ----------------------------------------------------
     * Attribute lifecycle
     * ----------------------------------------------------
     */

    const attributeStatusButton = event.target.closest(
      "[data-attribute-status-toggle]",
    );

    if (attributeStatusButton) {
      setAttributeStatus(root, attributeStatusButton);

      return;
    }

    /*
     * ----------------------------------------------------
     * New Attribute
     * ----------------------------------------------------
     */

    const addAttributeButton = event.target.closest("[data-add-new-attribute]");

    if (addAttributeButton) {
      openNewAttribute(root);

      return;
    }

    const cancelNewAttributeButton = event.target.closest(
      "[data-cancel-new-attribute]",
    );

    if (cancelNewAttributeButton) {
      closeNewAttribute(root);

      return;
    }

    const saveNewAttributeButton = event.target.closest(
      "[data-save-new-attribute]",
    );

    if (saveNewAttributeButton) {
      saveNewAttribute(root, saveNewAttributeButton);
    }

    /*
     * ----------------------------------------------------
     * RelationshipType rule editing
     * ----------------------------------------------------
     */

    const addRuleButton = event.target.closest("[data-rule-add]");

    if (addRuleButton) {
      openNewRule(root);

      return;
    }

    const editRuleButton = event.target.closest("[data-rule-edit]");

    if (editRuleButton) {
      const rule = editRuleButton.closest(".model-relationship-rule");

      if (rule) {
        openRule(rule);
      }

      return;
    }

    const cancelRuleButton = event.target.closest("[data-rule-cancel]");

    if (cancelRuleButton) {
      const rule = cancelRuleButton.closest(".model-relationship-rule");

      if (rule) {
        closeRule(rule);
      }

      return;
    }

    const saveRuleButton = event.target.closest("[data-rule-save]");

    if (saveRuleButton) {
      saveRule(root, saveRuleButton);

      return;
    }

    const discardRuleButton = event.target.closest("[data-rule-discard]");

    if (discardRuleButton) {
      discardRule(root, discardRuleButton);

      return;
    }

    /*
     * ----------------------------------------------------
     * RelationshipType new rule
     * ----------------------------------------------------
     */

    const cancelNewRuleButton = event.target.closest("[data-rule-cancel-new]");

    if (cancelNewRuleButton) {
      closeNewRule(root);

      return;
    }

    const saveNewRuleButton = event.target.closest("[data-rule-save-new]");

    if (saveNewRuleButton) {
      saveNewRule(root, saveNewRuleButton);
    }
  });

  /* ============================================================
       Choice attribute — show/hide "Allowed values" on data type
       ============================================================ */

  document.addEventListener("change", function (event) {
    const dataTypeInput = event.target.closest(
      "[data-attribute-data-type-input]",
    );

    if (!dataTypeInput) {
      return;
    }

    setChoiceSectionVisibility(dataTypeInput);
    setAttributeColourSectionVisibility(dataTypeInput);
    updateDefaultValueVisibility(dataTypeInput);
  });

  /* ============================================================
       Attribute value colours — save on change
       ============================================================ */

  document.addEventListener("change", function (event) {
    const colourInput = event.target.closest("[data-attribute-colour-input]");

    if (!colourInput) {
      return;
    }

    const section = colourInput.closest("[data-attribute-colour-section]");
    const row = colourInput.closest("[data-attribute-colour-row]");

    if (!section || !row) {
      return;
    }

    const endpoint = section.dataset.attributeColoursEndpoint;
    const valueKey = row.dataset.valueKey;
    const previousValue = colourInput.dataset.lastValue || colourInput.value;

    postAttributeColour(endpoint, getCsrfToken(), {
      field: valueKey,
      value: colourInput.value,
    })
      .then(function () {
        colourInput.dataset.lastValue = colourInput.value;
      })
      .catch(function (error) {
        colourInput.value = previousValue;
        console.error("Attribute colour update failed:", error);
      });
  });

  /* ============================================================
       Escape handling
       ============================================================ */

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
      return;
    }

    const root = event.target.closest(".proposal-editor");

    if (!root) {
      return;
    }

    const fieldEditor = event.target.closest("[data-field-editor]");

    if (fieldEditor) {
      const field = fieldEditor.closest(".proposal-editor-field");

      if (field) {
        cancelField(field);
      }

      return;
    }

    const attributeEditor = event.target.closest("[data-attribute-editor]");

    if (attributeEditor) {
      const attribute = attributeEditor.closest(".model-object-type-attribute");

      if (attribute) {
        closeAttribute(attribute);
      }
    }
  });

  /* ============================================================
       ObjectType field helpers
       ============================================================ */

  function getFieldInput(field) {
    const editor = field.querySelector("[data-field-editor]");

    if (!editor) {
      return null;
    }

    return editor.querySelector("input:not([type=hidden]), textarea, select");
  }

  function readInputValue(input) {
    if (!input) {
      return "";
    }

    if (input instanceof HTMLInputElement && input.type === "checkbox") {
      return input.checked ? "true" : "false";
    }

    return input.value;
  }

  function writeInputValue(input, value) {
    if (!input) {
      return;
    }

    if (input instanceof HTMLInputElement && input.type === "checkbox") {
      const normalised = normaliseValue(value);

      input.checked =
        normalised === "true" ||
        normalised === "1" ||
        normalised === "yes" ||
        normalised === "on";

      return;
    }

    input.value = normaliseValue(value);
  }

  function openField(field) {
    const display = field.querySelector("[data-field-display]");

    const editor = field.querySelector("[data-field-editor]");

    const editButton = field.querySelector('[data-proposal-action="edit"]');

    if (!display || !editor) {
      return;
    }

    const root = field.closest(".proposal-editor");

    if (root) {
      root
        .querySelectorAll(".proposal-editor-field")
        .forEach(function (otherField) {
          if (otherField === field) {
            return;
          }

          const otherDisplay = otherField.querySelector("[data-field-display]");

          const otherEditor = otherField.querySelector("[data-field-editor]");

          const otherEdit = otherField.querySelector(
            '[data-proposal-action="edit"]',
          );

          if (otherDisplay && otherEditor) {
            otherDisplay.hidden = false;

            otherEditor.hidden = true;

            if (otherEdit) {
              otherEdit.hidden = false;
            }
          }
        });
    }

    display.hidden = true;

    editor.hidden = false;

    if (editButton) {
      editButton.hidden = true;
    }

    const input = getFieldInput(field);

    if (input) {
      input.focus();
    }
  }

  function cancelField(field) {
    const display = field.querySelector("[data-field-display]");

    const editor = field.querySelector("[data-field-editor]");

    const editButton = field.querySelector('[data-proposal-action="edit"]');

    if (!display || !editor) {
      return;
    }

    editor.hidden = true;

    display.hidden = false;

    if (editButton) {
      editButton.hidden = false;
    }

    clearFieldError(field);
  }

  async function saveField(root, field, button) {
    const fieldName = field.dataset.field;

    const input = getFieldInput(field);

    if (!fieldName || !input) {
      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showFieldError(field, "Unable to save: CSRF token unavailable.");

      return;
    }

    clearFieldError(field);

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        field: fieldName,

        value: readInputValue(input),
      });

      writeInputValue(input, data.value);

      updateFieldDisplay(field, displayValue(data));

      cancelField(field);

      setFieldProposalState(field, Boolean(data.proposed));
    } catch (error) {
      showFieldError(field, error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function discardField(root, field, button) {
    const fieldName = field.dataset.field;

    if (!fieldName) {
      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showFieldError(field, "Unable to discard: CSRF token unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        field: fieldName,

        action: "discard",
      });

      const input = getFieldInput(field);

      writeInputValue(input, data.value);

      updateFieldDisplay(field, displayValue(data));

      cancelField(field);

      setFieldProposalState(field, false);
    } catch (error) {
      showFieldError(field, error.message);
    } finally {
      button.disabled = false;
    }
  }

  function setFieldProposalState(field, proposed) {
    const indicator = field.querySelector("[data-proposal-indicator]");

    const discard = field.querySelector('[data-proposal-action="discard"]');

    if (indicator) {
      indicator.hidden = !proposed;
    }

    if (discard) {
      discard.hidden = !proposed;
    }
  }

  // A field whose stored value is an id (a relationship endpoint) also
  // returns the label to show for it.
  function displayValue(data) {
    return data.display !== undefined ? data.display : data.value;
  }

  function updateFieldDisplay(field, value) {
    const display = field.querySelector("[data-field-display]");

    if (!display) {
      return;
    }

    display.replaceChildren();

    const text = normaliseValue(value);

    if (!text.trim()) {
      const empty = document.createElement("span");

      empty.className = "model-field-empty";

      empty.textContent = "Not defined";

      display.appendChild(empty);

      return;
    }

    display.textContent = text;
  }

  /* ============================================================
       ObjectType lifecycle
       ============================================================ */

  async function setObjectTypeStatus(root, button) {
    const control = root.querySelector("[data-object-type-lifecycle]");

    if (!control) {
      return;
    }

    const current = control.dataset.active === "true";

    const desired = !current;

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("ObjectType lifecycle: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "set_object_type_status",

        is_active: desired ? "true" : "false",
      });

      updateObjectTypeStatusUI(root, data.value, data.proposed);
    } catch (error) {
      console.error("ObjectType lifecycle update failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  async function discardObjectTypeStatus(root, button) {
    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("ObjectType lifecycle discard: CSRF unavailable.");
      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_object_type_status",
      });

      updateObjectTypeStatusUI(root, data.value, false);
    } catch (error) {
      console.error("ObjectType lifecycle discard failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  function updateObjectTypeStatusUI(root, value, proposed) {
    const active = normaliseValue(value) === "true";

    const control = root.querySelector("[data-object-type-lifecycle]");

    const status = root.querySelector("[data-status-display]");

    const toggle = root.querySelector("[data-status-toggle]");

    const indicator = root.querySelector("[data-lifecycle-proposal-indicator]");

    const discard = root.querySelector("[data-lifecycle-discard]");

    if (control) {
      control.dataset.active = active ? "true" : "false";

      control.dataset.proposed = proposed ? "true" : "false";
    }

    if (status) {
      status.className =
        "model-status-pill " +
        (active ? "model-status-active" : "model-status-retired");

      status.replaceChildren();

      const icon = document.createElement("i");

      icon.className = active ? "bi bi-check-circle" : "bi bi-archive";

      status.appendChild(icon);

      status.appendChild(
        document.createTextNode(active ? " Active" : " Retired"),
      );
    }

    if (toggle) {
      toggle.textContent = active ? "Retire" : "Activate";
    }

    if (indicator) {
      indicator.hidden = !proposed;
    }

    if (discard) {
      discard.hidden = !proposed;
    }
  }

  /* ============================================================
       Object (data record) lifecycle
       ============================================================ */

  async function setObjectStatus(root, button) {
    const control = root.querySelector("[data-object-lifecycle]");

    if (!control) {
      return;
    }

    const current = control.dataset.active === "true";

    const desired = !current;

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Object lifecycle: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "set_object_status",

        is_active: desired ? "true" : "false",
      });

      updateObjectStatusUI(root, data.value, data.proposed);
    } catch (error) {
      console.error("Object lifecycle update failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  async function discardObjectStatus(root, button) {
    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Object lifecycle discard: CSRF unavailable.");
      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_object_status",
      });

      updateObjectStatusUI(root, data.value, false);
    } catch (error) {
      console.error("Object lifecycle discard failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  function updateObjectStatusUI(root, value, proposed) {
    const active = normaliseValue(value) === "true";

    const control = root.querySelector("[data-object-lifecycle]");

    const status = root.querySelector("[data-status-display]");

    const toggle = root.querySelector("[data-status-toggle]");

    const indicator = root.querySelector("[data-lifecycle-proposal-indicator]");

    const discard = root.querySelector("[data-lifecycle-discard]");

    if (control) {
      control.dataset.active = active ? "true" : "false";

      control.dataset.proposed = proposed ? "true" : "false";
    }

    if (status) {
      status.className =
        "model-status-pill " +
        (active ? "model-status-active" : "model-status-retired");

      status.replaceChildren();

      const icon = document.createElement("i");

      icon.className = active ? "bi bi-check-circle" : "bi bi-archive";

      status.appendChild(icon);

      status.appendChild(
        document.createTextNode(active ? " Active" : " Retired"),
      );
    }

    if (toggle) {
      toggle.textContent = active ? "Retire" : "Activate";
    }

    if (indicator) {
      indicator.hidden = !proposed;
    }

    if (discard) {
      discard.hidden = !proposed;
    }
  }

  /* ============================================================
       Object data index discard
       ============================================================ */

  async function discardObjectProposal(button) {
    const objectId = button.dataset.objectId;

    if (!objectId) {
      console.error("Object proposal discard: ID missing.");

      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Object proposal discard: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(window.location.href, csrfToken, {
        action: "discard_object_proposal",

        object_id: objectId,
      });

      if (!data.success) {
        throw new Error(data.error || "Unable to discard object proposal.");
      }

      window.location.reload();
    } catch (error) {
      console.error("Object proposal discard failed:", error);

      button.disabled = false;
    }
  }

  /* ============================================================
       Relationship (data record) lifecycle
       ============================================================ */

  async function setRelationshipStatus(root, button) {
    const control = root.querySelector("[data-relationship-lifecycle]");

    if (!control) {
      return;
    }

    const current = control.dataset.active === "true";

    const desired = !current;

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Relationship lifecycle: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "set_relationship_status",

        is_active: desired ? "true" : "false",
      });

      updateRelationshipStatusUI(root, data.value, data.proposed);
    } catch (error) {
      console.error("Relationship lifecycle update failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  async function discardRelationshipStatus(root, button) {
    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Relationship lifecycle discard: CSRF unavailable.");
      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_relationship_status",
      });

      updateRelationshipStatusUI(root, data.value, false);
    } catch (error) {
      console.error("Relationship lifecycle discard failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  function updateRelationshipStatusUI(root, value, proposed) {
    const active = normaliseValue(value) === "true";

    const control = root.querySelector("[data-relationship-lifecycle]");

    const status = root.querySelector("[data-status-display]");

    const toggle = root.querySelector("[data-status-toggle]");

    const indicator = root.querySelector("[data-lifecycle-proposal-indicator]");

    const discard = root.querySelector("[data-lifecycle-discard]");

    if (control) {
      control.dataset.active = active ? "true" : "false";

      control.dataset.proposed = proposed ? "true" : "false";
    }

    if (status) {
      status.className =
        "model-status-pill " +
        (active ? "model-status-active" : "model-status-retired");

      status.replaceChildren();

      const icon = document.createElement("i");

      icon.className = active ? "bi bi-check-circle" : "bi bi-archive";

      status.appendChild(icon);

      status.appendChild(
        document.createTextNode(active ? " Active" : " Retired"),
      );
    }

    if (toggle) {
      toggle.textContent = active ? "Retire" : "Activate";
    }

    if (indicator) {
      indicator.hidden = !proposed;
    }

    if (discard) {
      discard.hidden = !proposed;
    }
  }

  /* ============================================================
       Relationship data index discard
       ============================================================ */

  async function discardRelationshipProposal(button) {
    const relationshipId = button.dataset.relationshipId;

    if (!relationshipId) {
      console.error("Relationship proposal discard: ID missing.");

      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Relationship proposal discard: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(window.location.href, csrfToken, {
        action: "discard_relationship_proposal",

        relationship_id: relationshipId,
      });

      if (!data.success) {
        throw new Error(
          data.error || "Unable to discard relationship proposal.",
        );
      }

      window.location.reload();
    } catch (error) {
      console.error("Relationship proposal discard failed:", error);

      button.disabled = false;
    }
  }

  /* ============================================================
       RelationshipType lifecycle
       ============================================================ */

  async function setRelationshipTypeStatus(root, button) {
    const control = root.querySelector("[data-relationship-type-lifecycle]");

    if (!control) {
      return;
    }

    const current = control.dataset.active === "true";

    const desired = !current;

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("RelationshipType lifecycle: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "set_relationship_type_status",

        is_active: desired ? "true" : "false",
      });

      updateRelationshipTypeStatusUI(root, data.value, data.proposed);
    } catch (error) {
      console.error("RelationshipType lifecycle update failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  async function discardRelationshipTypeStatus(root, button) {
    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("RelationshipType lifecycle discard: CSRF unavailable.");
      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_relationship_type_status",
      });

      updateRelationshipTypeStatusUI(root, data.value, false);
    } catch (error) {
      console.error("RelationshipType lifecycle discard failed:", error);
    } finally {
      button.disabled = false;
    }
  }

  function updateRelationshipTypeStatusUI(root, value, proposed) {
    const active = normaliseValue(value) === "true";

    const control = root.querySelector("[data-relationship-type-lifecycle]");

    const status = root.querySelector("[data-status-display]");

    const toggle = root.querySelector("[data-status-toggle]");

    const indicator = root.querySelector("[data-lifecycle-proposal-indicator]");

    const discard = root.querySelector("[data-lifecycle-discard]");

    if (control) {
      control.dataset.active = active ? "true" : "false";

      control.dataset.proposed = proposed ? "true" : "false";
    }

    if (status) {
      status.className =
        "model-status-pill " +
        (active ? "model-status-active" : "model-status-retired");

      status.replaceChildren();

      const icon = document.createElement("i");

      icon.className = active ? "bi bi-check-circle" : "bi bi-dash-circle";

      status.appendChild(icon);

      status.appendChild(
        document.createTextNode(active ? " Active" : " Retired"),
      );
    }

    if (toggle) {
      toggle.textContent = active ? "Retire" : "Activate";
    }

    if (indicator) {
      indicator.hidden = !proposed;
    }

    if (discard) {
      discard.hidden = !proposed;
    }
  }

  /* ============================================================
       Attribute helpers
       ============================================================ */

  function openAttribute(attribute) {
    const display = attribute.querySelector("[data-attribute-display]");

    const editor = attribute.querySelector("[data-attribute-editor]");

    if (!display || !editor) {
      return;
    }

    display.hidden = true;

    editor.hidden = false;

    const firstInput = editor.querySelector(
      "input:not([type=hidden]), textarea, select",
    );

    if (firstInput) {
      firstInput.focus();
    }
  }

  function closeAttribute(attribute) {
    const display = attribute.querySelector("[data-attribute-display]");

    const editor = attribute.querySelector("[data-attribute-editor]");

    if (!display || !editor) {
      return;
    }

    editor.hidden = true;

    display.hidden = false;

    clearAttributeError(attribute);
  }

  function collectAttributeValues(editor) {
    const read = function (name, fallback) {
      const input = editor.querySelector(`[name="${name}"]`);

      return input ? input.value : fallback;
    };

    const checked = function (name) {
      const input = editor.querySelector(`[name="${name}"]`);

      return input && input.checked ? "on" : "";
    };

    return {
      attribute_name: read("attribute_name", ""),

      attribute_key: read("attribute_key", ""),

      attribute_data_type: read("attribute_data_type", "text"),

      attribute_description: read("attribute_description", ""),

      attribute_default_value: readDefaultValue(editor),

      attribute_sort_order: read("attribute_sort_order", "0"),

      attribute_required: checked("attribute_required"),

      attribute_nullable: checked("attribute_nullable"),

      attribute_choices: JSON.stringify(collectChoiceValues(editor)),
    };
  }

  function collectChoiceValues(editor) {
    return Array.from(editor.querySelectorAll("[data-choice-input]"))
      .map(function (input) {
        return input.value.trim();
      })
      .filter(function (value) {
        return value.length > 0;
      });
  }

  function addChoiceRow(section, value) {
    const list = section.querySelector("[data-choice-list]");

    if (!list) {
      return;
    }

    const row = document.createElement("div");

    row.className = "model-choice-row";
    row.setAttribute("data-choice-row", "");

    const input = document.createElement("input");

    input.type = "text";
    input.className = "form-control";
    input.setAttribute("data-choice-input", "");
    input.value = value || "";

    const removeButton = document.createElement("button");

    removeButton.type = "button";
    removeButton.className = "btn btn-sm btn-outline-secondary";
    removeButton.setAttribute("data-remove-choice", "");

    const icon = document.createElement("i");

    icon.className = "bi bi-x-lg";

    removeButton.appendChild(icon);

    row.appendChild(input);
    row.appendChild(removeButton);

    list.appendChild(row);

    input.focus();
  }

  function setChoiceSectionVisibility(dataTypeInput) {
    const fields = dataTypeInput.closest(".model-editor-fields");

    const section = fields
      ? fields.querySelector("[data-choice-section]")
      : null;

    if (section) {
      section.hidden = dataTypeInput.value !== "choice";
    }
  }

  /* ============================================================
       Attribute value colours — Choice/Boolean only
       ============================================================
       Exists regardless of whether the attribute is currently
       selected as a graph colour source (Background/Border/Line);
       shown/hidden purely by data type, alongside "Allowed values".
       ============================================================ */

  const ATTRIBUTE_COLOUR_ELIGIBLE = ["choice", "boolean"];

  function setAttributeColourSectionVisibility(dataTypeInput) {
    const fields = dataTypeInput.closest(".model-editor-fields");

    const section = fields
      ? fields.querySelector("[data-attribute-colour-section]")
      : null;

    if (section) {
      section.hidden = !ATTRIBUTE_COLOUR_ELIGIBLE.includes(dataTypeInput.value);
    }
  }

  async function postAttributeColour(url, csrfToken, values) {
    if (!csrfToken || !url) {
      throw new Error("This attribute must be saved before its colours can be set.");
    }

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: new URLSearchParams(values),
    });

    let data = null;
    try {
      data = await response.json();
    } catch (_error) {
      data = null;
    }

    if (!response.ok || !data || !data.success) {
      throw new Error((data && data.error) || "This colour could not be saved.");
    }

    return data;
  }

  /* ============================================================
       Default value — datatype-aware control switching
       ============================================================ */

  const DEFAULT_VALUE_SELECTORS = {
    text: "[data-default-value-text]",
    url: "[data-default-value-text]",
    number: "[data-default-value-number]",
    boolean: "[data-default-value-boolean]",
    date: "[data-default-value-date]",
    datetime: "[data-default-value-datetime]",
  };

  function getDefaultValueSection(scopeEl) {
    const fields = scopeEl.closest(".model-editor-fields");

    return fields ? fields.querySelector("[data-default-value-section]") : null;
  }

  function getActiveDefaultValueControl(section, dataType) {
    const selector = DEFAULT_VALUE_SELECTORS[dataType];

    return section && selector ? section.querySelector(selector) : null;
  }

  function updateDefaultValueVisibility(dataTypeInput) {
    const section = getDefaultValueSection(dataTypeInput);

    if (!section) {
      return;
    }

    Object.values(DEFAULT_VALUE_SELECTORS).forEach(function (selector) {
      const el = section.querySelector(selector);

      if (el) {
        el.hidden = true;
      }
    });

    const active = getActiveDefaultValueControl(section, dataTypeInput.value);

    section.hidden = !active;

    if (active) {
      active.hidden = false;
    }
  }

  function readDefaultValue(editor) {
    const dataTypeInput = editor.querySelector('[name="attribute_data_type"]');

    const dataType = dataTypeInput ? dataTypeInput.value : "text";

    const section = editor.querySelector("[data-default-value-section]");

    const active = getActiveDefaultValueControl(section, dataType);

    return active ? active.value : "";
  }

  function writeDefaultValue(attribute, values) {
    const section = attribute.querySelector("[data-default-value-section]");

    const active = getActiveDefaultValueControl(section, values.data_type);

    if (!active) {
      return;
    }

    if (active.matches("[data-default-value-boolean]")) {
      const normalised = normaliseValue(values.default_value);

      active.value =
        normalised === "true" || normalised === "false" ? normalised : "";
    } else {
      writeInputValue(active, values.default_value);
    }
  }

  async function saveAttribute(root, button) {
    const attribute = button.closest(".model-object-type-attribute");

    if (!attribute) {
      return;
    }

    const attributeId = attribute.dataset.attributeId;

    const editor = attribute.querySelector("[data-attribute-editor]");

    if (!attributeId || !editor) {
      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showAttributeError(attribute, "Unable to save: CSRF token unavailable.");

      return;
    }

    clearAttributeError(attribute);

    button.disabled = true;

    try {
      const values = collectAttributeValues(editor);

      values.action = "save_attribute";

      values.attribute_id = attributeId;

      const data = await postForm(root.dataset.updateUrl, csrfToken, values);

      applyAttributeValues(attribute, data.values);

      updateAttributeProposalState(
        attribute,
        data.proposed_fields,
        data.proposed,
      );

      closeAttribute(attribute);
    } catch (error) {
      showAttributeError(attribute, error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function discardAttribute(root, button) {
    const attribute = button.closest(".model-object-type-attribute");

    if (!attribute) {
      return;
    }

    const attributeId = attribute.dataset.attributeId;

    if (!attributeId) {
      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showAttributeError(
        attribute,
        "Unable to discard: CSRF token unavailable.",
      );

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_attribute",

        attribute_id: attributeId,
      });

      if (data.removed) {
        attribute.remove();

        updateAttributeEmptyState(root);

        return;
      }

      applyAttributeValues(attribute, data.values);

      updateAttributeProposalState(
        attribute,
        data.proposed_fields,
        data.proposed,
      );

      closeAttribute(attribute);
    } catch (error) {
      showAttributeError(attribute, error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function setAttributeStatus(root, button) {
    const attribute = button.closest(".model-object-type-attribute");

    if (!attribute) {
      return;
    }

    const attributeId = attribute.dataset.attributeId;

    if (!attributeId) {
      return;
    }

    const current = attribute.dataset.attributeActive === "true";

    const desired = !current;

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showAttributeError(
        attribute,
        "Unable to update status: CSRF token unavailable.",
      );

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(root.dataset.updateUrl, csrfToken, {
        action: "set_attribute_status",

        attribute_id: attributeId,

        is_active: desired ? "true" : "false",
      });

      updateAttributeStatusUI(attribute, data.value);

      updateAttributeProposalState(
        attribute,
        data.proposed_fields,
        data.proposed,
      );
    } catch (error) {
      showAttributeError(attribute, error.message);
    } finally {
      button.disabled = false;
    }
  }

  function updateAttributeStatusUI(attribute, value) {
    const active = normaliseValue(value) === "true";

    attribute.dataset.attributeActive = active ? "true" : "false";

    const button = attribute.querySelector("[data-attribute-status-toggle]");

    if (button) {
      button.textContent = active ? "Retire" : "Activate";
    }

    const editorStatus = attribute.querySelector(
      "[data-attribute-editor-status]",
    );

    if (editorStatus) {
      editorStatus.replaceChildren();

      const pill = document.createElement("span");

      pill.className =
        "model-status-pill " +
        (active ? "model-status-active" : "model-status-retired");

      const icon = document.createElement("i");

      icon.className = active ? "bi bi-check-circle" : "bi bi-archive";

      pill.appendChild(icon);

      pill.appendChild(
        document.createTextNode(active ? " Active" : " Retired"),
      );

      editorStatus.appendChild(pill);
    }
  }

  function applyAttributeValues(attribute, values) {
    const input = function (name) {
      return attribute.querySelector(`[name="${name}"]`);
    };

    const name = input("attribute_name");

    const key = input("attribute_key");

    const dataType = input("attribute_data_type");

    const description = input("attribute_description");

    const sortOrder = input("attribute_sort_order");

    const required = input("attribute_required");

    const nullable = input("attribute_nullable");

    writeInputValue(name, values.name);

    writeInputValue(key, values.key);

    writeInputValue(dataType, values.data_type);

    writeInputValue(description, values.description);

    writeInputValue(sortOrder, values.sort_order);

    if (required) {
      required.checked = normaliseValue(values.required) === "true";
    }

    if (nullable) {
      nullable.checked = normaliseValue(values.nullable) === "true";
    }

    updateAttributeStatusUI(attribute, values.is_active);

    const nameDisplay = attribute.querySelector(
      ".model-object-type-attribute-name",
    );

    const keyDisplay = attribute.querySelector("[data-attribute-key]");

    const typeDisplay = attribute.querySelector("[data-attribute-data-type]");

    const requiredDisplay = attribute.querySelector(
      "[data-attribute-required]",
    );

    const nullableDisplay = attribute.querySelector(
      "[data-attribute-nullable]",
    );

    const descriptionDisplay = attribute.querySelector(
      "[data-attribute-description]",
    );

    if (nameDisplay) {
      nameDisplay.textContent = values.name || "Not defined";
    }

    if (keyDisplay) {
      keyDisplay.textContent = values.key || "";
    }

    if (typeDisplay) {
      typeDisplay.textContent = formatDataType(values.data_type);
    }

    if (requiredDisplay) {
      requiredDisplay.textContent =
        normaliseValue(values.required) === "true" ? "Required" : "Optional";
    }

    if (nullableDisplay) {
      nullableDisplay.textContent =
        normaliseValue(values.nullable) === "true"
          ? "Nullable"
          : "Not nullable";
    }

    if (descriptionDisplay) {
      descriptionDisplay.textContent = values.description || "";

      descriptionDisplay.hidden = !values.description;
    }

    if (dataType) {
      setChoiceSectionVisibility(dataType);
      updateDefaultValueVisibility(dataType);
      writeDefaultValue(attribute, values);
    }

    const choiceSection = attribute.querySelector("[data-choice-section]");

    if (choiceSection) {
      const list = choiceSection.querySelector("[data-choice-list]");

      if (list) {
        list.innerHTML = "";
      }

      let choices = [];

      try {
        const config = JSON.parse(values.config || "{}");

        choices = Array.isArray(config.choices) ? config.choices : [];
      } catch (error) {
        choices = [];
      }

      choices.forEach(function (choice) {
        addChoiceRow(choiceSection, choice);
      });
    }
  }

  function updateAttributeProposalState(attribute, proposedFields, proposed) {
    const isProposed = Boolean(
      proposed ||
      (proposedFields && Object.values(proposedFields).some(Boolean)),
    );

    attribute.dataset.attributeProposed = isProposed ? "true" : "false";

    const indicator = attribute.querySelector(
      "[data-attribute-proposal-indicator]",
    );

    const discard = attribute.querySelector("[data-discard-attribute]");

    if (indicator) {
      indicator.hidden = !isProposed;
    }

    if (discard) {
      discard.hidden = !isProposed;
    }
  }

  function formatDataType(value) {
    const labels = {
      text: "Text",

      number: "Number",

      boolean: "Boolean",

      date: "Date",

      datetime: "Date & time",

      choice: "Choice",

      url: "URL",
    };

    return labels[value] || value || "";
  }

  /* ============================================================
       New Attribute
       ============================================================ */

  function openNewAttribute(root) {
    const editor = root.querySelector("[data-new-attribute-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = false;

    const input = editor.querySelector('[name="attribute_name"]');

    if (input) {
      input.focus();
    }
  }

  function closeNewAttribute(root) {
    const editor = root.querySelector("[data-new-attribute-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = true;

    clearNewAttributeForm(editor);
  }

  async function saveNewAttribute(root, button) {
    const editor = root.querySelector("[data-new-attribute-editor]");

    if (!editor) {
      return;
    }

    const error = editor.querySelector("[data-new-attribute-error]");

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showElementError(error, "Unable to save: CSRF token unavailable.");

      return;
    }

    clearElementError(error);

    button.disabled = true;

    try {
      const values = collectAttributeValues(editor);

      values.action = "create_attribute";

      await postForm(root.dataset.updateUrl, csrfToken, values);

      window.location.reload();
    } catch (errorValue) {
      showElementError(error, errorValue.message);
    } finally {
      button.disabled = false;
    }
  }

  function clearNewAttributeForm(editor) {
    editor
      .querySelectorAll("input, textarea, select")
      .forEach(function (input) {
        if (input.type === "checkbox") {
          input.checked = false;
        } else if (input.name === "attribute_data_type") {
          input.value = "text";
        } else if (input.name === "attribute_sort_order") {
          input.value = "0";
        } else {
          input.value = "";
        }
      });
  }

  function updateAttributeEmptyState(root) {
    const list = root.querySelector("[data-attribute-list]");

    if (!list) {
      return;
    }

    const attributes = list.querySelectorAll(
      ".model-object-type-attribute" + ":not([data-new-attribute-editor])",
    );

    const empty = list.querySelector("[data-attribute-empty]");

    if (attributes.length === 0 && !empty) {
      const element = document.createElement("div");

      element.className = "model-editor-empty";

      element.dataset.attributeEmpty = "";

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

      const newEditor = list.querySelector("[data-new-attribute-editor]");

      if (newEditor) {
        list.insertBefore(element, newEditor);
      } else {
        list.appendChild(element);
      }
    }
  }

  /* ============================================================
       ObjectType index discard
       ============================================================ */

  async function discardObjectTypeProposal(button) {
    const objectTypeId = button.dataset.objectTypeId;

    if (!objectTypeId) {
      console.error("ObjectType proposal discard: ID missing.");

      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("ObjectType proposal discard: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(window.location.href, csrfToken, {
        action: "discard_object_type_proposal",

        object_type_id: objectTypeId,
      });

      if (!data.success) {
        throw new Error(
          data.error || "Unable to discard object type proposal.",
        );
      }

      window.location.reload();
    } catch (error) {
      console.error("ObjectType proposal discard failed:", error);

      button.disabled = false;
    }
  }

  /* ============================================================
       RelationshipType index discard
       ============================================================ */

  async function discardRelationshipTypeProposal(button) {
    const relationshipTypeId = button.dataset.relationshipTypeId;

    if (!relationshipTypeId) {
      console.error("RelationshipType proposal discard: ID missing.");

      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("RelationshipType proposal discard: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      const data = await postForm(window.location.href, csrfToken, {
        action: "discard_relationship_type_proposal",

        relationship_type_id: relationshipTypeId,
      });

      if (!data.success) {
        throw new Error(
          data.error || "Unable to discard relationship type proposal.",
        );
      }

      window.location.reload();
    } catch (error) {
      console.error("RelationshipType proposal discard failed:", error);

      button.disabled = false;
    }
  }

  /* ============================================================
       RelationshipType rules
       ============================================================ */

  function collectRuleValues(editor) {
    return {
      subject_type_id: editor.querySelector('[name="subject_type_id"]').value,

      object_type_id: editor.querySelector('[name="object_type_id"]').value,

      subject_minimum: editor.querySelector('[name="subject_minimum"]').value,

      subject_maximum: editor.querySelector('[name="subject_maximum"]').value,

      object_minimum: editor.querySelector('[name="object_minimum"]').value,

      object_maximum: editor.querySelector('[name="object_maximum"]').value,
    };
  }

  function openRule(rule) {
    const editor = rule.querySelector("[data-rule-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = false;

    const firstInput = editor.querySelector("input, select");

    if (firstInput) {
      firstInput.focus();
    }
  }

  function closeRule(rule) {
    const editor = rule.querySelector("[data-rule-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = true;

    clearElementError(editor.querySelector("[data-rule-error]"));
  }

  async function saveRule(root, button) {
    const rule = button.closest(".model-relationship-rule");

    if (!rule) {
      return;
    }

    const ruleId = rule.dataset.ruleId;

    const editor = rule.querySelector("[data-rule-editor]");

    if (!ruleId || !editor) {
      return;
    }

    const error = editor.querySelector("[data-rule-error]");

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showElementError(error, "Unable to save: CSRF token unavailable.");

      return;
    }

    clearElementError(error);

    button.disabled = true;

    try {
      const values = collectRuleValues(editor);

      values.action = "save_rule";

      values.rule_id = ruleId;

      await postForm(root.dataset.updateUrl, csrfToken, values);

      window.location.reload();
    } catch (errorValue) {
      showElementError(error, errorValue.message);

      button.disabled = false;
    }
  }

  async function discardRule(root, button) {
    const ruleId = button.dataset.ruleId;

    if (!ruleId) {
      return;
    }

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      console.error("Rule discard: CSRF unavailable.");

      return;
    }

    button.disabled = true;

    try {
      await postForm(root.dataset.updateUrl, csrfToken, {
        action: "discard_rule",

        rule_id: ruleId,
      });

      window.location.reload();
    } catch (error) {
      console.error("Rule discard failed:", error);

      button.disabled = false;
    }
  }

  function openNewRule(root) {
    const editor = root.querySelector("[data-new-rule-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = false;

    const firstInput = editor.querySelector("[data-new-rule-subject]");

    if (firstInput) {
      firstInput.focus();
    }
  }

  function closeNewRule(root) {
    const editor = root.querySelector("[data-new-rule-editor]");

    if (!editor) {
      return;
    }

    editor.hidden = true;

    clearElementError(editor.querySelector("[data-new-rule-error]"));

    clearNewRuleForm(editor);
  }

  async function saveNewRule(root, button) {
    const editor = root.querySelector("[data-new-rule-editor]");

    if (!editor) {
      return;
    }

    const error = editor.querySelector("[data-new-rule-error]");

    const csrfToken = getCsrfToken();

    if (!csrfToken) {
      showElementError(error, "Unable to save: CSRF token unavailable.");

      return;
    }

    clearElementError(error);

    button.disabled = true;

    try {
      const values = collectRuleValues(editor);

      values.action = "create_rule";

      await postForm(root.dataset.updateUrl, csrfToken, values);

      window.location.reload();
    } catch (errorValue) {
      showElementError(error, errorValue.message);

      button.disabled = false;
    }
  }

  function clearNewRuleForm(editor) {
    editor.querySelectorAll("input, select").forEach(function (input) {
      if (input.type === "checkbox") {
        input.checked = false;
      } else if (
        input.name === "subject_minimum" ||
        input.name === "object_minimum"
      ) {
        input.value = "0";
      } else {
        input.value = "";
      }
    });
  }

  /* ============================================================
       Request
       ============================================================ */

  async function postForm(url, csrfToken, values) {
    if (!csrfToken) {
      throw new Error("CSRF token unavailable.");
    }

    const response = await fetch(url, {
      method: "POST",

      headers: {
        "X-CSRFToken": csrfToken,

        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",

        "X-Requested-With": "XMLHttpRequest",
      },

      body: new URLSearchParams(values),
    });

    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
      throw new Error(`Unexpected server response (${response.status}).`);
    }

    const data = await response.json();

    if (!response.ok || !data.success) {
      let message = data.error;

      if (!message && data.errors) {
        message = Object.entries(data.errors)
          .map(function ([field, error]) {
            return `${field}: ${error}`;
          })
          .join(" ");
      }

      throw new Error(message || "The proposed change could not be saved.");
    }

    applySidebarHtml(data.sidebar_html);

    return data;
  }

  /* ============================================================
       Sidebar refresh
       ============================================================

       The server attaches a freshly-rendered `_sidebar.html` fragment
       (built from the same get_model_context() source of truth used
       for a full page load) to every successful proposal-editing
       response. Swapping it in keeps the sidebar's proposal list,
       change counts, and section state current without a page
       reload and without any separate proposal state tracked here.
       ============================================================ */

  function applySidebarHtml(html) {
    if (!html) {
      return;
    }

    const current = document.querySelector(".model-sidebar");

    if (!current) {
      return;
    }

    const wrapper = document.createElement("div");

    wrapper.innerHTML = html.trim();

    const next = wrapper.querySelector(".model-sidebar");

    if (!next) {
      return;
    }

    // Child groups render collapsed; re-open any the user had open so an
    // edit doesn't snap them shut. Clicking reuses sidebar.js's handler.
    const groupToggle = (group) =>
      group.querySelector(":scope > .model-nav-parent-row > .model-nav-toggle");

    const wasOpen = Array.from(current.querySelectorAll(".model-nav-group")).map(
      (group) => groupToggle(group)?.getAttribute("aria-expanded") === "true",
    );

    current.replaceWith(next);

    next.querySelectorAll(".model-nav-group").forEach((group, index) => {
      const toggle = groupToggle(group);

      if (wasOpen[index] && toggle) {
        toggle.click();
      }
    });
  }

  /* ============================================================
       Error helpers
       ============================================================ */

  function showFieldError(field, message) {
    const element = field.querySelector("[data-proposal-error]");

    if (!element) {
      console.error(message);

      return;
    }

    element.textContent = message;

    element.hidden = false;
  }

  function clearFieldError(field) {
    clearElementError(field.querySelector("[data-proposal-error]"));
  }

  function showAttributeError(attribute, error) {
    const element = attribute.querySelector("[data-attribute-error]");

    if (!element) {
      console.error(error.message);

      return;
    }

    element.textContent = error.message;

    element.hidden = false;
  }

  function showElementError(element, message) {
    if (!element) {
      console.error(message);

      return;
    }

    element.textContent = message;

    element.hidden = false;
  }

  function clearElementError(element) {
    if (!element) {
      return;
    }

    element.textContent = "";

    element.hidden = true;
  }

  function clearAttributeError(attribute) {
    clearElementError(attribute.querySelector("[data-attribute-error]"));
  }

  function normaliseValue(value) {
    if (value === null || value === undefined) {
      return "";
    }

    return String(value);
  }

  /* ============================================================
       Data index — click row to open record
       ============================================================ */

  document.querySelectorAll(".model-data-row[data-href]").forEach(function (row) {
    row.addEventListener("click", function (event) {
      if (event.target.closest("a, button")) {
        return;
      }

      window.location.href = row.dataset.href;
    });
  });
});
