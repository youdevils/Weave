from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context


@login_required
def relationship_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    proposal = context["active_proposal"]

    # =================================================================
    # Discard a RelationshipType proposal
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_relationship_type_proposal"
    ):

        relationship_type_id = request.POST.get(
            "relationship_type_id",
        )

        if not relationship_type_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type ID is required.",
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

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": "This proposal is locked and cannot be modified.",
                },
                status=400,
            )

        relationship_type_changes = proposal.changes.filter(
            target_type="RelationshipType",
            target_id=relationship_type_id,
        )

        if not relationship_type_changes.exists():
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "No proposed changes were found " "for this relationship type."
                    ),
                },
                status=404,
            )

        # -------------------------------------------------------------
        # If this RelationshipType itself is proposed as CREATE, also
        # remove proposed child attributes, rules, and relationships.
        # -------------------------------------------------------------

        is_created = relationship_type_changes.filter(
            operation=ProposalChange.Operation.CREATE,
        ).exists()

        if is_created:
            ProposalService.discard_children(
                proposal=proposal,
                parent_type="RelationshipType",
                parent_id=relationship_type_id,
                child_target_types={
                    "AttributeDefinition",
                    "RelationshipTypeRule",
                    "Relationship",
                },
            )

        # -------------------------------------------------------------
        # Discard RelationshipType proposal.
        # -------------------------------------------------------------

        ProposalService.discard_change(
            proposal=proposal,
            target_type="RelationshipType",
            target_id=relationship_type_id,
        )

        return JsonResponse(
            {
                "success": True,
                "removed": is_created,
            }
        )

    # =================================================================
    # Render
    # =================================================================

    return render(
        request,
        "model/relationship_types.html",
        context,
    )
