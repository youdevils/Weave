"""
Deterministic identity resolution against canonical Objects.

Resolution is by exact, explicit identity only:

  * an OnyxJar Object ID (a UUID), or
  * the value of one explicitly chosen attribute of an object type.

There is no name matching and no fuzzy matching. Only the canonical `Object`
table is read (one query per object type involved); no proposal is consulted.
Canonical stored values are compared as they are and never altered.
"""

from collections import defaultdict

from ingestion.services import coercion
from ingestion.services.mapping import BY_ID
from ingestion.services.plan import identity_key, parse_uuid, snippet
from model.models.object import Object


class AttributeIndex:
    """
    identity-key -> ids of the objects (of one type) whose attribute has that
    value. Inactive objects are included: they are still the same record.
    """

    def __init__(self, model, object_type_id, attribute_key):
        self.attribute_key = attribute_key
        self._ids = defaultdict(list)

        rows = Object.objects.filter(
            model=model,
            object_type_id=object_type_id,
        ).values_list("id", "attributes")

        for object_id, attributes in rows:
            key = identity_key((attributes or {}).get(attribute_key))

            if key is not None:
                self._ids[key].append(object_id)

    def find(self, value):
        key = identity_key(value)

        return list(self._ids.get(key, ())) if key is not None else []


class EndpointResolver:
    """
    Resolves one relationship endpoint column to an existing canonical Object.

    `resolve(cell)` returns (object_id, problem) where exactly one is None:
    a blank cell, an unknown or ambiguous value, or an id from another model
    (indistinguishable from a missing one) is a blocking problem, never a guess.
    """

    def __init__(self, model, entry, label, object_type_specs, cells):
        self.entry = entry
        self.label = label
        self._model = model
        self._known_ids = set()
        self._index = None
        self._attribute = None

        if entry.by == BY_ID:
            ids = {parse_uuid(cell) for cell in cells if not coercion.is_blank(cell)}
            ids.discard(None)

            if ids:
                self._known_ids = set(
                    Object.objects.filter(model=model, id__in=ids).values_list("id", flat=True)
                )

        else:
            spec = object_type_specs[entry.object_type_id]
            self._attribute = spec.attribute(entry.by_attribute_key)
            self._type_name = spec.name
            self._index = AttributeIndex(model, entry.object_type_id, self._attribute.key)

    def resolve(self, cell):

        if coercion.is_blank(cell):
            return None, ("missing_endpoint", f"The {self.label} is blank.")

        if self._index is None:
            return self._resolve_id(cell)

        return self._resolve_attribute(cell)

    def _resolve_id(self, cell):

        object_id = parse_uuid(cell)

        if object_id is None:
            return None, (
                "invalid_endpoint_id",
                f"The {self.label} '{snippet(cell)}' is not a valid OnyxJar Object ID.",
            )

        if object_id not in self._known_ids:
            return None, (
                "unresolved_endpoint",
                f"No object with id '{snippet(cell)}' exists in this model (the {self.label}).",
            )

        return object_id, None

    def _resolve_attribute(self, cell):

        coerced = coercion.coerce_attribute_cell(self._attribute.data_type, cell)

        if not coerced.converted or identity_key(coerced.value) is None:
            return None, (
                "invalid_endpoint_value",
                f"The {self.label} '{snippet(cell)}' cannot be read as a "
                f"{self._attribute.name} value.",
            )

        matches = self._index.find(coerced.value)

        if not matches:
            return None, (
                "unresolved_endpoint",
                f"No {self._type_name} has {self._attribute.name} '{snippet(coerced.value)}' "
                f"(the {self.label}).",
            )

        if len(matches) > 1:
            return None, (
                "ambiguous_endpoint",
                f"{len(matches)} {self._type_name} objects have {self._attribute.name} "
                f"'{snippet(coerced.value)}' (the {self.label}).",
            )

        return matches[0], None
