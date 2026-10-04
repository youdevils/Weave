"""
Who may start an Assisted Work operation (Reconcile / Change / Assess) against
a model.

Starting one of these operations is a model-data modification capability, so
this mirrors the access-check shape already used by ingestion/access.py and
model/access.py::get_bulk_editable_model:

  * not a member of the model's workspace  -> 404 (the model's existence is not revealed);
  * a member with the Viewer role          -> 403;
  * Owner or Editor                        -> allowed.

The membership is looked up for *this model's* workspace, so a user who
belongs to several workspaces is never checked against the wrong one.

The Assisted Work landing and task-detail pages are deliberately NOT gated by
this helper -- viewing them only requires model membership, like Overview or
Explore (see model/views/common_context.py::get_model_context). This helper
is for the three entry forms only (and their submit handlers), since a Viewer
should never be shown a live "Start reconciliation" button that would then
403 on click.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from model.models.model import Model
from workspace.models import WorkspaceMember

ASSISTED_WORK_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.EDITOR)


def get_assisted_workable_model(request, model_id) -> Model:
    """The model, if ``request.user`` may start Assisted Work against it;
    raises Http404 / PermissionDenied otherwise."""

    membership = (
        WorkspaceMember.objects.filter(user=request.user, workspace__models__id=model_id)
        .select_related("workspace")
        .first()
    )

    if membership is None:
        raise Http404

    if membership.role not in ASSISTED_WORK_ROLES:
        raise PermissionDenied("Only workspace owners and editors can start assisted work.")

    return Model.objects.get(id=model_id, workspace=membership.workspace)
