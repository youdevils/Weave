"""
Reading a Publication back: the hosted View and the Download.

Both read the stored ``Publication.bundle`` (the frozen snapshot) and never the
live model. ``publication_view`` mounts the same shared Explorer kit the
portable file uses, over the embedded bundle. ``publication_download`` renders
that same bundle into the portable HTML document, the same way publishing did.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET

from ..access import get_viewable_publication_model
from ..models import Publication
from ..services import publishing


@login_required
@require_GET
def publication_view(request, model_id, publication_id):
    model = get_viewable_publication_model(request, model_id)
    publication = get_object_or_404(Publication, id=publication_id, model=model)

    if not publication.bundle:
        return render(
            request,
            "publication/view_unavailable.html",
            {"model": model, "publication": publication},
            status=404,
        )

    return render(request, "publication/view.html", {"model": model, "publication": publication})


@login_required
@require_GET
def publication_download(request, model_id, publication_id):
    model = get_viewable_publication_model(request, model_id)
    publication = get_object_or_404(Publication, id=publication_id, model=model)

    try:
        html = publishing.render_for_download(publication)
    except publishing.PublicationError as error:
        return render(
            request,
            "publication/view_unavailable.html",
            {"model": model, "publication": publication},
            status=error.status,
        )

    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = content_disposition_header(as_attachment=True, filename=publication.filename)
    # The file is generated for this one response and must not be kept by any cache.
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Publication-Id"] = str(publication.id)
    response["X-Publication-Sequence"] = str(publication.sequence)
    response["X-Publication-Revision"] = str(publication.source_revision)
    response["X-Publication-Published-At"] = publication.published_at.isoformat()
    return response
