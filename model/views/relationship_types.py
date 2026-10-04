from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render

from model.access import get_bulk_editable_model
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.services.proposal.bulk_edit import (
    EmptySelectionError,
    TooManySelectedError,
    dedupe_and_bound,
)
from model.services.proposal.proposal import ProposalService
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.data_context import resolve_working_relationship_type
from model.views.relationship_type_editor import (
    RelationshipTypeLifecycleError,
    apply_relationship_type_lifecycle,
)
from model.views.sidebar import with_updated_sidebar


@login_required
@with_updated_sidebar
def relationship_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    # =================================================================
    # Bulk activate / deactivate
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "bulk_set_relationship_type_status"
    ):

        get_bulk_editable_model(request, model_id)

        desired_raw = str(request.POST.get("is_active", "")).strip().lower()

        if desired_raw not in {"true", "false"}:
            return JsonResponse(
                {"success": False, "error": "Status must be true or false."},
                status=400,
            )

        desired_active = desired_raw == "true"

        try:
            type_ids = dedupe_and_bound(request.POST.getlist("relationship_type_id"))
        except EmptySelectionError:
            return JsonResponse(
                {"success": False, "error": "Select at least one relationship type."},
                status=400,
            )
        except TooManySelectedError as exc:
            return JsonResponse(
                {"success": False, "error": str(exc)},
                status=400,
            )

        # Strict, all-or-nothing resolution -- mirrors object_types.py's
        # bulk status handler.
        resolved = []

        for type_id in type_ids:

            real = RelationshipType.objects.filter(id=type_id, model=model).first()

            if real is not None:
                resolved.append((real, False, type_id))
                continue

            candidate = resolve_working_relationship_type(context, type_id)

            if candidate is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "One or more selected relationship types could "
                            "not be found. Please refresh and try again."
                        ),
                    },
                    status=400,
                )

            resolved.append((candidate, True, type_id))

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        try:
            with transaction.atomic():

                results = {}

                for relationship_type_obj, proposal_only, type_id in resolved:

                    value, proposed = apply_relationship_type_lifecycle(
                        relationship_type=relationship_type_obj,
                        proposal_only=proposal_only,
                        proposal=proposal,
                        model=model,
                        relationship_type_id=type_id,
                        desired_active=desired_active,
                    )

                    results[str(type_id)] = {"value": value, "proposed": proposed}

        except RelationshipTypeLifecycleError as exc:
            return JsonResponse(
                {"success": False, "error": str(exc)},
                status=404,
            )

        return JsonResponse({"success": True, "results": results})

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
