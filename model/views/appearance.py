"""
Direct-save endpoint for Object Type / Relationship Type appearance.

Visual customisation is not governed by the Proposal system: these POSTs
persist immediately through AppearanceService and never create or touch a
ProposalChange. Views only pass values through; the service owns validation,
storage and the shape of what it returns.
"""

from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from model.models.model import Model
from model.services.appearance import (
    COLOUR_ELIGIBLE_DATA_TYPES,
    OBJECT_TYPE,
    RELATIONSHIP_TYPE,
    AppearanceService,
    AppearanceValidationError,
    UnknownTypeError,
)
from model.views.active_proposal import resolve_active_proposal
from model.views.data_context import (
    build_object_attribute_definitions,
    build_relationship_attribute_definitions,
)

# Fields whose value must be one of the type's current eligible (Choice/
# Boolean, canonical-or-proposed) attribute keys -- checked here, at the one
# place that has both a proposal and the appearance POST vocabulary in scope.
ATTRIBUTE_SELECT_FIELDS = ("background_attribute", "border_attribute", "colour_attribute")


def scoped_model(request, model_id):
    """The model, if the user belongs to its workspace; 404 otherwise."""
    membership = request.user.workspace_memberships.select_related("workspace").first()
    if not membership:
        raise Http404
    return get_object_or_404(Model, id=model_id, workspace=membership.workspace)


def _eligible_attributes(model, kind, type_id, proposal):
    """
    ``[(key, name), ...]`` for a type's current eligible (Choice/Boolean)
    attributes, reusing the same effective-attribute resolution the graph
    compiler and the type editors use -- never re-derived here.
    """
    if kind == OBJECT_TYPE:
        object_type = SimpleNamespace(id=type_id)
        definitions = build_object_attribute_definitions(object_type, proposal)
    else:
        relationship_type = SimpleNamespace(id=type_id)
        definitions = build_relationship_attribute_definitions(relationship_type, proposal)
    return [
        (definition.key, definition.name) for definition in definitions if definition.data_type in COLOUR_ELIGIBLE_DATA_TYPES
    ]


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

    proposal = resolve_active_proposal(request, model, request.user)
    eligible_attributes = _eligible_attributes(model, kind, type_id, proposal)
    valid_attribute_keys = {key for key, _name in eligible_attributes}

    def apply_set(field, value):
        AppearanceService.set_type_style(
            model,
            kind,
            type_id,
            field,
            value,
            valid_attribute_keys=valid_attribute_keys if field in ATTRIBUTE_SELECT_FIELDS else None,
        )

    try:
        error = apply_appearance_action(
            request,
            apply_set=apply_set,
            apply_reset_field=lambda field: AppearanceService.clear_type_style(model, kind, type_id, field),
            apply_reset_all=lambda: AppearanceService.clear_type_style(model, kind, type_id),
        )
    except UnknownTypeError:
        return JsonResponse({"success": False, "error": "Unknown type."}, status=404)

    if error:
        return JsonResponse({"success": False, "error": error}, status=400)

    return JsonResponse(
        {
            "success": True,
            "form": AppearanceService.type_form(model, kind, type_id, eligible_attributes=eligible_attributes),
        }
    )


@login_required
@require_POST
def attribute_value_appearance(request, model_id, kind, type_id, attribute_key):
    """
    Direct-save endpoint for one Choice/Boolean attribute's value->colour map.
    Independent of whether the attribute is currently selected as a
    background/border/line colour source anywhere.
    """
    model = scoped_model(request, model_id)

    if not AppearanceService.is_known_type(model, kind, type_id):
        return JsonResponse({"success": False, "error": "Unknown type."}, status=404)

    error = apply_appearance_action(
        request,
        apply_set=lambda value_key, colour: AppearanceService.set_attribute_colour(
            model, kind, type_id, attribute_key, value_key, colour
        ),
        apply_reset_field=lambda value_key: AppearanceService.clear_attribute_colour(
            model, kind, type_id, attribute_key, value_key
        ),
        apply_reset_all=lambda: AppearanceService.clear_attribute_colour(model, kind, type_id, attribute_key),
    )

    if error:
        return JsonResponse({"success": False, "error": error}, status=400)

    return JsonResponse(
        {
            "success": True,
            "colours": AppearanceService.attribute_value_colours(model, kind, type_id, attribute_key),
        }
    )
