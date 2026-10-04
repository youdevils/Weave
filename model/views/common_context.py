from types import SimpleNamespace

from django.shortcuts import get_object_or_404

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.models.proposal import ProposalChange
from model.views.active_proposal import (
    live_proposals_queryset,
    resolve_active_proposal,
)
from assisted.services.activity import active_task_for_model

# =====================================================================
# Shared proposal helpers
# =====================================================================


def _proposal_changes(
    proposal,
    target_type,
    target_id=None,
    operation=None,
):
    if not proposal:
        return []

    filters = {
        "target_type": target_type,
    }

    if target_id is not None:
        filters["target_id"] = target_id

    if operation is not None:
        filters["operation"] = operation

    return list(
        proposal.changes.filter(
            **filters,
        ).order_by(
            "created_at",
        )
    )


def _change_field_value(
    change,
):
    after = change.after or {}

    return (
        after.get("field"),
        after.get("value"),
    )


# =====================================================================
# Working ObjectType context
# =====================================================================


def _canonical_object_type_values(
    object_type,
):
    return {
        "name": object_type.name,
        "key": object_type.key,
        "description": object_type.description,
        "sort_order": object_type.sort_order,
        "is_active": object_type.is_active,
    }


def _object_type_effective_values(
    object_type,
    proposal,
):
    """
    Return canonical ObjectType values with any field-level changes
    from the user's working proposal applied.
    """

    values = _canonical_object_type_values(
        object_type,
    )

    for change in _proposal_changes(
        proposal,
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ):

        field, value = _change_field_value(
            change,
        )

        if field in values:
            values[field] = value

    return values


def _object_type_is_proposed(
    object_type,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
    ).exists()


def _attribute_count(
    object_type,
    proposal,
):
    """
    Return the effective number of active attributes belonging to an
    ObjectType.

    Canonical AttributeDefinitions are counted using their effective
    is_active value. Proposed CREATE AttributeDefinitions are included.
    """

    count = 0

    canonical_attributes = AttributeDefinition.objects.filter(
        object_type=object_type,
    )

    for attribute in canonical_attributes:

        active = attribute.is_active

        if proposal:

            change = (
                proposal.changes.filter(
                    target_type="AttributeDefinition",
                    target_id=attribute.id,
                    operation=ProposalChange.Operation.UPDATE,
                    after__field="is_active",
                )
                .order_by("-created_at")
                .first()
            )

            if change:

                after = change.after or {}

                if "value" in after:
                    active = after["value"]

        if active:
            count += 1

    if proposal:

        proposed_creates = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type="ObjectType",
            parent_id=object_type.id,
        )

        for change in proposed_creates:

            after = change.after or {}

            if after.get(
                "is_active",
                True,
            ):
                count += 1

    return count


def _build_working_object_types(
    object_types,
    proposal,
):
    """
    Build the effective ObjectType collection.

    Canonical ObjectTypes are overlaid with working proposal changes
    and proposal-only CREATE ObjectTypes are included.
    """

    items = []

    canonical_ids = {str(object_type.id) for object_type in object_types}

    # -----------------------------------------------------------------
    # Existing canonical ObjectTypes
    # -----------------------------------------------------------------

    for object_type in object_types:

        effective_values = _object_type_effective_values(
            object_type,
            proposal,
        )

        items.append(
            SimpleNamespace(
                id=object_type.id,
                name=effective_values["name"],
                key=effective_values["key"],
                description=effective_values["description"],
                sort_order=effective_values["sort_order"],
                is_active=effective_values["is_active"],
                canonical_is_active=object_type.is_active,
                attribute_count=_attribute_count(
                    object_type,
                    proposal,
                ),
                is_proposed=_object_type_is_proposed(
                    object_type,
                    proposal,
                ),
                is_created=False,
            )
        )

    # -----------------------------------------------------------------
    # Proposed CREATE ObjectTypes
    # -----------------------------------------------------------------

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="ObjectType",
            operation=ProposalChange.Operation.CREATE,
            parent_type="Model",
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            after = change.after or {}

            object_type_id = change.target_id

            proposed_object = SimpleNamespace(
                id=object_type_id,
                name=after.get(
                    "name",
                    "",
                ),
                key=after.get(
                    "key",
                    "",
                ),
                description=after.get(
                    "description",
                    "",
                ),
                sort_order=after.get(
                    "sort_order",
                    0,
                ),
                is_active=after.get(
                    "is_active",
                    True,
                ),
                canonical_is_active=after.get(
                    "is_active",
                    True,
                ),
                attribute_count=0,
                is_proposed=True,
                is_created=True,
            )

            proposed_object.attribute_count = (
                proposal.changes.filter(
                    target_type="AttributeDefinition",
                    operation=ProposalChange.Operation.CREATE,
                    parent_type="ObjectType",
                    parent_id=object_type_id,
                )
                .filter(
                    after__is_active=True,
                )
                .count()
            )

            items.append(
                proposed_object,
            )

    items.sort(
        key=lambda item: (
            item.sort_order,
            item.name.lower(),
        )
    )

    return items


