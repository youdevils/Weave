"""
Starting an Assisted operation, and the one-active-task-per-Model rule.

The lock-then-check-then-create pattern here is the same one
model.services.proposal.proposal.ProposalService.create_working and
model.services.model_deletion.delete_model already use: lock the Model row
first, so the reclaim-then-check-then-create sequence below is one
serialised step and two concurrent requests cannot both create an active
AssistedTask against the same Model.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from account.services.entitlement import user_can_run_assisted
from ai.services.intent import validate_intent
from model.models.model import Model

from assisted.models import AssistedTask
from assisted.services.cleanup import fail_task
from assisted.services.evidence import create_evidence


class AssistedTaskActive(Exception):
    """This Model already has an active (non-terminal) AssistedTask."""


class AssistedEntitlementDenied(Exception):
    """This user's Assisted entitlement (account.CustomUser.assisted_tier)
    does not currently allow running Assisted operations."""


class BootstrapModelGone(Exception):
    """
    This model no longer exists. Reachable when the caller's own stale
    QUEUED/RUNNING CREATE task against this exact Model gets reclaimed by
    _reclaim_stale() below -- fail_task() deletes a CREATE task's bootstrap
    Model as part of that reclaim, which can be the very Model this call was
    about to reuse for a fresh attempt.
    """


@transaction.atomic
def _reclaim_stale(model_id) -> None:
    """
    Lazy reclaim, mirroring model.services.proposal.submission.claim_next's
    stale-PROCESSING reclaim -- no Celery-beat sweep exists in this codebase
    today, and this lazy check is also the recovery path for a
    transaction.on_commit-dispatched .delay() call that silently failed to
    enqueue: the AssistedTask row is already durably QUEUED by that point,
    so nothing is rolled back there -- it simply sits QUEUED until this
    check reclaims it past ASSISTED_TASK_QUEUED_STUCK_THRESHOLD.

    Its own transaction, committed independently of start_assisted_create's
    -- fail_task() may delete this very Model (a stale CREATE task's
    bootstrap Model), and that cleanup must survive even if the caller then
    decides it cannot proceed (see BootstrapModelGone below). Routes every
    reclaim through the shared fail_task() helper (not a bare status flip)
    so a stale CREATE task gets the same full failure cleanup as any other
    failed Create.
    """

    locked_model = Model.objects.select_for_update().filter(pk=model_id).first()
    if locked_model is None:
        return  # already gone for some other reason; nothing to reclaim against

    now = timezone.now()

    stale_queued = Q(
        status=AssistedTask.Status.QUEUED,
        updated_at__lt=now - settings.ASSISTED_TASK_QUEUED_STUCK_THRESHOLD,
    )
    stale_running = Q(
        status=AssistedTask.Status.RUNNING,
        updated_at__lt=now - settings.ASSISTED_TASK_RUNNING_STUCK_THRESHOLD,
    )

    stale = list(
        AssistedTask.objects.select_for_update()
        .filter(model=locked_model)
        .filter(stale_queued | stale_running)
    )

    for task in stale:
        fail_task(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.STALE_TIMED_OUT,
            failure_reason="This assisted run did not report back in time and was marked as failed.",
        )


@transaction.atomic
def _create_task(*, workspace, model_id, user, intent_text, files) -> AssistedTask:
    """
    The actual lock-then-check-then-create step, in its own transaction so
    that _reclaim_stale's cleanup above (possibly including this Model's own
    deletion) is never rolled back by what happens here.
    """

    try:
        locked_model = Model.objects.select_for_update().get(pk=model_id)
    except Model.DoesNotExist:
        raise BootstrapModelGone(
            "This model no longer exists: a previous assisted attempt against "
            "it failed and was cleaned up. Create a new model to try again."
        ) from None

    if AssistedTask.objects.filter(model=locked_model, status__in=AssistedTask.ACTIVE_STATUSES).exists():
        raise AssistedTaskActive("This model already has an assisted operation in progress.")

    intent = validate_intent(intent_text)

    task = AssistedTask.objects.create(
        workspace=workspace,
        creator=user,
        operation=AssistedTask.Operation.CREATE,
        model=locked_model,
        status=AssistedTask.Status.QUEUED,
        submitted_intent=intent.text,
    )

    create_evidence(task, files)

    def _dispatch():
        from assisted.tasks import run_assisted_create

        run_assisted_create.delay(str(task.id))

    transaction.on_commit(_dispatch)

    return task


def start_assisted_create(*, workspace, model, user, intent_text, files) -> AssistedTask:
    """
    Creates the AssistedTask for Assisted Create against an already-created
    bootstrap Model (workspace.views.views.create_model creates the Model
    row before Starting Point is even chosen -- there is no Model creation
    here, only reuse of what already exists).

    The entitlement check runs first and before any Model locking/reclaim --
    this is the authoritative "request/task creation" gate: every caller of
    this function gets it, not just the UI form, so a BASIC user cannot
    reach it by calling the backend directly.
    """

    if not user_can_run_assisted(user):
        raise AssistedEntitlementDenied(
            "Assisted Create is available on the Enhanced tier."
        )

    _reclaim_stale(model.pk)

    return _create_task(workspace=workspace, model_id=model.pk, user=user, intent_text=intent_text, files=files)
