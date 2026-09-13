from collections import defaultdict

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule


class ProposalReviewService:

    MODEL_MAP = {
        "Model": Model,
        "ObjectType": ObjectType,
        "RelationshipType": RelationshipType,
        "AttributeDefinition": AttributeDefinition,
        "RelationshipTypeRule": RelationshipTypeRule,
        "Object": Object,
        "Relationship": Relationship,
    }

    # Extra relations to fetch eagerly when batch-loading canonical
    # instances, so RelationshipTypeRule identity building doesn't
    # trigger a query per FK.
    SELECT_RELATED = {
        "RelationshipTypeRule": ("subject_type", "object_type"),
        "Relationship": ("subject", "object"),
    }

    # Human-facing display names for target_type / parent_type,
    # used anywhere a type is shown to the reviewer.
    TYPE_LABELS = {
        "Model": "Model",
        "ObjectType": "Object Type",
        "AttributeDefinition": "Attribute",
        "RelationshipType": "Relationship Type",
        "RelationshipTypeRule": "Relationship Rule",
        "Object": "Object",
        "Relationship": "Relationship",
    }

    # Overrides for the "field changed" label on field-level UPDATE
    # changes, only where default title-casing reads badly.
    FIELD_LABEL_OVERRIDES = {
        "subject_type_id": "Subject Type",
        "object_type_id": "Object Type",
    }

    # -----------------------------------------------------------------
    # Type labels
    # -----------------------------------------------------------------

    @staticmethod
    def display_label(type_name):
        return ProposalReviewService.TYPE_LABELS.get(
            type_name,
            type_name,
        )

    # -----------------------------------------------------------------
    # Canonical instance resolution (shared by parents + targets)
    # -----------------------------------------------------------------

    @staticmethod
    def _resolve_instances(pairs):
        grouped = defaultdict(set)

        for type_name, object_id in pairs:
            if type_name and object_id:
                grouped[type_name].add(object_id)

        instances = {}

        for type_name, ids in grouped.items():

            model = ProposalReviewService.MODEL_MAP.get(type_name)

            if not model:
                continue

            queryset = model.objects.filter(id__in=ids)

            related = ProposalReviewService.SELECT_RELATED.get(type_name)

            if related:
                queryset = queryset.select_related(*related)

            for obj in queryset:
                instances[(type_name, obj.id)] = obj

        return instances

    @staticmethod
    def resolve_parents(changes):
        return ProposalReviewService._resolve_instances(
            (change.parent_type, change.parent_id) for change in changes
        )

    @staticmethod
    def resolve_targets(changes):
        return ProposalReviewService._resolve_instances(
            (change.target_type, change.target_id) for change in changes
        )

    # -----------------------------------------------------------------
    # Proposal-only CREATE fallback
    #
    # A target or parent may not exist in the canonical database yet.
    # This builds a lookup of every CREATE change's payload so that
    # target/parent resolution can fall back to sibling proposal data
    # instead of a failed database lookup.
    # -----------------------------------------------------------------

    @staticmethod
    def build_create_lookup(changes):
        return {
            (change.target_type, str(change.target_id)): (change.after or {})
            for change in changes
            if change.operation == ProposalChange.Operation.CREATE and change.target_id
        }

    # -----------------------------------------------------------------
    # ObjectType name resolution for RelationshipTypeRule identity
    # -----------------------------------------------------------------

    @staticmethod
    def resolve_object_type_names(changes, create_lookup):
        ids = set()

        for change in changes:

            if change.target_type != "RelationshipTypeRule":
                continue

            payload = create_lookup.get(
                ("RelationshipTypeRule", str(change.target_id))
            ) or {}

            for key in ("subject_type_id", "object_type_id"):

                value = payload.get(key)

                if value:
                    ids.add(str(value))

        if not ids:
            return {}

        names = {
            str(object_id): name
            for object_id, name in ObjectType.objects.filter(
                id__in=ids,
            ).values_list("id", "name")
        }

        for object_id in ids:

            if object_id in names:
                continue

            create_payload = create_lookup.get(("ObjectType", object_id))

            if create_payload:
                names[object_id] = (
                    create_payload.get("name")
                    or create_payload.get("key")
                    or "Untitled"
                )

        return names

    @staticmethod
    def resolve_object_names(changes, create_lookup):
        """
        Resolve Object names referenced by a Relationship CREATE
        payload's subject_id/object_id, with a CREATE-lookup fallback
        for endpoints that are themselves only proposal-only Objects
        in the same working proposal.
        """

        ids = set()

        for change in changes:

            if change.target_type != "Relationship":
                continue

            payload = create_lookup.get(
                ("Relationship", str(change.target_id))
            ) or {}

            for key in ("subject_id", "object_id"):

                value = payload.get(key)

                if value:
                    ids.add(str(value))

        if not ids:
            return {}

        names = {
            str(object_id): name
            for object_id, name in Object.objects.filter(
                id__in=ids,
            ).values_list("id", "name")
        }

        for object_id in ids:

            if object_id in names:
                continue

            create_payload = create_lookup.get(("Object", object_id))

            if create_payload:
                names[object_id] = create_payload.get("name") or "Untitled"

        return names

    # -----------------------------------------------------------------
    # Parent label
    # -----------------------------------------------------------------

    @staticmethod
    def parent_label(parent):
        if not parent:
            return ""

        if hasattr(parent, "name") and parent.name:
            return parent.name

        if hasattr(parent, "key") and parent.key:
            return parent.key

        return str(parent)

    # -----------------------------------------------------------------
    # Field-changed label (field-level UPDATE changes only)
    # -----------------------------------------------------------------

    @staticmethod
    def change_label(change):
        after = change.after or {}

        if not after.get("field"):
            return None

        field = after["field"]

        return ProposalReviewService.FIELD_LABEL_OVERRIDES.get(
            field,
            field.replace("_", " ").title(),
        )

    # -----------------------------------------------------------------
    # RelationshipTypeRule identity
    # -----------------------------------------------------------------

    @staticmethod
    def _cardinality(minimum, maximum):
        return f"{minimum}..{'*' if maximum is None else maximum}"

    @staticmethod
    def _rule_identity(change, targets, create_lookup, object_type_names):
        canonical_rule = targets.get(
            ("RelationshipTypeRule", change.target_id)
        )

        if canonical_rule is not None:

            subject_name = canonical_rule.subject_type.name
            object_name = canonical_rule.object_type.name

            subject_span = ProposalReviewService._cardinality(
                canonical_rule.subject_minimum,
                canonical_rule.subject_maximum,
            )

            object_span = ProposalReviewService._cardinality(
                canonical_rule.object_minimum,
                canonical_rule.object_maximum,
            )

        else:

            payload = create_lookup.get(
                ("RelationshipTypeRule", str(change.target_id))
            ) or {}

            subject_name = object_type_names.get(
                str(payload.get("subject_type_id")),
                "Unknown",
            )

            object_name = object_type_names.get(
                str(payload.get("object_type_id")),
                "Unknown",
            )

            subject_span = ProposalReviewService._cardinality(
                payload.get("subject_minimum", 0),
                payload.get("subject_maximum"),
            )

            object_span = ProposalReviewService._cardinality(
                payload.get("object_minimum", 0),
                payload.get("object_maximum"),
            )

        return f"{subject_name} {subject_span} → {object_span} {object_name}"

    # -----------------------------------------------------------------
    # Relationship identity
    # -----------------------------------------------------------------

    @staticmethod
    def _relationship_identity(change, targets, create_lookup, object_names):
        canonical_relationship = targets.get(
            ("Relationship", change.target_id)
        )

        if canonical_relationship is not None:
            subject_name = canonical_relationship.subject.name
            object_name = canonical_relationship.object.name
        else:
            payload = create_lookup.get(
                ("Relationship", str(change.target_id))
            ) or {}
            subject_name = object_names.get(
                str(payload.get("subject_id")),
                "Unknown",
            )
            object_name = object_names.get(
                str(payload.get("object_id")),
                "Unknown",
            )

        return f"{subject_name} → {object_name}"

    # -----------------------------------------------------------------
    # Target identity
    #
    # The exact thing being changed, as distinct from its parent
    # (the thing that contains it).
    # -----------------------------------------------------------------

    @staticmethod
    def change_target(change, targets, create_lookup, object_type_names, object_names=None):
        object_names = object_names or {}

        display_type = ProposalReviewService.display_label(change.target_type)

        if change.target_type == "RelationshipTypeRule":
            return {
                "type": display_type,
                "label": ProposalReviewService._rule_identity(
                    change,
                    targets,
                    create_lookup,
                    object_type_names,
                ),
            }

        if change.target_type == "Relationship":
            return {
                "type": display_type,
                "label": ProposalReviewService._relationship_identity(
                    change,
                    targets,
                    create_lookup,
                    object_names,
                ),
            }

        after = change.after or {}
        before = change.before or {}

        if after.get("field"):

            instance = targets.get((change.target_type, change.target_id))

            if instance is not None:
                label = ProposalReviewService.parent_label(instance)
            else:
                payload = create_lookup.get(
                    (change.target_type, str(change.target_id))
                ) or {}
                label = payload.get("name") or payload.get("key") or display_type

            return {"type": display_type, "label": label}

        if after.get("name"):
            label = after["name"]
        elif after.get("key"):
            label = after["key"]
        elif before.get("name"):
            label = before["name"]
        elif before.get("key"):
            label = before["key"]
        else:
            label = display_type

        return {"type": display_type, "label": label}

    # -----------------------------------------------------------------
    # Parent context
    # -----------------------------------------------------------------

    @staticmethod
    def change_parent_context(change, parents, create_lookup):
        if not change.parent_type or not change.parent_id:
            return None

        parent = parents.get(
            (
                change.parent_type,
                change.parent_id,
            )
        )

        if parent:
            label = ProposalReviewService.parent_label(parent)
        else:
            payload = create_lookup.get(
                (change.parent_type, str(change.parent_id))
            ) or {}
            label = payload.get("name") or payload.get("key") or ""

        return {
            "type": ProposalReviewService.display_label(change.parent_type),
            "label": label,
        }
