from types import SimpleNamespace

from django.shortcuts import get_object_or_404

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange

# =====================================================================
# Working ObjectType context
# =====================================================================


def _canonical_object_type_values(object_type):
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

    if not proposal:
        return values

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by(
        "created_at",
    )

    for change in changes:

        after = change.after or {}

        field = after.get(
            "field",
        )

        if field in values and "value" in after:
            values[field] = after["value"]

    return values


def _object_type_is_proposed(
    object_type,
    proposal,
):
    """
    Return True when the ObjectType has any working proposal changes.
    """

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
    Return the effective number of active attributes associated with
    an ObjectType.

    Canonical attributes are counted using their canonical/proposed
    is_active state.

    Proposed CREATE AttributeDefinitions are also included.
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
    Build the working ObjectType collection.

    The returned collection contains:

    - canonical ObjectTypes with effective proposed values;
    - proposed CREATE ObjectTypes that do not yet exist canonically.

    Each item exposes:

    - id
    - name
    - key
    - description
    - sort_order
    - is_active
    - attribute_count
    - is_proposed
    - is_created
    """

    items = []

    canonical_ids = {str(object_type.id) for object_type in object_types}

    # -------------------------------------------------------------
    # Existing canonical ObjectTypes
    # -------------------------------------------------------------

    for object_type in object_types:

        effective_values = _object_type_effective_values(
            object_type,
            proposal,
        )

        item = SimpleNamespace(
            id=object_type.id,
            name=effective_values["name"],
            key=effective_values["key"],
            description=effective_values["description"],
            sort_order=effective_values["sort_order"],
            is_active=effective_values["is_active"],
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

        items.append(item)

    # -------------------------------------------------------------
    # Proposed CREATE ObjectTypes
    # -------------------------------------------------------------

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
                attribute_count=0,
                is_proposed=True,
                is_created=True,
            )

            # -----------------------------------------------------
            # Include proposed AttributeDefinition creates.
            # -----------------------------------------------------

            proposed_object.attribute_count = proposal.changes.filter(
                target_type="AttributeDefinition",
                operation=ProposalChange.Operation.CREATE,
                parent_type="ObjectType",
                parent_id=object_type_id,
            ).count()

            items.append(
                proposed_object,
            )

    # -------------------------------------------------------------
    # Effective ordering
    # -------------------------------------------------------------

    items.sort(
        key=lambda item: (
            item.sort_order,
            item.name.lower(),
        ),
    )

    return items


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
    # Working proposals
    # =================================================================

    my_working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related(
            "changes",
        )
        .first()
    )

    ai_working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related(
            "changes",
        )
        .first()
    )

    my_change_count = my_working_proposal.changes.count() if my_working_proposal else 0

    ai_change_count = ai_working_proposal.changes.count() if ai_working_proposal else 0

    # =================================================================
    # Canonical model collections
    # =================================================================

    canonical_object_types = ObjectType.objects.filter(
        model=model,
    ).order_by(
        "sort_order",
        "name",
    )

    relationship_types = model.relationship_types.all()

    # =================================================================
    # Working model collections
    # =================================================================

    working_object_types = _build_working_object_types(
        canonical_object_types,
        my_working_proposal,
    )

    return {
        "model": model,
        # -------------------------------------------------------------
        # Effective / working model
        # -------------------------------------------------------------
        "object_types": working_object_types,
        "relationship_types": relationship_types,
        # -------------------------------------------------------------
        # Canonical model
        # -------------------------------------------------------------
        "canonical_object_types": canonical_object_types,
        # -------------------------------------------------------------
        # Proposal state
        # -------------------------------------------------------------
        "my_working_proposal": my_working_proposal,
        "my_change_count": my_change_count,
        "ai_working_proposal": ai_working_proposal,
        "ai_change_count": ai_change_count,
    }
