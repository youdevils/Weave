from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule


class ProposalReviewService:

    @staticmethod
    def resolve_parents(changes):
        references = {
            (
                change.parent_type,
                change.parent_id,
            )
            for change in changes
            if change.parent_type and change.parent_id
        }

        if not references:
            return {}

        parents = {}

        model_map = {
            "Model": Model,
            "ObjectType": ObjectType,
            "RelationshipType": RelationshipType,
            "AttributeDefinition": AttributeDefinition,
            "RelationshipTypeRule": RelationshipTypeRule,
            "Object": Object,
            "Relationship": Relationship,
        }

        for parent_type, parent_id in references:

            parent_model = model_map.get(parent_type)

            if not parent_model:
                continue

            parent = parent_model.objects.filter(id=parent_id).first()

            if parent:
                parents[(parent_type, parent_id)] = parent

        return parents

    @staticmethod
    def parent_label(parent):
        if not parent:
            return ""

        if hasattr(parent, "name") and parent.name:
            return parent.name

        if hasattr(parent, "key") and parent.key:
            return parent.key

        return str(parent)

    @staticmethod
    def change_label(change):
        after = change.after or {}
        before = change.before or {}

        if after.get("field"):
            return after["field"].replace("_", " ").title()

        if after.get("name"):
            return after["name"]

        if after.get("key"):
            return after["key"]

        if before.get("name"):
            return before["name"]

        if before.get("key"):
            return before["key"]

        return change.target_type

    @staticmethod
    def change_parent_context(change, parents):
        if not change.parent_type or not change.parent_id:
            return None

        parent = parents.get(
            (
                change.parent_type,
                change.parent_id,
            )
        )

        if not parent:
            return {
                "type": change.parent_type,
                "label": "",
            }

        return {
            "type": change.parent_type,
            "label": ProposalReviewService.parent_label(parent),
        }
