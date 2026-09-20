/**
 * Text helpers that reproduce the Python semantics the server-side Explorer
 * uses, so the offline engine sorts, folds and prints values the same way.
 */

// Python's str.casefold() differs from toLowerCase() for these characters.
const FOLD_SPECIAL = {
  "ß": "ss",
  "ẞ": "ss",
  "ς": "σ",
  "ſ": "s",
  "µ": "μ",
  "ﬀ": "ff",
  "ﬁ": "fi",
  "ﬂ": "fl",
  "ﬃ": "ffi",
  "ﬄ": "ffl",
  "ﬅ": "st",
  "ﬆ": "st",
};

/** Case-insensitive comparison key, matching Python's ``str.casefold`` for common text. */
export function casefold(value) {
  return String(value).toLowerCase().replace(/[ßẞςſµﬀ-ﬆ]/g, (ch) => FOLD_SPECIAL[ch]);
}

const SURROGATE = /[\uD800-\uDFFF]/;

/** Orders strings by code point (Python's default), not by UTF-16 code unit. */
export function compareStrings(a, b) {
  if (a === b) return 0;
  if (!SURROGATE.test(a) && !SURROGATE.test(b)) return a < b ? -1 : 1;
  const left = Array.from(a, (c) => c.codePointAt(0));
  const right = Array.from(b, (c) => c.codePointAt(0));
  const length = Math.min(left.length, right.length);
  for (let i = 0; i < length; i += 1) {
    if (left[i] !== right[i]) return left[i] < right[i] ? -1 : 1;
  }
  return left.length === right.length ? 0 : left.length < right.length ? -1 : 1;
}

/** Python's ``str(value)`` for the JSON values an attribute can hold. */
export function pyStr(value) {
  if (value === true) return "True";
  if (value === false) return "False";
  if (value === null || value === undefined) return "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** A stored attribute value counts as populated unless it is null or blank. */
export function isPopulated(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim() !== "";
  return true;
}

const NUMBER = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/;

/** Python's ``float(value)`` for numbers and numeric strings; null when it would raise. */
export function toFloat(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && NUMBER.test(value)) return Number(value);
  return null;
}

/** Characters (code points) of the text, for Python-style length and slicing. */
export const codePoints = (text) => Array.from(text);

const UUID_HEX = /^[0-9a-f]{32}$/;

/** ``str(uuid.UUID(raw))`` or null: accepts braces, ``urn:uuid:`` and missing hyphens like Python. */
export function normaliseId(raw) {
  if (raw === null || raw === undefined) return null;
  const hex = String(raw).toLowerCase().replace("urn:", "").replace("uuid:", "").replace(/[{}-]/g, "");
  if (!UUID_HEX.test(hex)) return null;
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
