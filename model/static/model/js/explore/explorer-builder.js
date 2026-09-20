/**
 * Reads the attribute-filter builder (rendered by renderFilterBuilder) into a
 * filter document. Shared by the Explorer and the Publishing scope panel so the
 * two build filters identically.
 */

/**
 * @param {Element} container  the element holding the rendered builder
 * @returns {{filter: object} | {error: string} | null}  null when there is no builder to read
 */
export function readFilterBuilder(container) {
  const builder = container.querySelector(".model-explorer-builder");
  if (!builder) return null;
  const { typeId, key, op } = builder.dataset;
  let value;

  if (op === "in") {
    value = [...builder.querySelectorAll("[data-builder-value]:checked")].map((box) => box.dataset.builderValue);
    if (value.length === 0) return { error: "Choose at least one value." };
  } else if (op === "contains") {
    value = builder.querySelector("[data-builder-text]").value.trim();
    if (!value) return { error: "Enter some text to match." };
  } else {
    const min = builder.querySelector("[data-builder-min]").value;
    const max = builder.querySelector("[data-builder-max]").value;
    if (!min && !max) return { error: "Enter a minimum, a maximum, or both." };
    value = { min: min || null, max: max || null };
  }
  return { filter: { type_id: typeId, key, op, value } };
}
