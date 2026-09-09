from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService


@login_required
def overview(request, model_id):
    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:
        return get_object_or_404(Model, id=model_id)

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    if request.method == "POST":
        field_name = request.POST.get("field")
        action = request.POST.get("action", "save")
        value = request.POST.get("value", "")

        editable_fields = {
            "description",
            "purpose",
            "scope",
            "exclusions",
        }

        if field_name not in editable_fields:
            return JsonResponse(
                {"error": "Invalid field."},
                status=400,
            )

        # ---------------------------------------------------------
        # Discard
        # ---------------------------------------------------------

        if action == "discard":

            proposal = Proposal.objects.filter(
                model=model,
                created_by=request.user,
                status=Proposal.Status.WORKING,
            ).first()

            if not proposal:
                return JsonResponse(
                    {"error": "No working proposal exists."},
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
                    "value": getattr(model, field_name),
                }
            )

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        canonical_value = getattr(model, field_name)

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        change = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
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
            }
        )

    object_types = model.object_types.all()
    relationship_types = model.relationship_types.all()

    working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related("changes")
        .first()
    )

    proposed_values = {}

    if working_proposal:
        for change in working_proposal.changes.all():
            if (
                change.target_type == "Model"
                and change.target_id == model.id
                and change.operation == ProposalChange.Operation.UPDATE
            ):
                field_name = change.after.get("field")

                if field_name:
                    proposed_values[field_name] = change.after.get(
                        "value",
                        "",
                    )

    def effective_value(field_name):
        if field_name in proposed_values:
            return proposed_values[field_name]

        return getattr(model, field_name)

    return render(
        request,
        "model/overview.html",
        {
            "model": model,
            "object_types": object_types,
            "relationship_types": relationship_types,
            "description_value": effective_value("description"),
            "description_proposed": "description" in proposed_values,
            "purpose_value": effective_value("purpose"),
            "purpose_proposed": "purpose" in proposed_values,
            "scope_value": effective_value("scope"),
            "scope_proposed": "scope" in proposed_values,
            "exclusions_value": effective_value("exclusions"),
            "exclusions_proposed": "exclusions" in proposed_values,
        },
    )
