/**
 * Inline SVG icons for the Explorer surfaces.
 *
 * The Explorer is also shipped inside a single self-contained HTML file, so it
 * cannot depend on an icon font loaded from a CDN. Each icon is a small stroke
 * glyph on a 16 x 16 grid that inherits the surrounding text colour.
 */

const GLYPHS = {
  search: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/>',
  cursor: '<path d="M3 2l4 11 1.8-4.2L13 7z"/>',
  "slash-circle": '<circle cx="8" cy="8" r="6"/><path d="M3.8 12.2 12.2 3.8"/>',
  paperclip: '<path d="M11.5 6.5 7 11a2 2 0 0 1-2.8-2.8l4.6-4.6a3.2 3.2 0 0 1 4.5 4.5l-4.6 4.6a4.4 4.4 0 0 1-6.2-6.2"/>',
};

export const ICON_NAMES = Object.freeze(Object.keys(GLYPHS));

export function icon(name) {
  if (!Object.hasOwn(GLYPHS, name)) throw new Error(`Unknown icon: ${name}`);
  return `<svg class="weave-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${GLYPHS[name]}</svg>`;
}
