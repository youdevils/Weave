"""Publishing History: a placeholder page for now (no history is listed yet)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET

from ..access import get_publishable_model


@login_required
@require_GET
def publication_history(request, model_id):
    model = get_publishable_model(request, model_id)
    return render(request, "publication/history.html", {"model": model})
