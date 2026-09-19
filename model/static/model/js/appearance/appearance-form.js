/**
 * Shared behaviour for appearance controls: the Customise page and both type
 * editors render the same partial and use this same module.
 *
 * The logic is split so it can be tested without a DOM:
 *   - pure helpers (describeField, groupsForScope, buildBody, previewFor, ...)
 *   - thin DOM glue (applyGroups, initAppearanceForm)
 *
 * Nothing here knows how appearance is stored; the server returns the field
 * states and this module only renders them and posts changes back.
 */

export const TEXT_INSIDE_SHAPES = ["box", "ellipse", "circle", "database"];

/** What a field should look like given the current values of the whole form. */
export function describeField(field, values, { inheritedLabel = "Default" } = {}) {
  const overridden = Boolean(field.overridden);
  let disabled = false;
  let reason = "";

  if (field.key === "size" && !values.icon && TEXT_INSIDE_SHAPES.includes(values.shape)) {
    disabled = true;
    reason = "This shape fits its label. Size applies to dot, square, diamond, triangle, hexagon, star and icons.";
  }

  return {
    value: field.value,
    overridden,
    status: overridden ? "Customised" : inheritedLabel,
    resetVisible: overridden,
    disabled,
    reason,
  };
}

/** Flatten server groups into {key: value}. */
export function collectValues(groups) {
  const values = {};
  for (const group of groups || []) {
    for (const field of group.fields) {
      values[field.key] = field.value;
    }
  }
  return values;
}

/**
 * The groups that belong to a form root. A Customise response carries several
 * scopes; a type-editor response carries a single set of groups.
 */
export function groupsForScope(scope, form) {
  if (!form) return [];
  if (Array.isArray(form.scopes)) {
    const match = form.scopes.find((entry) => entry.scope === scope);
    return match ? match.groups : [];
  }
  return form.groups || [];
}

/** Form-encoded body for the direct-save endpoints. */
export function buildBody({ scope, field, value, action }) {
  const params = new URLSearchParams();
  if (scope) params.set("scope", scope);
  if (action) params.set("action", action);
  if (field) params.set("field", field);
  if (value !== undefined && value !== null && !action) params.set("value", String(value));
  return params.toString();
}

/** POST one change and return the parsed response; throws Error(message) on failure. */
export async function postAppearance(fetchFn, url, csrfToken, body) {
  const response = await fetchFn(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
      "X-Requested-With": "XMLHttpRequest",
    },
    body,
  });

  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }

  if (!response.ok || !data || !data.success) {
    throw new Error((data && data.error) || "Could not save this change.");
  }
  return data;
}

/** Apply the resolved graph background to the page's own container. */
export function applyCanvasBackground(container, colour) {
  if (!container || !colour) return;
  container.style.background = colour;
}

/** A rough, viewer-independent sketch of a type for the editor preview. */
export function previewFor(kind, values) {
  if (kind === "object_type") {
    return {
      kind,
      shape: values.icon ? "icon" : values.shape,
      icon: values.icon || "",
      style: {
        background: values.background,
        borderColor: values.border,
        borderWidth: `${values.border_width}px`,
        color: values.font_colour,
        fontSize: `${values.font_size}px`,
        fontWeight: values.font_weight,
      },
    };
  }

  const dash = values.line_style === "dashed" ? "dashed" : values.line_style === "dotted" ? "dotted" : "solid";
  return {
    kind,
    arrows: values.arrows,
    style: {
      color: values.colour,
      borderTopColor: values.colour,
      borderTopWidth: `${values.width}px`,
      borderTopStyle: dash,
    },
    labelStyle: { color: values.label_colour, fontSize: `${values.label_size}px` },
  };
}

// ----------------------------------------------------------------------------
// DOM glue
// ----------------------------------------------------------------------------

function readControl(control) {
  return control.value;
}

export function applyGroups(root, groups, { inheritedLabel = "Default" } = {}) {
  const values = collectValues(groups);

  for (const group of groups) {
    for (const field of group.fields) {
      const wrapper = root.querySelector(`[data-appearance-field="${field.key}"]`);
      if (!wrapper) continue;

      const view = describeField(field, values, { inheritedLabel });
      const control = wrapper.querySelector("[data-appearance-control]");
      const status = wrapper.querySelector("[data-appearance-state]");
      const reset = wrapper.querySelector("[data-appearance-reset]");
      const note = wrapper.querySelector("[data-appearance-note]");

      if (control) {
        control.value = view.value;
        control.dataset.lastValue = String(view.value);
        control.disabled = view.disabled;
      }
      if (status) status.textContent = view.status;
      if (reset) reset.hidden = !view.resetVisible;
      if (note) {
        note.textContent = view.reason;
        note.hidden = !view.reason;
      }
      wrapper.dataset.overridden = view.overridden ? "true" : "false";
    }
  }

  return values;
}

function csrfTokenFor(root) {
  const input = root.querySelector("input[name=csrfmiddlewaretoken]");
  if (input) return input.value;
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

/**
 * Wire one appearance form root. Each successful save is announced through
 * ``onSaved(data)``; the caller decides how to re-render (the Customise page
 * refreshes every scope and its preview, an editor just its own groups).
 */
export function initAppearanceForm(root, { fetchFn = globalThis.fetch, onSaved = () => {} } = {}) {
  const endpoint = root.dataset.endpoint;
  const scope = root.dataset.scope || "";
  const statusEl = root.querySelector("[data-appearance-status]");

  function setStatus(message, isError = false) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.dataset.state = isError ? "error" : message ? "saved" : "";
  }

  async function send(params, control) {
    setStatus("Saving...");
    try {
      const data = await postAppearance(fetchFn, endpoint, csrfTokenFor(root), buildBody({ scope, ...params }));
      setStatus("Saved");
      onSaved(data, root);
    } catch (error) {
      if (control && control.dataset.lastValue !== undefined) {
        control.value = control.dataset.lastValue;
      }
      setStatus(error.message, true);
    }
  }

  root.addEventListener("change", (event) => {
    const control = event.target.closest("[data-appearance-control]");
    if (!control) return;
    const wrapper = control.closest("[data-appearance-field]");
    return send({ field: wrapper.dataset.appearanceField, value: readControl(control) }, control);
  });

  root.addEventListener("click", (event) => {
    const reset = event.target.closest("[data-appearance-reset]");
    if (reset) {
      const wrapper = reset.closest("[data-appearance-field]");
      return send({ action: "reset_field", field: wrapper.dataset.appearanceField });
    }
    const resetAll = event.target.closest("[data-appearance-reset-all]");
    if (resetAll) {
      return send({ action: "reset_all" });
    }
  });
}
