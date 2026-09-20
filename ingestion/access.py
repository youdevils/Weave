"""
Who may import data into a model.

Import creates a Proposal, so it is a model-data modification capability:

  * not a member of the model's workspace  -> 404 (the model's existence is not revealed);
  * a member with the Viewer role          -> 403;
  * Owner or Editor                        -> allowed.

The membership is looked up for *this model's* workspace, so a user who belongs
to several workspaces is never checked against the wrong one.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from model.models.model import Model
from workspace.models import WorkspaceMember

IMPORT_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.EDITOR)


def get_importable_model(request, model_id) -> Model:
    """The model, if ``request.user`` may import into it; raises Http404 / PermissionDenied otherwise."""

    membership = (
        WorkspaceMember.objects.filter(user=request.user, workspace__models__id=model_id)
        .select_related("workspace")
        .first()
    )

    if membership is None:
        raise Http404

    if membership.role not in IMPORT_ROLES:
        raise PermissionDenied("Only workspace owners and editors can import data.")

    return Model.objects.get(id=model_id, workspace=membership.workspace)
