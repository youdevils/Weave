from django.db import transaction

from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule

from model.model_templates.business_process import (
    BUSINESS_PROCESS_TEMPLATE,
)

TEMPLATES = {
    BUSINESS_PROCESS_TEMPLATE["key"]: BUSINESS_PROCESS_TEMPLATE,
}


def get_template(key: str) -> dict:
    """
    Return a model template by its stable key.
    """

    try:
        return TEMPLATES[key]
    except KeyError:
        raise ValueError(f"Unknown model template: '{key}'.")


@transaction.atomic
def instantiate_template(model, template_key: str):
    """
    Instantiate a model template into an existing Model.

    The template is declarative. It can define:

    - Object types
    - Object type attributes
    - Relationship types
    - Relationship type attributes
    - Relationship type rules
    - Sample objects
    - Sample relationships

    Template object and relationship keys are temporary references used
    only during instantiation. They are not persisted as fields on the
    Object or Relationship models.

    The entire operation occurs inside a transaction. If any part fails,
    none of the template is persisted.
    """

    template = get_template(template_key)

    object_types = _create_object_types(
        model=model,
        definitions=template.get("object_types", []),
    )

    relationship_types = _create_relationship_types(
        model=model,
        definitions=template.get("relationship_types", []),
    )

    _create_relationship_rules(
        relationship_types=relationship_types,
        object_types=object_types,
        definitions=template.get("relationship_types", []),
    )

    objects = _create_objects(
        model=model,
        object_types=object_types,
        definitions=template.get("objects", []),
    )

    _create_relationships(
        model=model,
        objects=objects,
        relationship_types=relationship_types,
        definitions=template.get("relationships", []),
    )

    return model


# ---------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------


def _create_object_types(model, definitions):
    """
    Create all ObjectType records and their AttributeDefinitions.

    Returns:
        dict: template key -> ObjectType instance
    """

    object_types = {}

    for definition in definitions:
        key = definition["key"]

        if key in object_types:
            raise ValueError(f"Duplicate object type template key: '{key}'.")

        object_type = ObjectType.objects.create(
            model=model,
            name=definition["name"],
            key=key,
            description=definition.get("description", ""),
            sort_order=definition.get("sort_order", 0),
        )

        object_types[key] = object_type

        _create_object_type_attributes(
            object_type=object_type,
            definitions=definition.get("attributes", []),
        )

    return object_types


def _create_object_type_attributes(object_type, definitions):
    """
    Create AttributeDefinitions belonging to an ObjectType.
    """

    for definition in definitions:
        AttributeDefinition.objects.create(
            object_type=object_type,
            name=definition["name"],
            key=definition["key"],
            data_type=definition["data_type"],
            description=definition.get("description", ""),
            required=definition.get("required", False),
            nullable=definition.get("nullable", False),
            default_value=definition.get("default_value"),
            sort_order=definition.get("sort_order", 0),
            config=definition.get("config", {}),
        )


# ---------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------


def _create_relationship_types(model, definitions):
    """
    Create all RelationshipType records.

    Returns:
        dict: template key -> RelationshipType instance

    Relationship rules are created separately because they reference
    ObjectTypes which must already exist.
    """

    relationship_types = {}

    for definition in definitions:
        key = definition["key"]

        if key in relationship_types:
            raise ValueError(f"Duplicate relationship type template key: '{key}'.")

        relationship_type = RelationshipType.objects.create(
            model=model,
            name=definition["name"],
            key=key,
            description=definition.get("description", ""),
            sort_order=definition.get("sort_order", 0),
        )

        relationship_types[key] = relationship_type

        _create_relationship_attributes(
            relationship_type=relationship_type,
            definitions=definition.get("attributes", []),
        )

    return relationship_types


def _create_relationship_attributes(
    relationship_type,
    definitions,
):
    """
    Create AttributeDefinitions belonging to a RelationshipType.
    """

    for definition in definitions:
        AttributeDefinition.objects.create(
            relationship_type=relationship_type,
            name=definition["name"],
            key=definition["key"],
            data_type=definition["data_type"],
            description=definition.get("description", ""),
            required=definition.get("required", False),
            nullable=definition.get("nullable", False),
            default_value=definition.get("default_value"),
            sort_order=definition.get("sort_order", 0),
            config=definition.get("config", {}),
        )


