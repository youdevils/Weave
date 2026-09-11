from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

EDITABLE_FIELDS = {
    "description",
    "purpose",
    "scope",
    "exclusions",
}


@login_required
def overview(request, model_id):

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    # ================================================================
    # POST - proposal-aware field editing
    # ================================================================

    if request.method == "POST":

        field_name = request.POST.get(
            "field",
            "",
        ).strip()

        action = request.POST.get(
            "action",
            "",
        ).strip()

        value = request.POST.get(
            "value",
            "",
        )

        if field_name not in EDITABLE_FIELDS:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid field.",
                },
                status=400,
            )

        # ============================================================
        # DISCARD
        # ============================================================

        if action == "discard":

            proposal = Proposal.objects.filter(
                model=model,
                created_by=request.user,
                source=Proposal.Source.USER,
                status=Proposal.Status.WORKING,
            ).first()

            if not proposal:

                return JsonResponse(
                    {
                        "success": False,
                        "error": ("No working proposal exists."),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Model",
                target_id=model.id,
                field=field_name,
            )

            return JsonResponse(
                {
                    "success": True,
                    "field": field_name,
                    "value": getattr(
                        model,
                        field_name,
                    ),
                    "proposed": False,
                }
            )

        # ============================================================
        # SAVE
        # ============================================================

        if action:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid action.",
                },
                status=400,
            )

        canonical_value = getattr(
            model,
            field_name,
        )

        # ------------------------------------------------------------
        # If the proposed value is the canonical value, there is no
        # change to propose. Remove any existing proposal for this
        # field.
        # ------------------------------------------------------------

        if value == canonical_value:

            proposal = Proposal.objects.filter(
                model=model,
                created_by=request.user,
                source=Proposal.Source.USER,
                status=Proposal.Status.WORKING,
            ).first()

            if proposal:

                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="Model",
                    target_id=model.id,
                    field=field_name,
                )

            return JsonResponse(
                {
                    "success": True,
                    "field": field_name,
                    "value": canonical_value,
                    "proposed": False,
                }
            )

        # ------------------------------------------------------------
        # Get/create working proposal
        # ------------------------------------------------------------

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        change = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            parent_type="",
            parent_id=None,
            field=field_name,
            before={
                "field": field_name,
                "value": canonical_value,
            },
            after={
                "field": field_name,
                "value": value,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "proposal_id": str(proposal.id),
                "change_id": str(change.id),
                "field": field_name,
                "value": value,
                "proposed": True,
            }
        )

    # ================================================================
    # GET - calculate effective values
    # ================================================================

    working_proposal = context["my_working_proposal"]

    proposed_values = {}

    if working_proposal:

        for change in working_proposal.changes.all():

            if (
                change.target_type == "Model"
                and change.target_id == model.id
                and change.operation == ProposalChange.Operation.UPDATE
            ):

                field_name = change.after.get("field")

                if field_name and field_name in EDITABLE_FIELDS:

                    proposed_values[field_name] = change.after.get(
                        "value",
                        "",
                    )

    def effective_value(field_name):

        if field_name in proposed_values:

            return proposed_values[field_name]

        return getattr(
            model,
            field_name,
        )

    context.update(
        {
            "description_value": effective_value("description"),
            "description_proposed": ("description" in proposed_values),
            "purpose_value": effective_value("purpose"),
            "purpose_proposed": ("purpose" in proposed_values),
            "scope_value": effective_value("scope"),
            "scope_proposed": ("scope" in proposed_values),
            "exclusions_value": effective_value("exclusions"),
            "exclusions_proposed": ("exclusions" in proposed_values),
        }
    )

    return render(
        request,
        "model/overview.html",
        context,
    )
