"""
Who may perform a bulk write against a model's data/ontology.

Bulk edit introduces the first role-gated endpoints in `model/` — ordinary
single-record editing (data_object_editor, object_type_editor, ...) relies
only on get_model_context's membership check, with no Owner/Editor/Viewer
distinction. That gap is deliberately left as-is; this helper is scoped to
the new bulk endpoints only, mirroring the access-check shape already used
by ingestion/access.py and publication/access.py:

  * not a member of the model's workspace  -> 404 (the model's existence is not revealed);
  * a member with the Viewer role          -> 403;
  * Owner or Editor                        -> allowed.

The membership is looked up for *this model's* workspace (unlike
get_model_context's "first membership" shortcut), so a user who belongs to
several workspaces is never checked against the wrong one.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from model.models.model import Model
from workspace.models import WorkspaceMember

BULK_EDIT_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.EDITOR)


def get_bulk_editable_model(request, model_id) -> Model:
    """The model, if request.user may bulk-edit it; Http404 / PermissionDenied otherwise."""

    membership = (
        WorkspaceMember.objects.filter(user=request.user, workspace__models__id=model_id)
        .select_related("workspace")
        .first()
    )

    if membership is None:
        raise Http404

    if membership.role not in BULK_EDIT_ROLES:
        raise PermissionDenied("Only workspace owners and editors can bulk-edit records.")

    return Model.objects.get(id=model_id, workspace=membership.workspace)
