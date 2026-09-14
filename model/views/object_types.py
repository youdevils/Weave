from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context
from model.views.data_context import discard_relationships_referencing_object


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
        # any proposed child attributes/objects belonging to it (and,
        # transitively, any proposed Relationship referencing one of
        # those discarded Objects).
        # -------------------------------------------------------------

        is_created = object_type_changes.filter(
            operation=ProposalChange.Operation.CREATE,
        ).exists()

        discarded = {}

        if is_created:
            discarded = ProposalService.discard_children(
                proposal=proposal,
                parent_type="ObjectType",
                parent_id=object_type_id,
                child_target_types={"AttributeDefinition", "Object"},
            )

        # -------------------------------------------------------------
        # Discard ObjectType proposal.
        # -------------------------------------------------------------

        ProposalService.discard_change(
            proposal=proposal,
            target_type="ObjectType",
            target_id=object_type_id,
        )

        for discarded_object_id in discarded.get("Object", set()):
            discard_relationships_referencing_object(proposal, discarded_object_id)

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
