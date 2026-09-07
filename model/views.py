from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from model.models.model import Model


@login_required
def overview(request, model_id):
    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:
        return get_object_or_404(Model, id=model_id)

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    object_types = model.object_types.all()
    relationship_types = model.relationship_types.all()

    return render(
        request,
        "model/overview.html",
        {
            "model": model,
            "object_types": object_types,
            "relationship_types": relationship_types,
        },
    )
