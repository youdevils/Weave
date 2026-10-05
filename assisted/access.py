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

Also checked here: the acting user's Assisted entitlement
(account.services.entitlement.user_can_run_assisted), so Reconcile/Change/
Assess's entry forms are gated the same way Create's already is at
assisted.services.lifecycle.start_assisted_create. Reconcile/Change/Assess
have no real execution yet (assisted.views._stub_submit) -- when they do,
their execution service must call user_can_run_assisted at its own
authoritative pre-execution point exactly like lifecycle.py does, not
invent a second check.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from account.services.entitlement import user_can_run_assisted
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

    if not user_can_run_assisted(request.user):
        raise PermissionDenied("Assisted Work is available on the Collaborator plan.")

    return Model.objects.get(id=model_id, workspace=membership.workspace)
