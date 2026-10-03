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

    def attribute(self, key):
        for attribute in self.attributes:
            if attribute.key == key:
                return attribute

        return None

    def to_dict(self):
        return {
            "kind": self.kind,
            "type_id": str(self.type_id),
            "name": self.name,
            "attributes": [attribute.to_dict() for attribute in self.attributes],
        }


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


def _relationship_spec(relationship_type) -> TargetSpec:
    return TargetSpec(
        kind=RELATIONSHIP,
        type_id=relationship_type.id,
        name=relationship_type.name,
        key=relationship_type.key,
        attributes=_attribute_specs(
            AttributeDefinition.objects.filter(relationship_type=relationship_type)
        ),
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
