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

    my_working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related("changes")
        .first()
    )

    ai_working_proposal = (
        Proposal.objects.filter(
            model=model,
            created_by=request.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )
        .prefetch_related("changes")
        .first()
    )

    my_change_count = my_working_proposal.changes.count() if my_working_proposal else 0

    ai_change_count = ai_working_proposal.changes.count() if ai_working_proposal else 0

    return {
        "model": model,
        "object_types": model.object_types.all(),
        "relationship_types": model.relationship_types.all(),
        "my_working_proposal": my_working_proposal,
        "my_change_count": my_change_count,
        "ai_working_proposal": ai_working_proposal,
        "ai_change_count": ai_change_count,
    }
