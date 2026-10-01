"""
Who may use Publishing for a model.

Publishing (creating a new Publication) sends model content out of OnyxJar, so
it is stricter than the membership-only rule most model pages use:

  * not a member of the model's workspace  -> 404 (the model's existence is not revealed);
  * a member with the Viewer role          -> 403;
  * Owner or Editor                        -> allowed.

Looking at publications that already exist (the index, a hosted View, a
Download) is not publishing: any member who can see the model at all may use
them, same as the model app's own view/explore pages.

The membership is looked up for *this model's* workspace, so a user in several
workspaces is never checked against the wrong one.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from model.models.model import Model
from workspace.models import WorkspaceMember

PUBLISHING_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.EDITOR)


def _membership(request, model_id):
    return (
        WorkspaceMember.objects.filter(user=request.user, workspace__models__id=model_id)
        .select_related("workspace")
        .first()
    )


def get_publishable_model(request, model_id) -> Model:
    """The model, if ``request.user`` may publish it; raises Http404 / PermissionDenied otherwise."""
    membership = _membership(request, model_id)
    if membership is None:
        raise Http404

    if membership.role not in PUBLISHING_ROLES:
        raise PermissionDenied("Only workspace owners and editors can publish a model.")

    return Model.objects.get(id=model_id, workspace=membership.workspace)


def get_viewable_publication_model(request, model_id) -> Model:
    """The model, if ``request.user`` is any member of its workspace; raises Http404 otherwise."""
    membership = _membership(request, model_id)
    if membership is None:
        raise Http404

    return Model.objects.get(id=model_id, workspace=membership.workspace)
