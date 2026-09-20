/**
 * Turns a projection into a viewer payload: the JS counterpart of
 * ``compile_model_graph``. Every visual decision was made when the bundle was
 * built (each type carries its resolved ``style``); this only assembles nodes
 * and edges around the bundle's ``graphTemplate``.
 */

import { isPopulated } from "./text.js";

function populated(specs, values) {
  const result = {};
  for (const spec of specs) if (isPopulated(values[spec.key])) result[spec.key] = values[spec.key];
  return result;
}

export function compileGraph(dataset, projection, template) {
  const nodes = projection.objectIds.map((id) => {
    const object = dataset.objects.get(id);
    const type = dataset.objectTypes.get(object.typeId);
    return {
      id: object.id,
      type_key: type.key,
      label: object.name,
      data: {
        object_type_id: type.id,
        object_type_name: type.name,
        is_proposed: false,
        is_created: false,
        attributes: populated(type.attributes, object.attributes),
      },
      style: type.style,
    };
  });

  const edges = projection.relationshipIds.map((id) => {
    const relationship = dataset.relationships.get(id);
    const type = dataset.relationshipTypes.get(relationship.typeId);
    return {
      id: relationship.id,
      relationship_type_key: type.key,
      // Direction is the relationship's: subject -> object.
      source: relationship.sourceId,
      target: relationship.targetId,
      label: type.name,
      data: {
        relationship_type_id: type.id,
        is_proposed: false,
        is_created: false,
        attributes: populated(type.attributes, relationship.attributes),
      },
      style: type.style,
    };
  });

  return { ...template, nodes, edges };
}
