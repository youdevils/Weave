/**
 * The published dataset as the engine uses it: lookups and adjacency over the
 * bundle's ``dataset`` block. Pure and read-only; mirrors EffectiveDataset.
 *
 * The bundle lists objects in the dataset's stable (name, id) order and
 * relationships in id order, and the engine relies on that rather than
 * re-sorting.
 */

export function createDataset(data) {
  const objectTypes = new Map(data.objectTypes.map((t) => [t.id, t]));
  const relationshipTypes = new Map(data.relationshipTypes.map((t) => [t.id, t]));
  const objects = new Map(data.objects.map((o) => [o.id, o]));
  const relationships = new Map(data.relationships.map((r) => [r.id, r]));

  const adjacency = new Map(data.objects.map((o) => [o.id, []]));
  for (const relationship of data.relationships) {
    adjacency.get(relationship.sourceId).push(relationship);
    if (relationship.targetId !== relationship.sourceId) adjacency.get(relationship.targetId).push(relationship);
  }

  return {
    objectTypes,
    relationshipTypes,
    objects,
    relationships,
    object: (id) => objects.get(String(id)) ?? null,
    relationship: (id) => relationships.get(String(id)) ?? null,
    relationshipsOf: (id) => [...(adjacency.get(String(id)) ?? [])],
    degree: (id) => (adjacency.get(String(id)) ?? []).length,

    /** The cardinality rule matching a relationship's endpoint types, or null. */
    ruleFor(relationship) {
      const type = relationshipTypes.get(relationship.typeId);
      const source = objects.get(relationship.sourceId);
      const target = objects.get(relationship.targetId);
      return (
        type.rules.find((rule) => rule.subjectTypeId === source.typeId && rule.objectTypeId === target.typeId) ?? null
      );
    },
  };
}
