"""
Pure translation of a declarative model template into ProposalChange specs.

Builds the exact spec shape ProposalService.record_changes_bulk() expects
(operation, target_type, target_id, parent_type, parent_id, before, after).
Never touches the database: template-local keys (object type / relationship
type / sample object keys) are resolved to pre-generated UUIDs here, in
memory, exactly as the manual editors (model.views.object_type_editor,
relationship_type_editor, data_object_editor, data_relationship_editor)
pre-generate a CREATE's target_id and reuse it as the row's eventual primary
key once model.services.proposal.submission applies the change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


class TemplateDefinitionError(ValueError):
    """The template dict is malformed: a duplicate or unknown template-local key."""


@dataclass
class TemplateChangeSet:
    specs: list[dict]
    object_type_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    relationship_type_ids: dict[str, uuid.UUID] = field(default_factory=dict)


def build_template_changes(template: dict, model_id) -> TemplateChangeSet:
    """
    Translate `template` into the ProposalChange specs that would create it,
    plus the template-local object-type/relationship-type key -> pre-generated
    id maps needed to apply template-defined appearance afterward.
    """

    specs: list[dict] = []
    object_type_ids: dict[str, uuid.UUID] = {}
    relationship_type_ids: dict[str, uuid.UUID] = {}
    object_ids: dict[str, uuid.UUID] = {}

    _build_object_types(
        template.get("object_types", []),
        model_id,
        specs,
        object_type_ids,
    )

    _build_relationship_types(
        template.get("relationship_types", []),
        model_id,
        specs,
        relationship_type_ids,
    )

    _build_relationship_rules(
        template.get("relationship_types", []),
        object_type_ids,
        relationship_type_ids,
        specs,
    )

    _build_objects(
        template.get("objects", []),
        object_type_ids,
        specs,
        object_ids,
    )

    _build_relationships(
        template.get("relationships", []),
        relationship_type_ids,
        object_ids,
        specs,
    )

    return TemplateChangeSet(
        specs=specs,
        object_type_ids=object_type_ids,
        relationship_type_ids=relationship_type_ids,
    )


# ---------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------


def _build_object_types(definitions, model_id, specs, object_type_ids):
    for definition in definitions:
        key = definition["key"]

        if key in object_type_ids:
            raise TemplateDefinitionError(f"Duplicate object type template key: '{key}'.")

        object_type_uuid = uuid.uuid4()
        object_type_ids[key] = object_type_uuid

        specs.append(
            {
                "operation": "create",
                "target_type": "ObjectType",
                "target_id": object_type_uuid,
                "parent_type": "Model",
                "parent_id": model_id,
                "before": None,
                "after": {
                    "name": definition["name"],
                    "key": key,
                    "description": definition.get("description", ""),
                    "sort_order": definition.get("sort_order", 0),
                    "is_active": True,
                },
            }
        )

        _build_attribute_definitions(
            definition.get("attributes", []),
            "ObjectType",
            object_type_uuid,
            specs,
        )


def _build_attribute_definitions(definitions, parent_type, parent_id, specs):
    for definition in definitions:
        specs.append(
            {
                "operation": "create",
                "target_type": "AttributeDefinition",
                "target_id": uuid.uuid4(),
                "parent_type": parent_type,
                "parent_id": parent_id,
                "before": None,
                "after": {
                    "name": definition["name"],
                    "key": definition["key"],
                    "data_type": definition["data_type"],
                    "description": definition.get("description", ""),
                    "required": definition.get("required", False),
                    "nullable": definition.get("nullable", False),
                    "default_value": definition.get("default_value"),
                    "sort_order": definition.get("sort_order", 0),
                    "config": definition.get("config", {}),
                    "is_active": True,
                },
            }
        )


# ---------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------


def _build_relationship_types(definitions, model_id, specs, relationship_type_ids):
    for definition in definitions:
        key = definition["key"]

        if key in relationship_type_ids:
            raise TemplateDefinitionError(f"Duplicate relationship type template key: '{key}'.")

        relationship_type_uuid = uuid.uuid4()
        relationship_type_ids[key] = relationship_type_uuid

        specs.append(
            {
                "operation": "create",
                "target_type": "RelationshipType",
                "target_id": relationship_type_uuid,
                "parent_type": "Model",
                "parent_id": model_id,
                "before": None,
                "after": {
                    "name": definition["name"],
                    "key": key,
                    "description": definition.get("description", ""),
                    "sort_order": definition.get("sort_order", 0),
                    "is_active": True,
                },
            }
        )

        _build_attribute_definitions(
            definition.get("attributes", []),
            "RelationshipType",
            relationship_type_uuid,
            specs,
        )


# ---------------------------------------------------------------------
# Relationship rules
# ---------------------------------------------------------------------


def _build_relationship_rules(definitions, object_type_ids, relationship_type_ids, specs):
    for definition in definitions:
        relationship_key = definition["key"]

        if relationship_key not in relationship_type_ids:
            raise TemplateDefinitionError(f"Relationship type '{relationship_key}' was not created.")

        relationship_type_uuid = relationship_type_ids[relationship_key]

        for rule in definition.get("rules", []):
            subject_key = rule["subject_type"]
            object_key = rule["object_type"]

            if subject_key not in object_type_ids:
                raise TemplateDefinitionError(
                    f"Unknown subject object type '{subject_key}' "
                    f"in relationship type '{relationship_key}'."
                )

            if object_key not in object_type_ids:
                raise TemplateDefinitionError(
                    f"Unknown object object type '{object_key}' "
                    f"in relationship type '{relationship_key}'."
                )

            specs.append(
                {
                    "operation": "create",
                    "target_type": "RelationshipTypeRule",
                    "target_id": uuid.uuid4(),
                    "parent_type": "RelationshipType",
                    "parent_id": relationship_type_uuid,
                    "before": None,
                    "after": {
                        "subject_type_id": str(object_type_ids[subject_key]),
                        "object_type_id": str(object_type_ids[object_key]),
                        "subject_minimum": rule.get("subject_minimum", 0),
                        "subject_maximum": rule.get("subject_maximum"),
                        "object_minimum": rule.get("object_minimum", 0),
                        "object_maximum": rule.get("object_maximum"),
                    },
                }
            )


# ---------------------------------------------------------------------
# Sample objects
# ---------------------------------------------------------------------


def _build_objects(definitions, object_type_ids, specs, object_ids):
    for definition in definitions:
        key = definition["key"]
        object_type_key = definition["type"]

        if key in object_ids:
            raise TemplateDefinitionError(f"Duplicate sample object template key: '{key}'.")

        if object_type_key not in object_type_ids:
            raise TemplateDefinitionError(
                f"Unknown object type '{object_type_key}' for sample object '{key}'."
            )

        object_uuid = uuid.uuid4()
        object_ids[key] = object_uuid

        specs.append(
            {
                "operation": "create",
                "target_type": "Object",
                "target_id": object_uuid,
                "parent_type": "ObjectType",
                "parent_id": object_type_ids[object_type_key],
                "before": None,
                "after": {
                    "name": definition["name"],
                    "description": definition.get("description", ""),
                    "is_active": definition.get("is_active", True),
                    "attributes": definition.get("attributes", {}),
                },
            }
        )


# ---------------------------------------------------------------------
# Sample relationships
# ---------------------------------------------------------------------


def _build_relationships(definitions, relationship_type_ids, object_ids, specs):
    for definition in definitions:
        relationship_type_key = definition["type"]
        subject_key = definition["subject"]
        object_key = definition["object"]

        if relationship_type_key not in relationship_type_ids:
            raise TemplateDefinitionError(f"Unknown relationship type '{relationship_type_key}'.")

        if subject_key not in object_ids:
            raise TemplateDefinitionError(
                f"Unknown sample object '{subject_key}' used as relationship subject."
            )

        if object_key not in object_ids:
            raise TemplateDefinitionError(
                f"Unknown sample object '{object_key}' used as relationship object."
            )

        specs.append(
            {
                "operation": "create",
                "target_type": "Relationship",
                "target_id": uuid.uuid4(),
                "parent_type": "RelationshipType",
                "parent_id": relationship_type_ids[relationship_type_key],
                "before": None,
                "after": {
                    "subject_id": str(object_ids[subject_key]),
                    "object_id": str(object_ids[object_key]),
                    "is_active": definition.get("is_active", True),
                    "attributes": definition.get("attributes", {}),
                    "valid_from": definition.get("valid_from"),
                    "valid_to": definition.get("valid_to"),
                },
            }
        )
