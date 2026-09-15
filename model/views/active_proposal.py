"""
Session-scoped "active proposal" selection for the multi-proposal
workspace.

There is no persisted is_active field: the active proposal is purely
a per-model pointer in the user's session, re-validated against the
database (ownership + editable status) on every read. This keeps
"which proposal is the current edit target" a UI/session concern,
while the database remains the sole authority on lifecycle status.
"""

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse

from model.models.proposal import Proposal

SESSION_KEY = "active_proposals"

EDITABLE_STATUSES = (Proposal.Status.WORKING, Proposal.Status.FAILED)

LIVE_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.FAILED,
    Proposal.Status.QUEUED,
    Proposal.Status.PROCESSING,
)


def live_proposals_queryset(model, user):
    """
    Every proposal that belongs in the active workspace: WORKING /
    FAILED / QUEUED / PROCESSING, plus COMPLETED proposals not yet
    acknowledged. Used by both the sidebar list and the live-proposal
    cap check.
    """

    return Proposal.objects.filter(
        model=model,
        created_by=user,
    ).filter(
        Q(status__in=LIVE_STATUSES)
        | Q(
            status=Proposal.Status.COMPLETED,
            acknowledged_at__isnull=True,
        )
    )


def get_active_proposal_id(request, model_id):

    return request.session.get(SESSION_KEY, {}).get(str(model_id))


def set_active_proposal_id(request, model_id, proposal_id):

    active = request.session.get(SESSION_KEY, {})
    active[str(model_id)] = str(proposal_id)
    request.session[SESSION_KEY] = active
    request.session.modified = True


def clear_active_proposal_id(request, model_id):

    active = request.session.get(SESSION_KEY, {})

    if active.pop(str(model_id), None) is not None:
        request.session[SESSION_KEY] = active
        request.session.modified = True


def resolve_active_proposal(request, model, user):
    """
    Read-only. Returns the session-pointed Proposal if it still
    exists, is owned by `user`, belongs to `model`, and is still
    WORKING/FAILED -- else None. Never creates anything. A stale
    pointer (deleted/submitted/wrong owner) simply resolves to None;
    it is not proactively cleaned out of the session, since the next
    explicit selection or auto-create will overwrite it anyway.
    """

    proposal_id = get_active_proposal_id(request, model.id)

    if not proposal_id:
        return None

    return (
        Proposal.objects.filter(
            id=proposal_id,
            model=model,
            created_by=user,
            status__in=EDITABLE_STATUSES,
        )
        .prefetch_related("changes")
        .first()
    )


def get_or_create_active_proposal(request, model, user):
    """
    The single write-path entry point used by every editor call site
    that used to call ProposalService.get_or_create_working(...)
    directly. Returns a (proposal, error_response) tuple:

    - (proposal, None) on success -- the resolved active proposal, or
      a freshly created one if none was active.
    - (None, JsonResponse) if creating a new one would exceed
      settings.PROPOSAL_MAX_LIVE_PER_MODEL -- the JsonResponse is
      ready to return as-is from the calling view (status=409).

    Call sites should do:

        proposal, error_response = get_or_create_active_proposal(request, model, request.user)
        if error_response is not None:
            return error_response
    """

    proposal = resolve_active_proposal(request, model, user)

    if proposal is not None:
        return proposal, None

    live_count = live_proposals_queryset(model, user).count()

    if live_count >= settings.PROPOSAL_MAX_LIVE_PER_MODEL:
        return None, JsonResponse(
            {
                "success": False,
                "error": (
                    f"You have reached the maximum of "
                    f"{settings.PROPOSAL_MAX_LIVE_PER_MODEL} active proposals "
                    "for this model. Submit, resolve, or delete one before "
                    "starting another."
                ),
            },
            status=409,
        )

    proposal = Proposal.objects.create(
        model=model,
        created_by=user,
        source=Proposal.Source.USER,
        status=Proposal.Status.WORKING,
        base_revision=model.revision,
        title=_default_title(model, user),
    )

    set_active_proposal_id(request, model.id, proposal.id)

    return proposal, None


def _default_title(model, user):

    n = live_proposals_queryset(model, user).count() + 1

    return f"Proposal {n}"
