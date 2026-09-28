/**
 * Tab switching for the Customise page's "Type defaults" section.
 *
 * Presentation only: every panel (and its appearance form) stays in the DOM so
 * the appearance modules keep initialising and updating all of them. Selecting
 * a tab only changes which panel is visible.
 */

/** Index of the tab a key should move to, or null when the key is not a tab key. */
export function nextTabIndex(current, count, key) {
  if (count <= 0) return null;
  switch (key) {
    case "ArrowRight":
      return (current + 1) % count;
    case "ArrowLeft":
      return (current - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/** Wire one [role=tablist]; each tab's aria-controls names the panel it shows. */
export function initTabs(tablist) {
  if (!tablist) return;

  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));

  function select(index, { focus = false } = {}) {
    tabs.forEach((tab, position) => {
      const selected = position === index;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;

      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
    if (focus) tabs[index].focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(index));
  });

  tablist.addEventListener("keydown", (event) => {
    const current = tabs.indexOf(document.activeElement);
    if (current === -1) return;

    const next = nextTabIndex(current, tabs.length, event.key);
    if (next === null) return;

    event.preventDefault();
    select(next, { focus: true });
  });
}
