"""
The Celery-worker side of an Assisted operation: claim the task, run the
existing AI orchestration, and interpret the result into a terminal
AssistedTask transition.

Idempotency is "redelivery-safe by construction", the same convention
model.tasks.proposal_tasks already uses -- not acks_late/autoretry_for. claim()
re-checks status under a lock before transitioning to RUNNING, exactly like
model.services.proposal.submission.process()'s `if proposal.status !=
PROCESSING: return`. A worker crash between claim() and _finish_ready/
_finish_failed leaves the task stuck RUNNING, recovered only by the lazy
ASSISTED_TASK_RUNNING_STUCK_THRESHOLD reclaim in
assisted.services.lifecycle._reclaim_stale -- the same accepted-limitation
shape as a crashed Proposal worker relying on PROPOSAL_PROCESSING_STUCK_THRESHOLD.
Re-delivering and re-running the whole AI call automatically (acks_late)
would double real provider cost on every transient redelivery, which this
codebase's other Celery tasks never risk.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from account.services.entitlement import user_can_run_assisted
from ai.services.orchestrator import run_ai_operation

from assisted.models import AssistedTask
from assisted.services.cleanup import fail_task
from assisted.services.outcome_policy import get_outcome_policy

logger = logging.getLogger(__name__)


def claim(assisted_task_id):
    """Txn 1: QUEUED -> RUNNING, only if still QUEUED. A racing/redelivered
    call, or one against an already-reclaimed-stale task, safely no-ops."""

    with transaction.atomic():
        task = AssistedTask.objects.select_for_update().filter(id=assisted_task_id).first()

        if task is None or task.status != AssistedTask.Status.QUEUED:
            return None

        task.status = AssistedTask.Status.RUNNING
        task.save(update_fields=["status", "updated_at"])

    return task


def _assets_for(task):
    """
    bytes -> best-effort UTF-8 text per evidence file, matching the
    {"name", "content", "mime_type"} asset shape run_ai_operation already
    accepts. No OCR/parsing layer exists anywhere in this codebase; this is a
    known MVP limitation, not something to build out here.
    """

    assets = []
    for item in task.evidence.all():
        text = bytes(item.content).decode("utf-8", errors="replace")
        assets.append({"name": item.original_filename, "content": text, "mime_type": item.content_type})
    return assets


def run_and_finish(assisted_task_id, *, provider=None) -> None:
    """`provider` is test-only injection, forwarded to run_ai_operation
    exactly as its own `provider` kwarg already allows (ai.tests.support's
    ScriptedProvider/RaisingProvider) -- no new test-double machinery."""

    task = claim(assisted_task_id)
    if task is None:
        return

    if task.model_id is None:
        _finish_failed(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="This assisted run's model no longer exists.",
        )
        return

    # Defensive, independent of the entitlement check already made at task
    # creation (assisted.services.lifecycle.start_assisted_create): a
    # queued/forged/stale task must not get to spend real provider cost just
    # because the creator's entitlement changed (or was never valid) between
    # creation and this worker actually picking it up.
    if not user_can_run_assisted(task.creator):
        _finish_failed(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.ENTITLEMENT_DENIED,
            failure_reason="This user is not entitled to run Assisted operations.",
        )
        return

    try:
        result = run_ai_operation(
            operation_id=task.operation,
            model=task.model,
            user=task.creator,
            intent_text=task.submitted_intent,
            assets=_assets_for(task),
            provider=provider,
        )
    except Exception:
        logger.exception("Unexpected error running assisted task %s", assisted_task_id)
        _finish_failed(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="An unexpected error occurred while running this assisted operation.",
        )
        return

    decision = get_outcome_policy(task.operation).decide(operation_result=result)

    if decision.status == AssistedTask.Status.READY_FOR_REVIEW:
        _finish_ready(task, result=result)
    else:
        _finish_failed(
            task,
            failure_reason_code=decision.failure_reason_code,
            failure_reason=decision.failure_reason,
            result=result,
        )


@transaction.atomic
def _finish_ready(task, *, result) -> None:
    locked = AssistedTask.objects.select_for_update().get(pk=task.pk)
    if locked.status != AssistedTask.Status.RUNNING:
        return  # redelivered/raced; another worker already finished this

    locked.status = AssistedTask.Status.READY_FOR_REVIEW
    locked.proposal_id = result.proposal_id
    locked.ai_execution_id = result.execution_id
    locked.ai_outcome = result.outcome.value if result.outcome else ""
    locked.refinement_cycles = result.refinement_cycles
    locked.context_expansions = result.context_expansions
    locked.ready_for_review_at = timezone.now()
    locked.save(
        update_fields=[
            "status",
            "proposal",
            "ai_execution",
            "ai_outcome",
            "refinement_cycles",
            "context_expansions",
            "ready_for_review_at",
            "updated_at",
        ]
    )


@transaction.atomic
def _finish_failed(task, *, failure_reason_code, failure_reason, result=None) -> None:
    locked = AssistedTask.objects.select_for_update().get(pk=task.pk)
    if locked.status != AssistedTask.Status.RUNNING:
        return  # redelivered/raced; another worker already finished this

    fail_task(
        locked,
        failure_reason_code=failure_reason_code,
        failure_reason=failure_reason,
        result=result,
    )
