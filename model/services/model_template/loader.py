from django.db import transaction

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
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

    The template is resolved by its stable key and its complete
    declarative definition is persisted to the database.

    The entire operation occurs inside a transaction. If any part
    fails, none of the ontology is persisted.
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

    return model


def _create_object_types(model, definitions):
    """
    Create all ObjectType records and their AttributeDefinitions.

    Returns a mapping of template key -> ObjectType instance.
    """

    object_types = {}

    for definition in definitions:

        object_type = ObjectType.objects.create(
            model=model,
            name=definition["name"],
            key=definition["key"],
            description=definition.get("description", ""),
            sort_order=definition.get("sort_order", 0),
        )

        object_types[definition["key"]] = object_type

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


def _create_relationship_types(model, definitions):
    """
    Create all RelationshipType records.

    Returns a mapping of template key -> RelationshipType instance.

    Relationship rules are created separately because they reference
    ObjectTypes which must already exist.
    """

    relationship_types = {}

    for definition in definitions:

        relationship_type = RelationshipType.objects.create(
            model=model,
            name=definition["name"],
            key=definition["key"],
            description=definition.get("description", ""),
            sort_order=definition.get("sort_order", 0),
        )

        relationship_types[definition["key"]] = relationship_type

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

        relationship_type = relationship_types[definition["key"]]

        for rule in definition.get("rules", []):

            subject_type = object_types[rule["subject_type"]]

            object_type = object_types[rule["object_type"]]

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
                subject_required=rule.get(
                    "subject_required",
                    False,
                ),
                object_minimum=rule.get(
                    "object_minimum",
                    0,
                ),
                object_maximum=rule.get(
                    "object_maximum",
                ),
                object_required=rule.get(
                    "object_required",
                    False,
                ),
            )
