/**
 * Public website behaviour: the header's scroll state and the mobile menu.
 *
 * That is all. Progressive enhancement only: every page and link works without
 * this script (pages without a hero render the compact header server-side, and
 * the mobile menu only collapses once this script has marked the page `ff-js`).
 *
 * The decisions are pure functions so they can be tested without a browser;
 * `initHeader` only wires them to the DOM.
 */

/** Scroll distance (px) after which the hero header becomes the compact one. */
export const SCROLL_THRESHOLD = 24;

/** Viewport width (px) at which the desktop navigation replaces the menu. */
export const DESKTOP_MIN_WIDTH = 861;

export function isScrolled(scrollY, threshold = SCROLL_THRESHOLD) {
  return scrollY > threshold;
}

/** The next open/closed state of the mobile menu for an event. */
export function nextMenuState(open, event) {
  switch (event) {
    case "toggle":
      return !open;
    case "close":
    case "escape":
    case "link":
    case "desktop":
      return false;
    default:
      return open;
  }
}

/**
 * Wire the header at `[data-ff-header]`. Dependencies are injectable for tests.
 * Returns a small handle (or null when the page has no header).
 */
export function initHeader(doc = document, win = window) {
  const header = doc.querySelector("[data-ff-header]");
  if (!header) return null;

  const toggle = header.querySelector("[data-ff-menu-toggle]");
  const nav = header.querySelector("[data-ff-nav]");
  const hero = header.hasAttribute("data-ff-hero");
  let open = false;
  let pending = false;

  const paintScroll = () => {
    pending = false;
    // A hero header turns compact on scroll; other pages are compact already.
    if (hero) header.classList.toggle("is-scrolled", isScrolled(win.scrollY));
  };

  const setOpen = (next) => {
    open = next;
    header.classList.toggle("is-open", open);
    toggle?.setAttribute("aria-expanded", String(open));
    toggle?.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };

  win.addEventListener(
    "scroll",
    () => {
      if (pending) return;
      pending = true;
      win.requestAnimationFrame(paintScroll);
    },
    { passive: true },
  );
  paintScroll();

  toggle?.addEventListener("click", () => setOpen(nextMenuState(open, "toggle")));

  nav?.addEventListener("click", (event) => {
    if (event.target.closest?.("a")) setOpen(nextMenuState(open, "link"));
  });

  doc.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && open) {
      setOpen(nextMenuState(open, "escape"));
      toggle?.focus();
    }
  });

  win.addEventListener("resize", () => {
    if (win.innerWidth >= DESKTOP_MIN_WIDTH && open) setOpen(nextMenuState(open, "desktop"));
  });

  return { setOpen, isOpen: () => open };
}

if (typeof document !== "undefined") {
  initHeader();
}
