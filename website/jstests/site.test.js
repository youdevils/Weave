import assert from "node:assert/strict";
import test from "node:test";

import { DESKTOP_MIN_WIDTH, initHeader, isScrolled, nextMenuState, SCROLL_THRESHOLD } from "../static/website/js/site.js";

test("the header turns compact only after the scroll threshold", () => {
  assert.equal(isScrolled(0), false);
  assert.equal(isScrolled(SCROLL_THRESHOLD), false);
  assert.equal(isScrolled(SCROLL_THRESHOLD + 1), true);
  assert.equal(isScrolled(500, 1000), false);
});

test("the menu toggles and every closing event closes it", () => {
  assert.equal(nextMenuState(false, "toggle"), true);
  assert.equal(nextMenuState(true, "toggle"), false);

  for (const event of ["close", "escape", "link", "desktop"]) {
    assert.equal(nextMenuState(true, event), false, event);
    assert.equal(nextMenuState(false, event), false, event);
  }

  assert.equal(nextMenuState(true, "unknown"), true);
});

// A tiny fake DOM: just enough surface for initHeader.
function fakeElement({ attrs = {} } = {}) {
  const classes = new Set();
  const listeners = {};
  return {
    attrs: { ...attrs },
    listeners,
    focused: false,
    classList: {
      toggle: (name, force) => (force ? classes.add(name) : classes.delete(name)),
      contains: (name) => classes.has(name),
    },
    setAttribute(name, value) {
      this.attrs[name] = value;
    },
    hasAttribute(name) {
      return name in this.attrs;
    },
    addEventListener(type, handler) {
      (listeners[type] ??= []).push(handler);
    },
    focus() {
      this.focused = true;
    },
    fire(type, event = {}) {
      (listeners[type] ?? []).forEach((handler) => handler(event));
    },
  };
}

function setup({ hero }) {
  const header = fakeElement({ attrs: hero ? { "data-ff-hero": "" } : {} });
  const toggle = fakeElement();
  const nav = fakeElement();
  header.querySelector = (selector) => (selector === "[data-ff-menu-toggle]" ? toggle : selector === "[data-ff-nav]" ? nav : null);

  const doc = fakeElement();
  doc.querySelector = (selector) => (selector === "[data-ff-header]" ? header : null);

  const win = fakeElement();
  win.scrollY = 0;
  win.innerWidth = 400;
  win.requestAnimationFrame = (callback) => (callback(), 1);

  return { header, toggle, nav, doc, win };
}

test("a hero header becomes compact on scroll and quiet again at the top", () => {
  const { header, doc, win } = setup({ hero: true });
  initHeader(doc, win);

  assert.equal(header.classList.contains("is-scrolled"), false);

  win.scrollY = 200;
  win.fire("scroll");
  assert.equal(header.classList.contains("is-scrolled"), true);

  win.scrollY = 0;
  win.fire("scroll");
  assert.equal(header.classList.contains("is-scrolled"), false);
});

test("a non-hero header is left alone by scrolling (it is compact from the server)", () => {
  const { header, doc, win } = setup({ hero: false });
  initHeader(doc, win);

  win.scrollY = 200;
  win.fire("scroll");

  assert.equal(header.classList.contains("is-scrolled"), false);
});

test("the mobile menu opens, reports its state, and closes on link, Escape and desktop width", () => {
  const { header, toggle, nav, doc, win } = setup({ hero: false });
  initHeader(doc, win);

  toggle.fire("click");
  assert.equal(header.classList.contains("is-open"), true);
  assert.equal(toggle.attrs["aria-expanded"], "true");
  assert.equal(toggle.attrs["aria-label"], "Close menu");

  nav.fire("click", { target: { closest: (selector) => (selector === "a" ? {} : null) } });
  assert.equal(header.classList.contains("is-open"), false);
  assert.equal(toggle.attrs["aria-expanded"], "false");

  toggle.fire("click");
  doc.fire("keydown", { key: "Escape" });
  assert.equal(header.classList.contains("is-open"), false);
  assert.equal(toggle.focused, true, "focus returns to the toggle");

  toggle.fire("click");
  win.innerWidth = DESKTOP_MIN_WIDTH;
  win.fire("resize");
  assert.equal(header.classList.contains("is-open"), false);
});

test("clicks that are not on a link do not close the menu", () => {
  const { header, toggle, nav, doc, win } = setup({ hero: false });
  initHeader(doc, win);

  toggle.fire("click");
  nav.fire("click", { target: { closest: () => null } });

  assert.equal(header.classList.contains("is-open"), true);
});

test("a page without a header is a no-op", () => {
  const doc = fakeElement();
  doc.querySelector = () => null;

  assert.equal(initHeader(doc, fakeElement()), null);
});
