import test from "node:test";
import assert from "node:assert/strict";

import {
  applyCanvasBackground,
  applyGroups,
  buildBody,
  collectValues,
  describeField,
  groupsForScope,
  initAppearanceForm,
  postAppearance,
  previewFor,
} from "../static/model/js/appearance/appearance-form.js";

function field(key, value, overridden = false) {
  return { key, value, inherited: "", overridden };
}

// --------------------------------------------------------------------------
// Pure helpers
// --------------------------------------------------------------------------

test("describeField marks overridden fields as customised with a reset", () => {
  const view = describeField(field("shape", "square", true), { shape: "square" });

  assert.equal(view.status, "Customised");
  assert.equal(view.resetVisible, true);
});

test("describeField shows the inherited label when not overridden", () => {
  assert.equal(describeField(field("shape", "box"), {}).status, "Default");
  assert.equal(describeField(field("shape", "box"), {}, { inheritedLabel: "Inherited" }).status, "Inherited");
  assert.equal(describeField(field("shape", "box"), {}).resetVisible, false);
});

test("size is disabled for text-inside shapes and enabled for marker shapes and icons", () => {
  for (const shape of ["box", "ellipse", "circle", "database"]) {
    const view = describeField(field("size", 25), { shape, icon: "" });
    assert.equal(view.disabled, true, shape);
    assert.ok(view.reason.length > 0);
  }
  for (const shape of ["dot", "square", "diamond", "triangle", "hexagon", "star"]) {
    assert.equal(describeField(field("size", 25), { shape, icon: "" }).disabled, false, shape);
  }
  assert.equal(describeField(field("size", 25), { shape: "box", icon: "person" }).disabled, false);
});

test("only the size field is ever disabled", () => {
  assert.equal(describeField(field("border", "#000000"), { shape: "box" }).disabled, false);
});

test("collectValues flattens groups into a key-value map", () => {
  const values = collectValues([
    { label: "A", fields: [field("shape", "box"), field("size", 25)] },
    { label: "B", fields: [field("border", "#4C6EF5")] },
  ]);

  assert.deepEqual(values, { shape: "box", size: 25, border: "#4C6EF5" });
  assert.deepEqual(collectValues(undefined), {});
});

test("groupsForScope picks a scope from a Customise response", () => {
  const form = {
    scopes: [
      { scope: "theme", groups: ["theme-groups"] },
      { scope: "object", groups: ["object-groups"] },
    ],
  };

  assert.deepEqual(groupsForScope("object", form), ["object-groups"]);
  assert.deepEqual(groupsForScope("relationship", form), []);
});

test("groupsForScope uses the single group set of a type-editor response", () => {
  assert.deepEqual(groupsForScope("", { groups: ["g"] }), ["g"]);
  assert.deepEqual(groupsForScope("", null), []);
});

test("buildBody encodes set, reset and scope requests", () => {
  assert.equal(buildBody({ scope: "theme", field: "accent", value: "#FF0000" }), "scope=theme&field=accent&value=%23FF0000");
  assert.equal(buildBody({ field: "shape", value: "" }), "field=shape&value=");
  assert.equal(buildBody({ action: "reset_field", field: "shape" }), "action=reset_field&field=shape");
  assert.equal(buildBody({ action: "reset_all" }), "action=reset_all");
});

test("applyCanvasBackground sets the container background", () => {
  const container = { style: {} };

  applyCanvasBackground(container, "#101010");

  assert.equal(container.style.background, "#101010");
});

test("applyCanvasBackground is applied again on every update", () => {
  const container = { style: {} };

  for (const colour of ["#101010", "#FFFFFF", "#EFEFEF"]) {
    applyCanvasBackground(container, colour);
    assert.equal(container.style.background, colour);
  }
});

test("applyCanvasBackground ignores a missing container or colour", () => {
  assert.doesNotThrow(() => applyCanvasBackground(null, "#000000"));
  const container = { style: { background: "#123456" } };
  applyCanvasBackground(container, "");
  assert.equal(container.style.background, "#123456");
});

test("previewFor sketches an object type from its values", () => {
  const preview = previewFor("object_type", {
    shape: "square",
    icon: "",
    background: "#EDF2FF",
    border: "#4C6EF5",
    border_width: 2,
    font_colour: "#212529",
    font_size: 14,
    font_weight: "bold",
  });

  assert.equal(preview.shape, "square");
  assert.equal(preview.style.background, "#EDF2FF");
  assert.equal(preview.style.borderWidth, "2px");
  assert.equal(preview.style.fontWeight, "bold");
});

