/**
 * Details-panel data for a selected Object or Relationship: the JS counterpart
 * of ``model.services.model_graph.details``. Read-only. When a projection is
 * supplied, items carry ``inView`` flags so the UI can tell what the current
 * filters are hiding.
 */

import { compareStrings, isPopulated, pyStr } from "./text.js";

/** How an attribute value is shown to people; null when it is not populated. */
export function displayValue(dataType, value) {
  if (!isPopulated(value)) return null;
  if (dataType === "boolean") return value === true || String(value).toLowerCase() === "true" ? "Yes" : "No";
  return pyStr(value);
}

/** Every defined attribute in definition order, populated or not. */
function attributes(specs, values) {
  return specs.map((spec) => {
    const value = values[spec.key] ?? null;
    return { key: spec.key, label: spec.name, dataType: spec.dataType, value, display: displayValue(spec.dataType, value) };
  });
}

const inView = (projection, id) => (projection ? projection.containsObject(id) : null);

function objectRef(dataset, object, projection) {
  return {
    id: object.id,
    name: object.name,
    typeId: object.typeId,
    typeName: dataset.objectTypes.get(object.typeId).name,
    isProposed: false,
    inView: inView(projection, object.id),
  };
}

export function objectDetails(dataset, objectId, projection = null) {
  const object = dataset.object(objectId);
  if (!object) return null;

  const objectType = dataset.objectTypes.get(object.typeId);
  const groups = new Map();
  const hiddenCounterparts = new Set();

  for (const relationship of dataset.relationshipsOf(object.id)) {
    const outgoing = relationship.sourceId === object.id;
    const counterpart = dataset.objects.get(outgoing ? relationship.targetId : relationship.sourceId);
    const relationshipType = dataset.relationshipTypes.get(relationship.typeId);

    const item = {
      relationshipId: relationship.id,
      direction: outgoing ? "outgoing" : "incoming",
      isProposed: false,
      inView: projection ? projection.containsRelationship(relationship.id) : null,
      counterpart: objectRef(dataset, counterpart, projection),
      attributes: attributes(relationshipType.attributes, relationship.attributes).filter((a) => a.display),
    };
    if (!groups.has(relationshipType.id)) groups.set(relationshipType.id, []);
    groups.get(relationshipType.id).push(item);

    if (counterpart.id !== object.id && inView(projection, counterpart.id) === false) hiddenCounterparts.add(counterpart.id);
  }

  const sortKeyOf = (item) => dataset.objects.get(item.counterpart.id).sortKey;

  return {
    kind: "object",
    id: object.id,
    name: object.name,
    description: object.description,
    type: { id: objectType.id, key: objectType.key, name: objectType.name },
    isProposed: false,
    isCreated: false,
    inView: inView(projection, object.id),
    attributes: attributes(objectType.attributes, object.attributes),
    relationships: [...dataset.relationshipTypes.keys()]
      .filter((typeId) => groups.has(typeId))
      .map((typeId) => ({
        type: { id: typeId, name: dataset.relationshipTypes.get(typeId).name },
        items: groups
          .get(typeId)
          .sort((a, b) => compareStrings(sortKeyOf(a), sortKeyOf(b)) || compareStrings(a.relationshipId, b.relationshipId)),
      })),
    connectionCount: dataset.degree(object.id),
    hiddenConnectionIds: [...hiddenCounterparts],
  };
}

function cardinality(rule) {
  if (!rule) return null;
  return {
    subject: { minimum: rule.subjectMinimum, maximum: rule.subjectMaximum },
    object: { minimum: rule.objectMinimum, maximum: rule.objectMaximum },
  };
}

export function relationshipDetails(dataset, relationshipId, projection = null) {
  const relationship = dataset.relationship(relationshipId);
  if (!relationship) return null;

  const type = dataset.relationshipTypes.get(relationship.typeId);
  return {
    kind: "relationship",
    id: relationship.id,
    type: { id: type.id, key: type.key, name: type.name },
    source: objectRef(dataset, dataset.objects.get(relationship.sourceId), projection),
    target: objectRef(dataset, dataset.objects.get(relationship.targetId), projection),
    attributes: attributes(type.attributes, relationship.attributes),
    validFrom: relationship.validFrom,
    validTo: relationship.validTo,
    cardinality: cardinality(dataset.ruleFor(relationship)),
    isProposed: false,
    isCreated: false,
    inView: projection ? projection.containsRelationship(relationship.id) : null,
  };
}
