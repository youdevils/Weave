/**
 * Local search and Active | All filtering for the model index pages
 * (object types, relationship types, and the two data type choosers).
 *
 * Every item is already rendered, so filtering only toggles the `hidden`
 * attribute. State is page-local: it defaults to Active on load and is not
 * persisted or shared between pages.
 */

export const FILTER_ACTIVE = "active";
export const FILTER_ALL = "all";

/** Case-insensitive match: every whitespace-separated token must appear. */
export function matchesQuery(haystack, query) {
  const tokens = String(query || "")
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  const text = String(haystack || "").toLowerCase();
  return tokens.every((token) => text.includes(token));
}

/** Whether an item ({ active, search }) is shown for the current view. */
export function isVisible(item, { query, filter }) {
  if (filter !== FILTER_ALL && !item.active) return false;
  return matchesQuery(item.search, query);
}

/**
 * What to show when nothing is visible.
 * `retiredMatches` is how many inactive items match the query but are hidden
 * by the Active filter.
 */
export function emptyState({ query, filter, noun, retiredMatches = 0 }) {
  const trimmed = String(query || "").trim();
  const hiddenByFilter = filter !== FILTER_ALL;

  if (trimmed) {
    return {
      message: `No ${noun} match "${trimmed}".`,
      showClear: true,
      showAll: hiddenByFilter && retiredMatches > 0,
    };
  }

  return {
    message: `No active ${noun}.`,
    showClear: false,
    showAll: hiddenByFilter,
  };
}

/** Wire one [data-model-index] root. */
export function initIndex(root) {
  if (!root) return;

  const noun = root.dataset.noun || "items";
  const input = root.querySelector("[data-index-search]");
  const clearButton = root.querySelector("[data-index-clear]");
  const filterButtons = Array.from(
    root.querySelectorAll("[data-index-filter-value]"),
  );
  const noResults = root.querySelector("[data-index-noresults]");
  const message = root.querySelector("[data-index-noresults-message]");
  const clearAction = root.querySelector('[data-index-action="clear-search"]');
  const showAllAction = root.querySelector('[data-index-action="show-all"]');

  const items = Array.from(root.querySelectorAll("[data-index-item]")).map(
    (element) => ({
      element,
      active: element.dataset.active === "true",
      search: element.dataset.search || "",
    }),
  );

  let filter = FILTER_ACTIVE;

  function render() {
    const query = input ? input.value : "";
    let visibleCount = 0;
    let retiredMatches = 0;

    items.forEach((item) => {
      const visible = isVisible(item, { query, filter });
      item.element.hidden = !visible;
      if (visible) visibleCount += 1;
      else if (!item.active && matchesQuery(item.search, query)) {
        retiredMatches += 1;
      }
    });

    filterButtons.forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        button.dataset.indexFilterValue === filter ? "true" : "false",
      );
    });

    if (clearButton) clearButton.hidden = !query;

    if (!noResults) return;

    if (visibleCount > 0) {
      noResults.hidden = true;
      return;
    }

    const state = emptyState({ query, filter, noun, retiredMatches });
    if (message) message.textContent = state.message;
    if (clearAction) clearAction.hidden = !state.showClear;
    if (showAllAction) showAllAction.hidden = !state.showAll;
    noResults.hidden = false;
  }

  function clearSearch() {
    if (!input) return;
    input.value = "";
    input.focus();
    render();
  }

  function setFilter(value) {
    filter = value === FILTER_ALL ? FILTER_ALL : FILTER_ACTIVE;
    render();
  }

  if (input) {
    input.addEventListener("input", render);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && input.value) {
        event.preventDefault();
        clearSearch();
      }
    });
  }

  if (clearButton) clearButton.addEventListener("click", clearSearch);
  if (clearAction) clearAction.addEventListener("click", clearSearch);
  if (showAllAction) {
    showAllAction.addEventListener("click", () => setFilter(FILTER_ALL));
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () =>
      setFilter(button.dataset.indexFilterValue),
    );
  });

  render();
}

if (typeof document !== "undefined") {
  document
    .querySelectorAll("[data-model-index]")
    .forEach((root) => initIndex(root));
}