def _working_object_type_lookup(
    working_object_types,
):
    return {str(object_type.id): object_type for object_type in working_object_types}


# =====================================================================
# Working RelationshipType helpers
# =====================================================================


def _canonical_relationship_type_values(
    relationship_type,
):
    return {
        "name": relationship_type.name,
        "key": relationship_type.key,
        "description": relationship_type.description,
        "sort_order": relationship_type.sort_order,
        "is_active": relationship_type.is_active,
    }


def _relationship_type_effective_values(
    relationship_type,
    proposal,
):
    """
    Return canonical RelationshipType values with any field-level
    changes from the user's working proposal applied.
    """

    values = _canonical_relationship_type_values(
        relationship_type,
    )

    for change in _proposal_changes(
        proposal,
        target_type="RelationshipType",
        target_id=relationship_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ):

        field, value = _change_field_value(
            change,
        )

        if field in values:
            values[field] = value

    return values


def _relationship_type_is_proposed(
    relationship_type,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="RelationshipType",
        target_id=relationship_type.id,
    ).exists()


def _relationship_attribute_count(
    relationship_type,
    proposal,
):
    """
    Return the effective number of active attributes belonging to a
    RelationshipType.
    """

    count = 0

    canonical_attributes = AttributeDefinition.objects.filter(
        relationship_type=relationship_type,
    )

    for attribute in canonical_attributes:

        active = attribute.is_active

        if proposal:

            change = (
                proposal.changes.filter(
                    target_type="AttributeDefinition",
                    target_id=attribute.id,
                    operation=ProposalChange.Operation.UPDATE,
                    after__field="is_active",
                )
                .order_by("-created_at")
                .first()
            )

            if change:

                after = change.after or {}

                if "value" in after:
                    active = after["value"]

        if active:
            count += 1

    if proposal:

        proposed_creates = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
        )

        for change in proposed_creates:

            after = change.after or {}

            if after.get(
                "is_active",
                True,
            ):
                count += 1

    return count


# =====================================================================
# Working RelationshipTypeRule helpers
# =====================================================================


def _rule_canonical_values(
    rule,
):
    return {
        "subject_type_id": rule.subject_type_id,
        "object_type_id": rule.object_type_id,
        "subject_minimum": rule.subject_minimum,
        "subject_maximum": rule.subject_maximum,
        "object_minimum": rule.object_minimum,
        "object_maximum": rule.object_maximum,
    }


def _rule_update_field_value(
    change,
):
    after = change.after or {}

    field = after.get(
        "field",
    )

    if "value" not in after:
        return field, None, False

    return field, after["value"], True


def _rule_effective_values(
    rule,
    proposal,
):
    values = _rule_canonical_values(
        rule,
    )

    for change in _proposal_changes(
        proposal,
        target_type="RelationshipTypeRule",
        target_id=rule.id,
        operation=ProposalChange.Operation.UPDATE,
    ):

        field, value, has_value = _rule_update_field_value(
            change,
        )

        if has_value and field in values:
            values[field] = value

    return values