# ---------------------------------------------------------------------
# Relationship rules
# ---------------------------------------------------------------------


def _create_relationship_rules(
    relationship_types,
    object_types,
    definitions,
):
    """
    Create RelationshipTypeRule records.

    Object types are referenced by their stable template keys rather
    than database IDs.
    """

    for definition in definitions:
        relationship_key = definition["key"]

        if relationship_key not in relationship_types:
            raise ValueError(f"Relationship type '{relationship_key}' was not created.")

        relationship_type = relationship_types[relationship_key]

        for rule in definition.get("rules", []):
            subject_key = rule["subject_type"]
            object_key = rule["object_type"]

            if subject_key not in object_types:
                raise ValueError(
                    f"Unknown subject object type '{subject_key}' "
                    f"in relationship type '{relationship_key}'."
                )

            if object_key not in object_types:
                raise ValueError(
                    f"Unknown object object type '{object_key}' "
                    f"in relationship type '{relationship_key}'."
                )

            subject_type = object_types[subject_key]
            object_type = object_types[object_key]

            RelationshipTypeRule.objects.create(
                relationship_type=relationship_type,
                subject_type=subject_type,
                object_type=object_type,
                subject_minimum=rule.get(
                    "subject_minimum",
                    0,
                ),
                subject_maximum=rule.get(
                    "subject_maximum",
                ),
                object_minimum=rule.get(
                    "object_minimum",
                    0,
                ),
                object_maximum=rule.get(
                    "object_maximum",
                ),
            )


# ---------------------------------------------------------------------
# Sample objects
# ---------------------------------------------------------------------


def _create_objects(
    model,
    object_types,
    definitions,
):
    """
    Create sample Object records defined by the template.

    Each object definition must contain:

        key
        type
        name

    The template key is an in-memory reference used to create
    relationships between sample objects. It is not stored on Object.

    Returns:
        dict: template object key -> Object instance
    """

    objects = {}

    for definition in definitions:
        key = definition["key"]
        object_type_key = definition["type"]

        if key in objects:
            raise ValueError(f"Duplicate sample object template key: '{key}'.")

        if object_type_key not in object_types:
            raise ValueError(
                f"Unknown object type '{object_type_key}' "
                f"for sample object '{key}'."
            )

        object_type = object_types[object_type_key]

        obj = Object.objects.create(
            model=model,
            object_type=object_type,
            name=definition["name"],
            description=definition.get("description", ""),
            is_active=definition.get("is_active", True),
            attributes=definition.get("attributes", {}),
        )

        objects[key] = obj

    return objects


# ---------------------------------------------------------------------
# Sample relationships
# ---------------------------------------------------------------------


def _create_relationships(
    model,
    objects,
    relationship_types,
    definitions,
):
    """
    Create sample Relationship records defined by the template.

    Each relationship definition must contain:

        type
        subject
        object

    subject/object reference sample object template keys.

    Optional fields:

        is_active
        attributes
        valid_from
        valid_to
    """

    for definition in definitions:
        relationship_type_key = definition["type"]
        subject_key = definition["subject"]
        object_key = definition["object"]

        if relationship_type_key not in relationship_types:
            raise ValueError(f"Unknown relationship type '{relationship_type_key}'.")

        if subject_key not in objects:
            raise ValueError(
                f"Unknown sample object '{subject_key}' "
                f"used as relationship subject."
            )

        if object_key not in objects:
            raise ValueError(
                f"Unknown sample object '{object_key}' " f"used as relationship object."
            )

        relationship_type = relationship_types[relationship_type_key]
        subject = objects[subject_key]
        object_ = objects[object_key]

        Relationship.objects.create(
            model=model,
            relationship_type=relationship_type,
            subject=subject,
            object=object_,
            is_active=definition.get("is_active", True),
            attributes=definition.get("attributes", {}),
            valid_from=definition.get("valid_from"),
            valid_to=definition.get("valid_to"),
        )
