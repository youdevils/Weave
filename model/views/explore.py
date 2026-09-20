"""
Model Explorer: a read-only exploration workspace over the effective model
(canonical data plus the current user's active proposal).

Every endpoint here is GET-only and never writes: no model, proposal or
appearance state changes. The page is a thin shell; the projection, search and
details logic lives in ``model.services.model_graph`` and the visual identity
comes from AppearanceService via the compiler.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from model.services.appearance import AppearanceService
from model.services.model_graph.compiler import compile_model_graph
from model.services.model_graph.details import object_details, relationship_details
from model.services.model_graph.explorer import explore as build_exploration
from model.services.model_graph.facets import build_facets
from model.services.model_graph.provenance import build_provenance
from model.services.model_graph.query import QueryError
from model.services.model_graph.search import search_objects
from model.views.active_proposal import resolve_active_proposal
from model.views.appearance import scoped_model
from model.views.common_context import get_model_context

_PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"


def _exploration(request, model_id):
    """``(model, exploration, error_response)`` for the request's query params."""
    model = scoped_model(request, model_id)
    proposal = resolve_active_proposal(request, model, request.user)

    try:
        return model, build_exploration(model, proposal, request.GET), None
    except QueryError as error:
        return model, None, JsonResponse({"success": False, "error": str(error)}, status=400)


def _graph_response(model, exploration):
    payload = compile_model_graph(model, exploration.dataset, exploration.projection)
    return {
        "payload": payload.to_dict(),
        "summary": exploration.projection.summary.to_dict(),
        # What the server actually applied: the client reconciles its state to this.
        "state": exploration.query.to_state(),
        "dropped": exploration.dropped,
        "canvasBackground": AppearanceService.resolve_theme(model).canvas_background,
    }


@login_required
@require_GET
def explore(request, model_id):
    model = scoped_model(request, model_id)
    context = get_model_context(request, model_id)
    exploration = build_exploration(model, context["active_proposal"], {})

    urls = {
        "graph": reverse("model:explore_graph", args=[model.id]),
        "search": reverse("model:explore_search", args=[model.id]),
        "object": reverse("model:explore_object", args=[model.id, _PLACEHOLDER_ID]),
        "relationship": reverse("model:explore_relationship", args=[model.id, _PLACEHOLDER_ID]),
        "placeholder": _PLACEHOLDER_ID,
    }

    graph = _graph_response(model, exploration)
    context.update(
        {
            "explorer_bootstrap": {
                "graph": graph,
                "facets": build_facets(exploration.dataset, AppearanceService.resolver(model)),
                "urls": urls,
                "hasProposal": bool(context["active_proposal"]),
            },
            "canvas_background": graph["canvasBackground"],
            "explorer_legend": AppearanceService.legend(model),
            "explorer_has_data": bool(exploration.dataset.objects),
        }
    )

    return render(request, "model/explore.html", context)


@login_required
@require_GET
def explore_graph(request, model_id):
    model, exploration, error = _exploration(request, model_id)
    if error:
        return error

    return JsonResponse({"success": True, **_graph_response(model, exploration)})


@login_required
@require_GET
def explore_search(request, model_id):
    _model, exploration, error = _exploration(request, model_id)
    if error:
        return error

    results = search_objects(
        exploration.dataset,
        request.GET.get("q", ""),
        projection=exploration.projection,
    )

    return JsonResponse(
        {
            "success": True,
            **results.to_dict(),
            "state": exploration.query.to_state(),
            "dropped": exploration.dropped,
        }
    )


def _with_provenance(model, target_type, details):
    """
    Add the record's provenance chain (committed proposals only) to its details.
    Derived on read from ProposalChange / EvidenceReference; nothing is written.
    """
    if details is not None:
        specs = {a["key"]: {"label": a["label"], "dataType": a["dataType"]} for a in details["attributes"]}
        details["provenance"] = build_provenance(model, target_type, details["id"], specs)
    return details


def _details_response(exploration, details, kind):
    if details is None:
        return JsonResponse(
            {
                "success": False,
                "code": "not_found",
                "error": f"This {kind} is no longer part of the effective model.",
            },
            status=404,
        )
    return JsonResponse({"success": True, "details": details, "state": exploration.query.to_state()})


@login_required
@require_GET
def explore_object(request, model_id, object_id):
    model, exploration, error = _exploration(request, model_id)
    if error:
        return error

    return _details_response(
        exploration,
        _with_provenance(
            model,
            "Object",
            object_details(exploration.dataset, object_id, exploration.projection),
        ),
        "object",
    )


@login_required
@require_GET
def explore_relationship(request, model_id, relationship_id):
    model, exploration, error = _exploration(request, model_id)
    if error:
        return error

    return _details_response(
        exploration,
        _with_provenance(
            model,
            "Relationship",
            relationship_details(exploration.dataset, relationship_id, exploration.projection),
        ),
        "relationship",
    )