def _rule_is_proposed(
    rule,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule.id,
    ).exists()


def _rule_is_deleted(
    rule,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule.id,
        operation=ProposalChange.Operation.DELETE,
    ).exists()


def _rule_working_item(
    rule,
    proposal,
    object_type_lookup,
):
    values = _rule_effective_values(
        rule,
        proposal,
    )

    subject_type = object_type_lookup.get(
        str(values["subject_type_id"]),
    )

    object_type = object_type_lookup.get(
        str(values["object_type_id"]),
    )

    return SimpleNamespace(
        id=rule.id,
        relationship_type_id=rule.relationship_type_id,
        subject_type_id=values["subject_type_id"],
        object_type_id=values["object_type_id"],
        subject_type=subject_type,
        object_type=object_type,
        subject_minimum=values["subject_minimum"],
        subject_maximum=values["subject_maximum"],
        object_minimum=values["object_minimum"],
        object_maximum=values["object_maximum"],
        is_proposed=_rule_is_proposed(
            rule,
            proposal,
        ),
        is_created=False,
        is_deleted=_rule_is_deleted(
            rule,
            proposal,
        ),
    )


def _extract_created_rule_values(
    change,
):
    """
    Resolve a CREATE payload.

    The preferred representation is direct property names, which
    mirrors the RelationshipTypeRule model. This also accepts the
    *_id naming used by ForeignKey values.
    """

    after = dict(
        change.after or {},
    )

    subject_type_id = after.get(
        "subject_type_id",
    )

    if subject_type_id is None:
        subject_type_id = after.get(
            "subject_type",
        )

    object_type_id = after.get(
        "object_type_id",
    )

    if object_type_id is None:
        object_type_id = after.get(
            "object_type",
        )

    return {
        "subject_type_id": subject_type_id,
        "object_type_id": object_type_id,
        "subject_minimum": after.get(
            "subject_minimum",
            0,
        ),
        "subject_maximum": after.get(
            "subject_maximum",
        ),
        "object_minimum": after.get(
            "object_minimum",
            0,
        ),
        "object_maximum": after.get(
            "object_maximum",
        ),
    }


def _build_working_relationship_rules(
    relationship_type,
    proposal,
    object_type_lookup,
):
    """
    Build the effective RelationshipTypeRule collection for a
    RelationshipType.

    Canonical rules are overlaid with working UPDATEs and excluded when
    represented by a DELETE. Proposal-only CREATE rules are included.
    """

    items = []

    canonical_rule_ids = set(str(rule.id) for rule in relationship_type.rules.all())

    # -----------------------------------------------------------------
    # Canonical rules
    # -----------------------------------------------------------------

    for rule in relationship_type.rules.all():

        if _rule_is_deleted(
            rule,
            proposal,
        ):
            continue

        items.append(
            _rule_working_item(
                rule,
                proposal,
                object_type_lookup,
            )
        )

    # -----------------------------------------------------------------
    # Proposed CREATE rules
    # -----------------------------------------------------------------

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="RelationshipTypeRule",
            operation=ProposalChange.Operation.CREATE,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_rule_ids:
                continue

            values = _extract_created_rule_values(
                change,
            )

            subject_type = object_type_lookup.get(
                str(values["subject_type_id"]),
            )

            object_type = object_type_lookup.get(
                str(values["object_type_id"]),
            )

            items.append(
                SimpleNamespace(
                    id=change.target_id,
                    relationship_type_id=relationship_type.id,
                    subject_type_id=values["subject_type_id"],
                    object_type_id=values["object_type_id"],
                    subject_type=subject_type,
                    object_type=object_type,
                    subject_minimum=values["subject_minimum"],
                    subject_maximum=values["subject_maximum"],
                    object_minimum=values["object_minimum"],
                    object_maximum=values["object_maximum"],
                    is_proposed=True,
                    is_created=True,
                    is_deleted=False,
                )
            )

    return items


def _relationship_rule_count(
    relationship_type,
    proposal,
    object_type_lookup,
):
    return len(
        _build_working_relationship_rules(
            relationship_type,
            proposal,
            object_type_lookup,
        )
    )


