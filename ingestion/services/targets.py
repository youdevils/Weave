"""
What an import may target, read from the canonical ontology.

An import populates existing canonical types; it never defines them. A target
is one active ObjectType or RelationshipType of the selected model together
with that type's active attribute definitions. Only canonical rows are read:
a type or attribute that exists only inside a proposal is not importable.
"""

import uuid
from dataclasses import dataclass

from django.core.exceptions import ValidationError

from ingestion.services.errors import TargetError
from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule

DataType = AttributeDefinition.DataType

OBJECT = "object"
RELATIONSHIP = "relationship"

# Exact-match identity needs a value that is stable and comparable as-is.
# Booleans and timestamps are not identifiers.
IDENTITY_ATTRIBUTE_TYPES = frozenset(
    {
        DataType.TEXT,
        DataType.NUMBER,
        DataType.CHOICE,
        DataType.URL,
        DataType.DATE,
    }
)


@dataclass(frozen=True)
class AttributeSpec:
    id: uuid.UUID
    key: str
    name: str
    data_type: str
    required: bool = False
    choices: tuple = ()

    @property
    def identity_eligible(self) -> bool:
        return self.data_type in IDENTITY_ATTRIBUTE_TYPES

    def to_dict(self):
        return {
            "key": self.key,
            "name": self.name,
            "data_type": self.data_type,
            "required": self.required,
            "choices": list(self.choices),
            "identity_eligible": self.identity_eligible,
        }


@dataclass(frozen=True)
class TargetSpec:
    kind: str
    type_id: uuid.UUID
    name: str
    key: str
    attributes: tuple
    # RELATIONSHIP only: the object types this relationship's own rules
    # allow on each side, and the exact (subject_type_id, object_type_id)
    # pairs those rules permit -- each side resolving to *some* allowed
    # type does not mean the pair they form together is permitted. Used
    # to scope key-based endpoint resolution (search every allowed type
    # on that side) and to validate the resolved pair.
    subject_type_ids: tuple = ()
    object_type_ids: tuple = ()
    allowed_pairs: tuple = ()
    # (type_id, name) for every id appearing in subject_type_ids/
    # object_type_ids -- display only (template comments, wizard labels).
    endpoint_type_names: tuple = ()

    def attribute(self, key):
        for attribute in self.attributes:
            if attribute.key == key:
                return attribute

        return None

    def endpoint_type_name(self, type_id):
        for candidate_id, name in self.endpoint_type_names:
            if candidate_id == type_id:
                return name

        return None

    def to_dict(self):
        data = {
            "kind": self.kind,
            "type_id": str(self.type_id),
            "name": self.name,
            "key": self.key,
            "attributes": [attribute.to_dict() for attribute in self.attributes],
        }

        if self.kind == RELATIONSHIP:
            data["subject_type_ids"] = [str(type_id) for type_id in self.subject_type_ids]
            data["object_type_ids"] = [str(type_id) for type_id in self.object_type_ids]

        return data


def _attribute_specs(queryset):
    return tuple(
        AttributeSpec(
            id=definition.id,
            key=definition.key,
            name=definition.name,
            data_type=definition.data_type,
            required=definition.required,
            choices=tuple((definition.config or {}).get("choices", ())),
        )
        for definition in queryset.filter(is_active=True).order_by("sort_order", "name")
    )


def _object_spec(object_type) -> TargetSpec:
    return TargetSpec(
        kind=OBJECT,
        type_id=object_type.id,
        name=object_type.name,
        key=object_type.key,
        attributes=_attribute_specs(
            AttributeDefinition.objects.filter(object_type=object_type)
        ),
    )


def endpoint_type_ids(relationship_type_id):
    """
    (subject_type_ids, object_type_ids, allowed_pairs, names) for one
    RelationshipType, read directly from its RelationshipTypeRule rows (a
    canonical model, not proposal-related -- safe to read from ingestion's
    planners under the same rule identity.py already follows for Object/
    Relationship). One RelationshipType can have several rules, each its
    own (subject_type, object_type) pair -- the sets below are every
    distinct type seen on each side; `allowed_pairs` is the exact set of
    pairs those rules permit, which is not simply every combination of
    the two sets. `names` is (type_id, name) for every distinct type
    seen, resolved in the same query (select_related) -- display only.
    """

    rules = RelationshipTypeRule.objects.filter(
        relationship_type_id=relationship_type_id
    ).select_related("subject_type", "object_type")

    subject_type_ids = set()
    object_type_ids = set()
    allowed_pairs = set()
    names = {}

    for rule in rules:
        subject_type_ids.add(rule.subject_type_id)
        object_type_ids.add(rule.object_type_id)
        allowed_pairs.add((rule.subject_type_id, rule.object_type_id))
        names[rule.subject_type_id] = rule.subject_type.name
        names[rule.object_type_id] = rule.object_type.name

    return (
        tuple(subject_type_ids),
        tuple(object_type_ids),
        tuple(allowed_pairs),
        tuple(names.items()),
    )


def _relationship_spec(relationship_type) -> TargetSpec:
    subject_type_ids, object_type_ids, allowed_pairs, endpoint_type_names = endpoint_type_ids(
        relationship_type.id
    )

    return TargetSpec(
        kind=RELATIONSHIP,
        type_id=relationship_type.id,
        name=relationship_type.name,
        key=relationship_type.key,
        attributes=_attribute_specs(
            AttributeDefinition.objects.filter(relationship_type=relationship_type)
        ),
        subject_type_ids=subject_type_ids,
        object_type_ids=object_type_ids,
        allowed_pairs=allowed_pairs,
        endpoint_type_names=endpoint_type_names,
    )


def resolve_target(model, kind, type_id) -> TargetSpec:
    """
    The target for (kind, type_id) inside `model`. The id comes from the
    browser: it is looked up *within the model*, so another model's type is
    indistinguishable from a missing one.
    """

    if kind == OBJECT:
        queryset, build = ObjectType.objects, _object_spec
    elif kind == RELATIONSHIP:
        queryset, build = RelationshipType.objects, _relationship_spec
    else:
        raise TargetError("Choose whether to import objects or relationships.")

    try:
        instance = queryset.filter(model=model, id=type_id, is_active=True).first()
    except (ValueError, TypeError, ValidationError):
        instance = None

    if instance is None:
        raise TargetError("That type was not found in this model, or it is not active.")

    return build(instance)


def object_type_specs(model) -> dict:
    """Every active object type of the model, by id (endpoint resolution)."""

    return {
        object_type.id: _object_spec(object_type)
        for object_type in ObjectType.objects.filter(model=model, is_active=True)
    }


def relationship_type_specs(model) -> dict:
    """Every active relationship type of the model, by id."""

    return {
        relationship_type.id: _relationship_spec(relationship_type)
        for relationship_type in RelationshipType.objects.filter(
            model=model, is_active=True
        ).order_by("sort_order", "name")
    }


def describe_targets(model) -> dict:
    """The page's picklists: importable types with their fields."""

    object_specs = object_type_specs(model)

    return {
        "object_types": [
            spec.to_dict()
            for spec in sorted(object_specs.values(), key=lambda spec: spec.name.lower())
        ],
        "relationship_types": [
            spec.to_dict() for spec in relationship_type_specs(model).values()
        ],
    }
