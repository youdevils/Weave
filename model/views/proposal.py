from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import Proposal
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context


@login_required
def proposal(request, model_id):

    # -------------------------------------------------------------
    # Common model context
    # -------------------------------------------------------------

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    working_proposal = context["working_proposal"]

    # -------------------------------------------------------------
    # No working proposal
    # -------------------------------------------------------------

    if not working_proposal or not working_proposal.changes.exists():
        return render(
            request,
            "model/proposal.html",
            {
                **context,
                "proposal": None,
                "changes": [],
            },
        )

    # -------------------------------------------------------------
    # POST — discard change
    # -------------------------------------------------------------

    if request.method == "POST":

        action = request.POST.get("action")
        change_id = request.POST.get("change_id")

        if action == "discard":

            change = working_proposal.changes.filter(
                id=change_id,
            ).first()

            if not change:
                return JsonResponse(
                    {"error": "Change not found."},
                    status=404,
                )

            # Model overview changes currently use the field stored
            # in the change payload.
            field_name = change.after.get("field") if change.after else None

            ProposalService.discard_change(
                proposal=working_proposal,
                target_type=change.target_type,
                target_id=change.target_id,
                field=field_name,
            )

            return JsonResponse(
                {
                    "success": True,
                    "change_id": str(change.id),
                }
            )

        return JsonResponse(
            {"error": "Invalid action."},
            status=400,
        )

    # -------------------------------------------------------------
    # Changes
    # -------------------------------------------------------------

    changes = working_proposal.changes.all()

    context.update(
        {
            "proposal": working_proposal,
            "changes": changes,
        }
    )

    return render(
        request,
        "model/proposal.html",
        context,
    )