def _build_working_relationship_types(
    relationship_types,
    proposal,
    object_type_lookup,
):
    """
    Build the effective RelationshipType collection.

    Each item contains:

    - core effective values;
    - attribute_count;
    - rule_count;
    - working rules;
    - proposal state.
    """

    items = []

    canonical_ids = {
        str(relationship_type.id) for relationship_type in relationship_types
    }

    # -----------------------------------------------------------------
    # Existing canonical RelationshipTypes
    # -----------------------------------------------------------------

    for relationship_type in relationship_types:

        effective_values = _relationship_type_effective_values(
            relationship_type,
            proposal,
        )

        rules = _build_working_relationship_rules(
            relationship_type,
            proposal,
            object_type_lookup,
        )

        items.append(
            SimpleNamespace(
                id=relationship_type.id,
                name=effective_values["name"],
                key=effective_values["key"],
                description=effective_values["description"],
                sort_order=effective_values["sort_order"],
                is_active=effective_values["is_active"],
                canonical_is_active=relationship_type.is_active,
                attribute_count=_relationship_attribute_count(
                    relationship_type,
                    proposal,
                ),
                rule_count=len(rules),
                rules=rules,
                is_proposed=_relationship_type_is_proposed(
                    relationship_type,
                    proposal,
                ),
                is_created=False,
            )
        )

    # -----------------------------------------------------------------
    # Proposed CREATE RelationshipTypes
    # -----------------------------------------------------------------

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="RelationshipType",
            operation=ProposalChange.Operation.CREATE,
            parent_type="Model",
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            after = change.after or {}

            relationship_type_id = change.target_id

            proposed_relationship_type = SimpleNamespace(
                id=relationship_type_id,
                name=after.get(
                    "name",
                    "",
                ),
                key=after.get(
                    "key",
                    "",
                ),
                description=after.get(
                    "description",
                    "",
                ),
                sort_order=after.get(
                    "sort_order",
                    0,
                ),
                is_active=after.get(
                    "is_active",
                    True,
                ),
                canonical_is_active=after.get(
                    "is_active",
                    True,
                ),
                attribute_count=0,
                rule_count=0,
                rules=[],
                is_proposed=True,
                is_created=True,
            )

            # ---------------------------------------------------------
            # Proposed RelationshipType attributes
            # ---------------------------------------------------------

            proposed_relationship_type.attribute_count = (
                proposal.changes.filter(
                    target_type="AttributeDefinition",
                    operation=ProposalChange.Operation.CREATE,
                    parent_type="RelationshipType",
                    parent_id=relationship_type_id,
                )
                .filter(
                    after__is_active=True,
                )
                .count()
            )

            # ---------------------------------------------------------
            # Proposed RelationshipType rules
            # ---------------------------------------------------------

            proposed_relationship_type.rules = (
                _build_working_relationship_rules_for_proposed_type(
                    relationship_type_id,
                    proposal,
                    object_type_lookup,
                )
            )

            proposed_relationship_type.rule_count = len(
                proposed_relationship_type.rules
            )

            items.append(
                proposed_relationship_type,
            )

    items.sort(
        key=lambda item: (
            item.sort_order,
            item.name.lower(),
        )
    )

    return items


def _build_working_relationship_rules_for_proposed_type(
    relationship_type_id,
    proposal,
    object_type_lookup,
):
    """
    Build rules belonging to a proposal-only RelationshipType.

    Since no canonical RelationshipTypeRule rows can exist yet, every
    rule represented here is proposal-created.
    """

    items = []

    create_changes = proposal.changes.filter(
        target_type="RelationshipTypeRule",
        operation=ProposalChange.Operation.CREATE,
        parent_type="RelationshipType",
        parent_id=relationship_type_id,
    ).order_by(
        "created_at",
    )

    for change in create_changes:

        if not change.target_id:
            continue

        values = _extract_created_rule_values(
            change,
        )

        subject_type = object_type_lookup.get(
            str(values["subject_type_id"]),
        )

        object_type = object_type_lookup.get(
            str(values["object_type_id"]),
        )

        items.append(
            SimpleNamespace(
                id=change.target_id,
                relationship_type_id=relationship_type_id,
                subject_type_id=values["subject_type_id"],
                object_type_id=values["object_type_id"],
                subject_type=subject_type,
                object_type=object_type,
                subject_minimum=values["subject_minimum"],
                subject_maximum=values["subject_maximum"],
                object_minimum=values["object_minimum"],
                object_maximum=values["object_maximum"],
                is_proposed=True,
                is_created=True,
                is_deleted=False,
            )
        )

    return items


