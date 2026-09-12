from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context


@login_required
def object_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

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
                    "error": "Object type ID is required.",
                },
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "There is no working proposal to discard.",
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
            operation=ProposalChange.Operation.CREATE,
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

    return render(
        request,
        "model/object_types.html",
        context,
    )
