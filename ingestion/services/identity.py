"""
Deterministic identity resolution against canonical Objects.

Resolution is by exact, explicit identity only:

  * an object's OnyxJar Key (its normal, user-facing identity -- scoped to
    its type, assigned by OnyxJar, never typed in by a user), or
  * the value of one explicitly chosen attribute of an object type, or
  * its Database ID (a UUID) -- kept as an advanced/optional path for files
    that already use it; not the normal column a user fills in.

There is no name matching and no fuzzy matching. Only the canonical `Object`
table is read (one query per object type involved); no proposal is consulted.
Canonical stored values are compared as they are and never altered.

A relationship endpoint column identified by key is not always pinned to one
object type: when the relationship type's rules allow more than one type on
that side, the column is resolved by searching every allowed type's keys.
Found in exactly one of them is unambiguous; found in more than one is a
blocking problem (ambiguous_endpoint_key) -- never guessed, never silently
picked. See EndpointResolver.
"""

from collections import defaultdict

from ingestion.services import coercion
from ingestion.services.mapping import BY_ID, BY_KEY
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


class KeyIndex:
    """
    key -> id of the object (of one type) with that key. Object.key is
    unique per (model, object_type) -- see uniq_object_model_type_key --
    so there is at most one match per type.
    """

    def __init__(self, model, object_type_id):
        self._ids = dict(
            Object.objects.filter(model=model, object_type_id=object_type_id).values_list("key", "id")
        )

    def find(self, value):
        object_id = self._ids.get(value.strip())
        return [object_id] if object_id is not None else []


class EndpointResolver:
    """
    Resolves one relationship endpoint column to an existing canonical Object.

    `resolve(cell)` returns (object_id, object_type_id, problem) where
    exactly one of (object_id, object_type_id) is None together with
    `problem`, or both are set and `problem` is None: a blank cell, an
    unknown or ambiguous value, or an id from another model (indistinguishable
    from a missing one) is a blocking problem, never a guess. `object_type_id`
    on a match lets the caller cross-check the resolved (subject, object)
    pair against the relationship type's own allowed-pairs rules -- each
    side resolving to *some* allowed type does not mean the pair they form
    together is one the relationship type's rules actually permit.
    """

    def __init__(self, model, entry, label, object_type_specs, cells, candidate_type_ids=None):
        self.entry = entry
        self.label = label
        self._model = model
        self._known_types = {}
        self._attribute = None
        self._key_indexes = None
        self._type_names = {}

        if entry.by == BY_ID:
            ids = {parse_uuid(cell) for cell in cells if not coercion.is_blank(cell)}
            ids.discard(None)

            if ids:
                self._known_types = dict(
                    Object.objects.filter(model=model, id__in=ids).values_list("id", "object_type_id")
                )

        elif entry.by == BY_KEY:
            type_ids = [entry.object_type_id] if entry.object_type_id else list(candidate_type_ids or ())
            self._key_indexes = {type_id: KeyIndex(model, type_id) for type_id in type_ids}
            self._type_names = {type_id: object_type_specs[type_id].name for type_id in type_ids}

        else:
            spec = object_type_specs[entry.object_type_id]
            self._attribute = spec.attribute(entry.by_attribute_key)
            self._type_name = spec.name
            self._object_type_id = entry.object_type_id
            self._index = AttributeIndex(model, entry.object_type_id, self._attribute.key)

    def resolve(self, cell):

        if coercion.is_blank(cell):
            return None, None, ("missing_endpoint", f"The {self.label} is blank.")

        if self.entry.by == BY_ID:
            return self._resolve_id(cell)

        if self.entry.by == BY_KEY:
            return self._resolve_key(cell)

        return self._resolve_attribute(cell)

    def _resolve_id(self, cell):

        object_id = parse_uuid(cell)

        if object_id is None:
            return None, None, (
                "invalid_endpoint_id",
                f"The {self.label} '{snippet(cell)}' is not a valid Database ID.",
            )

        object_type_id = self._known_types.get(object_id)

        if object_type_id is None:
            return None, None, (
                "unresolved_endpoint",
                f"No object with id '{snippet(cell)}' exists in this model (the {self.label}).",
            )

        return object_id, object_type_id, None

    def _resolve_attribute(self, cell):

        coerced = coercion.coerce_attribute_cell(self._attribute.data_type, cell)

        if not coerced.converted or identity_key(coerced.value) is None:
            return None, None, (
                "invalid_endpoint_value",
                f"The {self.label} '{snippet(cell)}' cannot be read as a "
                f"{self._attribute.name} value.",
            )

        matches = self._index.find(coerced.value)

        if not matches:
            return None, None, (
                "unresolved_endpoint",
                f"No {self._type_name} has {self._attribute.name} '{snippet(coerced.value)}' "
                f"(the {self.label}).",
            )

        if len(matches) > 1:
            return None, None, (
                "ambiguous_endpoint",
                f"{len(matches)} {self._type_name} objects have {self._attribute.name} "
                f"'{snippet(coerced.value)}' (the {self.label}).",
            )

        return matches[0], self._object_type_id, None

    def _resolve_key(self, cell):

        value = str(cell).strip()

        matches = []
        matched_type_ids = []

        for type_id, index in self._key_indexes.items():
            found = index.find(value)
            if found:
                matches.extend(found)
                matched_type_ids.append(type_id)

        if not matches:
            allowed = ", ".join(sorted(self._type_names.values())) or "any type"
            return None, None, (
                "unresolved_endpoint",
                f"No object with key '{snippet(value)}' among the types this relationship "
                f"allows: {allowed} (the {self.label}).",
            )

        if len(matches) > 1:
            names = ", ".join(sorted(self._type_names[type_id] for type_id in matched_type_ids))
            return None, None, (
                "ambiguous_endpoint_key",
                f"Key '{snippet(value)}' matches an object in more than one type this "
                f"relationship allows ({names}). Map this column to one specific type, or "
                f"make the key unique across those types (the {self.label}).",
            )

        return matches[0], matched_type_ids[0], None
