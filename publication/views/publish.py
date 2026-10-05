"""
The Publishing page and its endpoints.

    GET  publish/          the page (defaults resolved from the last successful publication)
    GET  publish/search/   find objects to use as starting points (a locator, not a scope rule)
    POST publish/preview/  the bundle a definition would publish (read-only)
    POST publish/submit/   publish: record the publication and report where to find it

Views only translate HTTP: access control, JSON in and out. The definition, the
preview and the publishing rules all live in ``publication.services``; View and
Download (reading a Publication back) live in ``publication.views.detail``.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from account.services.entitlement import user_can_publish
from model.services.appearance import AppearanceService
from model.services.model_graph.facets import build_facets
from model.services.model_graph.search import search_objects

from ..access import get_publishable_model
from ..services import publishing
from ..services.config import DEFAULT_DEPTH, MAX_DEPTH
from ..services.defaults import resolve_defaults
from ..services.filenames import default_filename


def _config_document(config) -> dict:
    """A sanitised definition in the shape the page edits and posts back."""
    return {
        "title": config.title,
        "description": config.description,
        "filename": config.filename,
        "scope": config.scope.to_dict(),
        "presentation": config.presentation.to_dict(),
        "default_view": config.default_view.to_dict(),
    }


def _error(error: publishing.PublicationError) -> JsonResponse:
    return JsonResponse(
        {"success": False, "code": error.code, "error": str(error), **error.details}, status=error.status
    )


def _json_body(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _bad_request(message="The request body must be a JSON object."):
    return JsonResponse({"success": False, "code": "invalid", "error": message}, status=400)


@login_required
@require_GET
def publish(request, model_id):
    model = get_publishable_model(request, model_id)

    if not user_can_publish(request.user):
        return render(request, "publication/publish_unavailable.html", {"model": model})

    model, canonical = publishing.load_canonical(model.id)
    defaults, previous = resolve_defaults(model, canonical)

    bootstrap = {
        "revision": model.revision,
        "config": _config_document(defaults.config),
        "notices": defaults.notices,
        "facets": build_facets(canonical, AppearanceService.resolver(model)),
        "roots": publishing.named_objects(canonical, defaults.config.scope.roots),
        "previous": (
            {
                "sequence": previous.sequence,
                "title": previous.title,
                "revision": previous.source_revision,
                "publishedAt": previous.published_at.isoformat(),
            }
            if previous
            else None
        ),
        "modelAccent": AppearanceService.resolve_theme(model).accent,
        "defaultFilename": default_filename(model.name, model.revision),
        "depth": {"default": DEFAULT_DEPTH, "max": MAX_DEPTH},
        "urls": {
            "search": reverse("publication:publish_search", args=[model.id]),
            "preview": reverse("publication:publish_preview", args=[model.id]),
            "submit": reverse("publication:publish_submit", args=[model.id]),
        },
    }

    return render(
        request,
        "publication/publish.html",
        {
            "model": model,
            "publish_bootstrap": bootstrap,
            "canvas_background": AppearanceService.resolve_theme(model).canvas_background,
            "previous": previous,
        },
    )


@login_required
@require_GET
def publish_search(request, model_id):
    model = get_publishable_model(request, model_id)
    _model, canonical = publishing.load_canonical(model.id)

    results = search_objects(canonical, request.GET.get("q", ""))
    return JsonResponse({"success": True, **results.to_dict()})


@login_required
@require_POST
def publish_preview(request, model_id):
    model = get_publishable_model(request, model_id)
    body = _json_body(request)
    if body is None:
        return _bad_request()

    try:
        preview = publishing.preview(model.id, body.get("config"))
    except publishing.PublicationError as error:
        return _error(error)

    return JsonResponse(
        {
            "success": True,
            "revision": preview.revision,
            "digest": preview.digest,
            "summary": preview.summary,
            "notices": preview.notices,
            "tooLarge": preview.too_large,
            "config": _config_document(preview.config),
            "roots": preview.roots,
            "bundle": preview.bundle,
        }
    )


@login_required
@require_POST
def publish_submit(request, model_id):
    model = get_publishable_model(request, model_id)
    body = _json_body(request)
    if body is None:
        return _bad_request()

    try:
        artifact = publishing.publish(model.id, request.user, body.get("config"), body.get("expected"))
    except publishing.PublicationError as error:
        return _error(error)

    # The document was already rendered and validated as part of publishing
    # (the correctness gate); it is not sent here. View and Download each read
    # the stored Publication back on their own, so publishing itself only needs
    # to report what was created and where to find it.
    publication = artifact.publication
    return JsonResponse(
        {
            "success": True,
            "publication": {
                "id": str(publication.id),
                "sequence": publication.sequence,
                "title": publication.title,
                "revision": publication.source_revision,
                "publishedAt": publication.published_at.isoformat(),
            },
            "urls": {
                "view": reverse("publication:publication_view", args=[model.id, publication.id]),
                "download": reverse("publication:publication_download", args=[model.id, publication.id]),
                "index": reverse("publication:publication_history", args=[model.id]),
            },
        }
    )
