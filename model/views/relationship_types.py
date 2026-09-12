from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import ProposalChange
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

    proposal = context["my_working_proposal"]

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
        # remove proposed child attributes and rules.
        # -------------------------------------------------------------

        is_created = relationship_type_changes.filter(
            operation=ProposalChange.Operation.CREATE,
        ).exists()

        child_attribute_ids = set()
        child_rule_ids = set()

        if is_created:

            child_changes = proposal.changes.filter(
                parent_type="RelationshipType",
                parent_id=relationship_type_id,
            )

            for change in child_changes:

                if change.target_type == "AttributeDefinition":
                    child_attribute_ids.add(
                        change.target_id,
                    )

                elif change.target_type == "RelationshipTypeRule":
                    child_rule_ids.add(
                        change.target_id,
                    )

        # -------------------------------------------------------------
        # Discard RelationshipType proposal.
        # -------------------------------------------------------------

        ProposalService.discard_change(
            proposal=proposal,
            target_type="RelationshipType",
            target_id=relationship_type_id,
        )

        # -------------------------------------------------------------
        # Discard proposed child attributes.
        # -------------------------------------------------------------

        for target_id in child_attribute_ids:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="AttributeDefinition",
                target_id=target_id,
            )

        # -------------------------------------------------------------
        # Discard proposed child rules.
        # -------------------------------------------------------------

        for target_id in child_rule_ids:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="RelationshipTypeRule",
                target_id=target_id,
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
