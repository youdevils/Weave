from django.shortcuts import get_object_or_404

from model.models.model import Model
from model.models.proposal import Proposal


def get_model_context(request, model_id):

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

    working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related("changes")
        .first()
    )

    return {
        "model": model,
        "object_types": model.object_types.all(),
        "relationship_types": model.relationship_types.all(),
        "working_proposal": working_proposal,
        "proposal_change_count": (
            working_proposal.changes.count() if working_proposal else 0
        ),
    }
