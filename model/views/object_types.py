from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render

from model.access import get_bulk_editable_model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.bulk_edit import (
    EmptySelectionError,
    TooManySelectedError,
    dedupe_and_bound,
)
from model.services.proposal.proposal import ProposalService
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.data_context import (
    discard_relationships_referencing_object,
    resolve_working_object_type,
)
from model.views.object_type_editor import ObjectTypeLifecycleError, apply_object_type_lifecycle
from model.views.sidebar import with_updated_sidebar


@login_required
@with_updated_sidebar
def object_types(
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
        and request.POST.get("action") == "bulk_set_object_type_status"
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
            type_ids = dedupe_and_bound(request.POST.getlist("object_type_id"))
        except EmptySelectionError:
            return JsonResponse(
                {"success": False, "error": "Select at least one object type."},
                status=400,
            )
        except TooManySelectedError as exc:
            return JsonResponse(
                {"success": False, "error": str(exc)},
                status=400,
            )

        # Strict, all-or-nothing resolution -- mirrors the same two-step
        # (real canonical row, then proposal-only fallback) the single
        # item editor's own view uses, so `canonical_active` inside
        # apply_object_type_lifecycle is always the true canonical value,
        # never the context list's effective-overlaid one.
        resolved = []

        for type_id in type_ids:

            real = ObjectType.objects.filter(id=type_id, model=model).first()

            if real is not None:
                resolved.append((real, False, type_id))
                continue

            candidate = resolve_working_object_type(context, type_id)

            if candidate is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "One or more selected object types could not be "
                            "found. Please refresh and try again."
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

        # The whole batch commits together or not at all: letting
        # ObjectTypeLifecycleError propagate out of this block (rather
        # than returning from inside it) is what makes transaction.atomic
        # roll back any iterations that already succeeded.
        try:
            with transaction.atomic():

                results = {}

                for object_type_obj, proposal_only, type_id in resolved:

                    value, proposed = apply_object_type_lifecycle(
                        object_type=object_type_obj,
                        proposal_only=proposal_only,
                        proposal=proposal,
                        model=model,
                        object_type_id=type_id,
                        desired_active=desired_active,
                    )

                    results[str(type_id)] = {"value": value, "proposed": proposed}

        except ObjectTypeLifecycleError as exc:
            return JsonResponse(
                {"success": False, "error": str(exc)},
                status=404,
            )

        return JsonResponse({"success": True, "results": results})

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
