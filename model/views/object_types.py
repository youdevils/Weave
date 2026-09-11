from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

# =====================================================================
# Helpers
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
    Return canonical ObjectType values overlaid with any field-level
    changes in the user's working proposal.
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
    ).order_by("created_at")

    for change in changes:

        after = change.after or {}

        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

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
    Return the effective number of active attributes associated with
    the ObjectType.

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


def _build_object_type_items(
    object_types,
    proposal,
):
    """
    Build the working ObjectType index.

    The returned collection contains:

    - canonical ObjectTypes with effective proposed values;
    - proposed CREATE ObjectTypes that do not yet exist canonically.
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
        ).order_by("created_at")

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

            items.append(proposed_object)

    # -------------------------------------------------------------
    # Effective ordering.
    # -------------------------------------------------------------

    items.sort(
        key=lambda item: (
            item.sort_order,
            item.name.lower(),
        )
    )

    return items


# =====================================================================
# View
# =====================================================================


@login_required
def object_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    proposal = context["my_working_proposal"]

    # =================================================================
    # Discard an ObjectType proposal
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_object_type_proposal"
    ):

        object_type_id = request.POST.get(
            "object_type_id",
        )

        if not object_type_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type ID is required."),
                },
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("There is no working " "proposal to discard."),
                },
                status=400,
            )

        object_type_changes = proposal.changes.filter(
            target_type="ObjectType",
            target_id=object_type_id,
        )

        if not object_type_changes.exists():

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "No proposed changes were found " "for this object type."
                    ),
                },
                status=404,
            )

        # -------------------------------------------------------------
        # If this ObjectType is itself proposed as CREATE, also remove
        # any proposed child attributes belonging to it.
        # -------------------------------------------------------------

        is_created = object_type_changes.filter(
            operation=(ProposalChange.Operation.CREATE)
        ).exists()

        child_target_ids = set()

        if is_created:

            child_changes = proposal.changes.filter(
                parent_type="ObjectType",
                parent_id=object_type_id,
            )

            for change in child_changes:

                if change.target_type == "AttributeDefinition":
                    child_target_ids.add(change.target_id)

        # -------------------------------------------------------------
        # Discard ObjectType proposal.
        # -------------------------------------------------------------

        ProposalService.discard_change(
            proposal=proposal,
            target_type="ObjectType",
            target_id=object_type_id,
        )

        # -------------------------------------------------------------
        # Discard proposed child attributes.
        # -------------------------------------------------------------

        for target_id in child_target_ids:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="AttributeDefinition",
                target_id=target_id,
            )

        return JsonResponse(
            {
                "success": True,
                "removed": is_created,
            }
        )

    # =================================================================
    # Build working index
    # =================================================================

    object_types = ObjectType.objects.filter(
        model=model,
    ).order_by(
        "sort_order",
        "name",
    )

    working_object_types = _build_object_type_items(
        object_types,
        proposal,
    )

    context.update(
        {
            "object_types": working_object_types,
            "has_object_types": bool(working_object_types),
        }
    )

    return render(
        request,
        "model/object_types.html",
        context,
    )