test("previewFor shows an icon type as an icon", () => {
  const preview = previewFor("object_type", { shape: "box", icon: "person", border_width: 1, font_size: 12 });

  assert.equal(preview.shape, "icon");
  assert.equal(preview.icon, "person");
});

test("previewFor maps relationship line styles and arrows", () => {
  const solid = previewFor("relationship_type", { colour: "#000000", width: 2, line_style: "solid", arrows: "to", label_colour: "#111111", label_size: 11 });
  const dashed = previewFor("relationship_type", { colour: "#000000", width: 2, line_style: "dashed", arrows: "both" });
  const dotted = previewFor("relationship_type", { colour: "#000000", width: 2, line_style: "dotted", arrows: "none" });

  assert.equal(solid.style.borderTopStyle, "solid");
  assert.equal(dashed.style.borderTopStyle, "dashed");
  assert.equal(dotted.style.borderTopStyle, "dotted");
  assert.equal(dashed.arrows, "both");
  assert.equal(solid.style.borderTopWidth, "2px");
  assert.equal(solid.labelStyle.color, "#111111");
});

// --------------------------------------------------------------------------
// Networking (fetch injected)
// --------------------------------------------------------------------------

function fakeFetch(response, { ok = true, calls = [] } = {}) {
  const fn = async (url, options) => {
    calls.push({ url, options });
    return { ok, json: async () => response };
  };
  fn.calls = calls;
  return fn;
}

test("postAppearance sends a CSRF-protected form POST and returns the parsed body", async () => {
  const fetchFn = fakeFetch({ success: true, form: { groups: [] } });

  const data = await postAppearance(fetchFn, "/save/", "token-123", "field=shape&value=box");

  assert.deepEqual(data, { success: true, form: { groups: [] } });
  const call = fetchFn.calls[0];
  assert.equal(call.url, "/save/");
  assert.equal(call.options.method, "POST");
  assert.equal(call.options.headers["X-CSRFToken"], "token-123");
  assert.equal(call.options.headers["Content-Type"], "application/x-www-form-urlencoded");
  assert.equal(call.options.body, "field=shape&value=box");
});

test("postAppearance throws the server's error message on rejection", async () => {
  const fetchFn = fakeFetch({ success: false, error: "Shape must be one of the available choices." }, { ok: false });

  await assert.rejects(() => postAppearance(fetchFn, "/save/", "t", "x"), /Shape must be one of the available choices\./);
});

test("postAppearance falls back to a generic message for an unparseable response", async () => {
  const fetchFn = async () => ({
    ok: false,
    json: async () => {
      throw new Error("not json");
    },
  });

  await assert.rejects(() => postAppearance(fetchFn, "/save/", "t", "x"), /Could not save/);
});

// --------------------------------------------------------------------------
// DOM glue against a tiny fake DOM
// --------------------------------------------------------------------------

function fakeElement(dataset = {}) {
  const listeners = {};
  const element = {
    dataset,
    hidden: false,
    disabled: false,
    value: "",
    textContent: "",
    _children: {},
    querySelector(selector) {
      return this._children[selector] || null;
    },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    fire(type, event) {
      return listeners[type](event);
    },
    closest() {
      return this._closest || null;
    },
  };
  return element;
}

function fakeFieldWrapper(key, initial = "") {
  const wrapper = fakeElement({ appearanceField: key });
  const control = fakeElement({});
  control.value = initial;
  control.dataset.lastValue = initial;
  const status = fakeElement();
  const reset = fakeElement();
  const note = fakeElement();
  wrapper._children = {
    "[data-appearance-control]": control,
    "[data-appearance-state]": status,
    "[data-appearance-reset]": reset,
    "[data-appearance-note]": note,
  };
  return { wrapper, control, status, reset, note };
}

test("applyGroups renders values, status, reset visibility and the size note", () => {
  const shape = fakeFieldWrapper("shape");
  const size = fakeFieldWrapper("size");
  const root = fakeElement();
  root._children = {
    '[data-appearance-field="shape"]': shape.wrapper,
    '[data-appearance-field="size"]': size.wrapper,
  };

  applyGroups(
    root,
    [{ label: "Shape", fields: [field("shape", "box", true), field("size", 25, false)] }],
    { inheritedLabel: "Inherited" },
  );

  assert.equal(shape.control.value, "box");
  assert.equal(shape.status.textContent, "Customised");
  assert.equal(shape.reset.hidden, false);
  assert.equal(shape.wrapper.dataset.overridden, "true");
  assert.equal(size.status.textContent, "Inherited");
  assert.equal(size.reset.hidden, true);
  assert.equal(size.control.disabled, true);
  assert.equal(size.note.hidden, false);
});

