"""The publications index: every Publication created for a model, newest first."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET
from workspace.models import WorkspaceMember

from ..access import PUBLISHING_ROLES, get_viewable_publication_model
from ..models import Publication


@login_required
@require_GET
def publication_history(request, model_id):
    model = get_viewable_publication_model(request, model_id)
    publications = Publication.objects.filter(model=model)  # default ordering: -sequence

    # Any member may view this page; only Owner/Editor get the Publish call to action.
    membership = WorkspaceMember.objects.filter(user=request.user, workspace=model.workspace).first()
    can_publish = membership is not None and membership.role in PUBLISHING_ROLES

    return render(
        request,
        "publication/history.html",
        {"model": model, "publications": publications, "can_publish": can_publish},
    )
