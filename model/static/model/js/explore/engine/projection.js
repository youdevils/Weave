/**
 * Which part of the dataset belongs in the current graph: the JS counterpart of
 * ``model.services.model_graph.projection.project``. Pure; no DOM, no viewer.
 *
 *   - hiding an Object Type hides its objects, and so their relationships;
 *   - hiding a Relationship Type hides those relationships only;
 *   - an attribute filter constrains objects of its own type only;
 *   - ``include`` ids are brought into view explicitly and override hiding and
 *     attribute filters;
 *   - over ``limit`` objects, included ids are kept first, then the best
 *     connected, and ``truncated`` says so.
 */

import { filterMatches } from "./query.js";
import { compareStrings } from "./text.js";

function passesFilters(object, query) {
  return query.attributeFilters
    .filter((f) => f.typeId === object.typeId)
    .every((f) => filterMatches(f, object.attributes[f.key]));
}

export function project(dataset, query) {
  let hiddenByType = 0;
  let hiddenByFilter = 0;
  const matching = new Map();

  for (const object of dataset.objects.values()) {
    const included = query.include.has(object.id);
    if (query.hiddenObjectTypes.has(object.typeId)) {
      if (!included) {
        hiddenByType += 1;
        continue;
      }
    } else if (!passesFilters(object, query) && !included) {
      hiddenByFilter += 1;
      continue;
    }
    matching.set(object.id, object);
  }

  let visible = matching;
  const truncated = matching.size > query.limit;
  if (truncated) {
    const ranked = [...matching.values()].sort(
      (a, b) =>
        Number(!query.include.has(a.id)) - Number(!query.include.has(b.id)) ||
        dataset.degree(b.id) - dataset.degree(a.id) ||
        compareStrings(a.sortKey, b.sortKey) ||
        compareStrings(a.id, b.id),
    );
    visible = new Map(ranked.slice(0, query.limit).map((o) => [o.id, o]));
  }

  const relationshipIds = [...dataset.relationships.values()]
    .filter(
      (r) => !query.hiddenRelationshipTypes.has(r.typeId) && visible.has(r.sourceId) && visible.has(r.targetId),
    )
    .map((r) => r.id);

  // Keep the dataset's stable order rather than rank order.
  const objectIds = [...dataset.objects.keys()].filter((id) => visible.has(id));
  const objectSet = new Set(objectIds);
  const relationshipSet = new Set(relationshipIds);

  return {
    objectIds,
    relationshipIds,
    containsObject: (id) => objectSet.has(String(id)),
    containsRelationship: (id) => relationshipSet.has(String(id)),
    summary: {
      totalObjects: dataset.objects.size,
      totalRelationships: dataset.relationships.size,
      matchingObjects: matching.size,
      shownObjects: objectIds.length,
      shownRelationships: relationshipIds.length,
      hiddenByObjectType: hiddenByType,
      hiddenByAttributeFilter: hiddenByFilter,
      includedObjects: [...query.include].filter((id) => dataset.objects.has(id)).length,
      truncated,
      limit: query.limit,
    },
  };
}
