"""
Model-scoped Customise page: model-wide visual language (theme, and the
defaults every Object Type / Relationship Type inherits).

Saves persist directly through AppearanceService and are outside the Proposal
system. The live preview re-compiles the real ontology, so it always reflects
exactly what the Overview will draw.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.services.appearance import AppearanceService
from model.services.ontology_graph.compiler import compile_ontology_graph
from model.views.active_proposal import resolve_active_proposal
from model.views.appearance import apply_appearance_action, scoped_model
from model.views.common_context import get_model_context

SCOPE_FIELD = "scope"


def _preview(model, proposal):
    """Fresh preview data: the compiled ontology plus the theme the page applies itself."""
    payload = compile_ontology_graph(model, proposal).to_dict()
    return {
        "payload": payload,
        "canvas_background": AppearanceService.resolve_theme(model).canvas_background,
    }


@login_required
def customise(request, model_id):
    model = scoped_model(request, model_id)

    if request.method == "POST":
        scope = request.POST.get(SCOPE_FIELD, "").strip()

        error = apply_appearance_action(
            request,
            apply_set=lambda field, value: AppearanceService.update_customisation(model, scope, field, value),
            apply_reset_field=lambda field: AppearanceService.update_customisation(model, scope, field, None),
            # Only model-level customisation; per-type overrides are untouched.
            apply_reset_all=lambda: AppearanceService.reset_customisation(model),
        )

        if error:
            return JsonResponse({"success": False, "error": error}, status=400)

        proposal = resolve_active_proposal(request, model, request.user)
        return JsonResponse(
            {
                "success": True,
                "form": AppearanceService.customisation_form(model),
                **_preview(model, proposal),
            }
        )

    context = get_model_context(request, model_id)
    preview = _preview(model, context["active_proposal"])

    context.update(
        {
            "appearance_form": AppearanceService.customisation_form(model),
            "ontology_payload": preview["payload"],
            "canvas_background": preview["canvas_background"],
            "has_types": bool(preview["payload"]["nodes"]),
        }
    )

    return render(request, "model/customise.html", context)
