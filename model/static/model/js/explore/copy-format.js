/**
 * A human-readable, plain-text/HTML extract of a selected object for the
 * clipboard: name, type, its own populated attributes, and its directly
 * connected objects (one hop), grouped by relationship type. Not a model
 * export: no ids, no proposal/history or evidence metadata, no recursion
 * past the directly connected objects.
 *
 * Only usable where a ``dataset`` is available in memory (the published
 * Explorer), since a connected object's own attributes are not part of the
 * shared ``objectDetails()`` contract (see engine/details.js) and are looked
 * up here directly.
 */

import { displayValue } from "./engine/details.js";
import { escapeHtml } from "./explorer-render.js";

function counterpartAttributes(dataset, counterpartId) {
  const object = dataset.objects.get(counterpartId);
  if (!object) return [];
  const type = dataset.objectTypes.get(object.typeId);
  return type.attributes.map((spec) => ({
    label: spec.name,
    display: displayValue(spec.dataType, object.attributes[spec.key] ?? null),
  }));
}

const withDisplay = (attributes) => attributes.filter((a) => a.display !== null);

export function buildObjectCopyText(details, dataset) {
  const lines = [`# ${details.name}`, "", `Type: ${details.type.name}`];

  const ownAttributes = withDisplay(details.attributes);
  if (ownAttributes.length) {
    lines.push("", "## Attributes", ...ownAttributes.map((a) => `- ${a.label}: ${a.display}`));
  }

  if (details.relationships.length) {
    lines.push("", "## Connected Objects");
    for (const group of details.relationships) {
      lines.push("", `### ${group.type.name}`);
      for (const item of group.items) {
        lines.push("", `#### ${item.counterpart.name}`, `Type: ${item.counterpart.typeName}`);
        const attributes = withDisplay(counterpartAttributes(dataset, item.counterpart.id));
        lines.push(...attributes.map((a) => `- ${a.label}: ${a.display}`));
      }
    }
  }

  return `${lines.join("\n")}\n`;
}

function attributeListHtml(attributes) {
  if (!attributes.length) return "";
  const items = attributes.map((a) => `<li><strong>${escapeHtml(a.label)}:</strong> ${escapeHtml(a.display)}</li>`).join("");
  return `<ul>${items}</ul>`;
}

export function buildObjectCopyHtml(details, dataset) {
  const parts = [`<h1>${escapeHtml(details.name)}</h1>`, `<p><em>Type: ${escapeHtml(details.type.name)}</em></p>`];

  const ownAttributes = withDisplay(details.attributes);
  if (ownAttributes.length) {
    parts.push("<h2>Attributes</h2>", attributeListHtml(ownAttributes));
  }

  if (details.relationships.length) {
    parts.push("<h2>Connected Objects</h2>");
    for (const group of details.relationships) {
      parts.push(`<h3>${escapeHtml(group.type.name)}</h3>`);
      for (const item of group.items) {
        const attributes = withDisplay(counterpartAttributes(dataset, item.counterpart.id));
        parts.push(
          `<h4>${escapeHtml(item.counterpart.name)}</h4>`,
          `<p><em>Type: ${escapeHtml(item.counterpart.typeName)}</em></p>`,
          attributeListHtml(attributes),
        );
      }
    }
  }

  return parts.join("\n");
}