test("applyGroups re-enables size once a marker shape is chosen", () => {
  const shape = fakeFieldWrapper("shape");
  const size = fakeFieldWrapper("size");
  const root = fakeElement();
  root._children = {
    '[data-appearance-field="shape"]': shape.wrapper,
    '[data-appearance-field="size"]': size.wrapper,
  };

  applyGroups(root, [{ label: "Shape", fields: [field("shape", "star", true), field("size", 30)] }]);

  assert.equal(size.control.disabled, false);
  assert.equal(size.note.hidden, true);
});

test("initAppearanceForm saves a changed control and reports the response", async () => {
  const { wrapper, control } = fakeFieldWrapper("shape", "box");
  control._closest = control;
  control.closest = (selector) => (selector === "[data-appearance-control]" ? control : wrapper);
  control.value = "square";

  const csrf = fakeElement();
  csrf.value = "tok";
  const status = fakeElement();
  const root = fakeElement({ endpoint: "/type/appearance/", scope: "" });
  root._children = { "input[name=csrfmiddlewaretoken]": csrf, "[data-appearance-status]": status };

  const fetchFn = fakeFetch({ success: true, form: { groups: [] } });
  let saved = null;
  initAppearanceForm(root, { fetchFn, onSaved: (data) => (saved = data) });

  await root.fire("change", { target: control });

  assert.equal(fetchFn.calls.length, 1);
  assert.equal(fetchFn.calls[0].url, "/type/appearance/");
  assert.equal(fetchFn.calls[0].options.body, "field=shape&value=square");
  assert.equal(fetchFn.calls[0].options.headers["X-CSRFToken"], "tok");
  assert.deepEqual(saved, { success: true, form: { groups: [] } });
  assert.equal(status.textContent, "Saved");
});

test("initAppearanceForm sends the scope with Customise saves", async () => {
  const { wrapper, control } = fakeFieldWrapper("accent", "#4C6EF5");
  control.closest = (selector) => (selector === "[data-appearance-control]" ? control : wrapper);
  control.value = "#00AA00";
  const root = fakeElement({ endpoint: "/customise/", scope: "theme" });
  root._children = { "input[name=csrfmiddlewaretoken]": Object.assign(fakeElement(), { value: "t" }) };

  const fetchFn = fakeFetch({ success: true, form: { scopes: [] } });
  initAppearanceForm(root, { fetchFn });
  await root.fire("change", { target: control });

  assert.equal(fetchFn.calls[0].options.body, "scope=theme&field=accent&value=%2300AA00");
});

test("a rejected save restores the previous control value and shows the error", async () => {
  const { wrapper, control } = fakeFieldWrapper("border_width", "2");
  control.closest = (selector) => (selector === "[data-appearance-control]" ? control : wrapper);
  control.value = "99";
  const status = fakeElement();
  const root = fakeElement({ endpoint: "/type/appearance/", scope: "" });
  root._children = {
    "input[name=csrfmiddlewaretoken]": Object.assign(fakeElement(), { value: "t" }),
    "[data-appearance-status]": status,
  };

  const fetchFn = fakeFetch({ success: false, error: "Border width must be at most 8." }, { ok: false });
  let saved = false;
  initAppearanceForm(root, { fetchFn, onSaved: () => (saved = true) });
  await root.fire("change", { target: control });

  assert.equal(control.value, "2");
  assert.equal(saved, false);
  assert.equal(status.textContent, "Border width must be at most 8.");
  assert.equal(status.dataset.state, "error");
});

test("reset buttons post reset_field and reset_all", async () => {
  const { wrapper } = fakeFieldWrapper("shape", "square");
  const resetButton = fakeElement();
  resetButton.closest = (selector) => (selector === "[data-appearance-reset]" ? resetButton : wrapper);
  const resetAllButton = fakeElement();
  resetAllButton.closest = (selector) => (selector === "[data-appearance-reset-all]" ? resetAllButton : null);

  const root = fakeElement({ endpoint: "/type/appearance/", scope: "" });
  root._children = { "input[name=csrfmiddlewaretoken]": Object.assign(fakeElement(), { value: "t" }) };
  const fetchFn = fakeFetch({ success: true, form: { groups: [] } });
  initAppearanceForm(root, { fetchFn });

  await root.fire("click", { target: resetButton });
  await root.fire("click", { target: resetAllButton });

  assert.equal(fetchFn.calls[0].options.body, "action=reset_field&field=shape");
  assert.equal(fetchFn.calls[1].options.body, "action=reset_all");
});