# =====================================================================
# Working model values
# =====================================================================


def _build_working_model_values(
    model,
    proposal,
):
    """
    Resolve effective editable Model field values.

    Canonical values come from the Model instance. UPDATE proposals
    overlay those values.
    """

    values = {
        "description": model.description,
        "purpose": model.purpose,
        "scope": model.scope,
        "exclusions": model.exclusions,
    }

    proposed_fields = set()

    if proposal:

        for change in proposal.changes.all():

            if (
                change.target_type != "Model"
                or change.target_id != model.id
                or change.operation != ProposalChange.Operation.UPDATE
            ):
                continue

            after = change.after or {}

            field = after.get(
                "field",
            )

            if field not in values:
                continue

            if "value" not in after:
                continue

            values[field] = after["value"]
            proposed_fields.add(field)

    return values, proposed_fields


# =====================================================================
# Common model context
# =====================================================================


def get_model_context(
    request,
    model_id,
):

    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:

        return get_object_or_404(
            Model,
            id=model_id,
        )

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    # =================================================================
    # Active proposal (session-scoped, read-only resolution) and the
    # sidebar's live proposal list
    # =================================================================

    active_proposal = resolve_active_proposal(
        request,
        model,
        request.user,
    )

    proposals = list(
        live_proposals_queryset(model, request.user)
        .prefetch_related("changes")
        .order_by("-created_at")
    )

    for p in proposals:
        p.change_count = p.changes.count()

    # =================================================================
    # Canonical model collections
    # =================================================================

    canonical_object_types = ObjectType.objects.filter(
        model=model,
    ).order_by(
        "sort_order",
        "name",
    )

    canonical_relationship_types = RelationshipType.objects.filter(
        model=model,
    ).order_by(
        "sort_order",
        "name",
    )

    # =================================================================
    # Working ObjectTypes
    # =================================================================

    working_object_types = _build_working_object_types(
        canonical_object_types,
        active_proposal,
    )

    object_type_lookup = _working_object_type_lookup(
        working_object_types,
    )

    # =================================================================
    # Working RelationshipTypes
    # =================================================================

    working_relationship_types = _build_working_relationship_types(
        canonical_relationship_types,
        active_proposal,
        object_type_lookup,
    )

    # =================================================================
    # Working Model fields
    # =================================================================

    working_model_values, working_model_proposed_fields = _build_working_model_values(
        model,
        active_proposal,
    )

    # =================================================================
    # Context
    # =================================================================

    return {
        "model": model,
        # -------------------------------------------------------------
        # Effective / working ontology
        # -------------------------------------------------------------
        "object_types": working_object_types,
        "relationship_types": working_relationship_types,
        # -------------------------------------------------------------
        # Canonical ontology
        # -------------------------------------------------------------
        "canonical_object_types": canonical_object_types,
        "canonical_relationship_types": canonical_relationship_types,
        # -------------------------------------------------------------
        # Effective / working Model fields
        # -------------------------------------------------------------
        "working_model_values": working_model_values,
        "working_model_proposed_fields": (working_model_proposed_fields),
        # -------------------------------------------------------------
        # Proposal state
        # -------------------------------------------------------------
        "active_proposal": active_proposal,
        "proposals": proposals,
        # -------------------------------------------------------------
        # Assisted Work state (sidebar status line)
        # -------------------------------------------------------------
        "active_assisted_task": active_task_for_model(model),
    }
