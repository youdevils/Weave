"""
Direct-save endpoint for Object Type / Relationship Type appearance.

Visual customisation is not governed by the Proposal system: these POSTs
persist immediately through AppearanceService and never create or touch a
ProposalChange. Views only pass values through; the service owns validation,
storage and the shape of what it returns.
"""

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from model.models.model import Model
from model.services.appearance import (
    AppearanceService,
    AppearanceValidationError,
    UnknownTypeError,
)


def scoped_model(request, model_id):
    """The model, if the user belongs to its workspace; 404 otherwise."""
    membership = request.user.workspace_memberships.select_related("workspace").first()
    if not membership:
        raise Http404
    return get_object_or_404(Model, id=model_id, workspace=membership.workspace)


def apply_appearance_action(request, apply_set, apply_reset_field, apply_reset_all):
    """
    Interpret the shared appearance POST vocabulary:

        {field, value}                     set (an empty value clears)
        {action: "reset_field", field}     clear one field
        {action: "reset_all"}              clear everything in this scope

    Returns an error string for a bad request, or None on success. Validation
    errors raised by the service are turned into messages here.
    """
    action = request.POST.get("action", "").strip()
    field = request.POST.get("field", "").strip()

    try:
        if action == "reset_all":
            apply_reset_all()
        elif action == "reset_field":
            if not field:
                return "A field is required."
            apply_reset_field(field)
        elif action == "":
            if not field:
                return "A field is required."
            apply_set(field, request.POST.get("value", ""))
        else:
            return "Unknown action."
    except AppearanceValidationError as error:
        return str(error)

    return None


@login_required
@require_POST
def type_appearance(request, model_id, kind, type_id):
    model = scoped_model(request, model_id)

    if not AppearanceService.is_known_type(model, kind, type_id):
        return JsonResponse({"success": False, "error": "Unknown type."}, status=404)

    try:
        error = apply_appearance_action(
            request,
            apply_set=lambda field, value: AppearanceService.set_type_style(model, kind, type_id, field, value),
            apply_reset_field=lambda field: AppearanceService.clear_type_style(model, kind, type_id, field),
            apply_reset_all=lambda: AppearanceService.clear_type_style(model, kind, type_id),
        )
    except UnknownTypeError:
        return JsonResponse({"success": False, "error": "Unknown type."}, status=404)

    if error:
        return JsonResponse({"success": False, "error": error}, status=400)

    return JsonResponse({"success": True, "form": AppearanceService.type_form(model, kind, type_id)})
