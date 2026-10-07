"""
The Celery-worker side of an Assisted operation: claim the task, run the
existing AI orchestration, and interpret the result into a terminal
AssistedTask transition.

A staged run makes several provider calls. Before each one the worker
heartbeats (AssistedTask.updated_at/current_stage, see _heartbeat), so the
stale-RUNNING reclaim measures inactivity rather than total run time; and the
final Proposal commit re-checks, under a row lock inside the commit
transaction, that this task is still RUNNING (_still_running), so a task
reclaimed meanwhile can never leave an orphaned Proposal behind.

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

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from account.services.entitlement import user_can_run_assisted
from ai.services.orchestrator import run_ai_operation
from model.services.proposal.proposal import ProposalLimitReached

from assisted.models import AssistedTask
from assisted.services.cleanup import fail_task
from assisted.services.evidence_extraction import bounded, bounded_blocks, extract_text
from assisted.services.outcome_policy import get_outcome_policy
from assisted.services.results import apply_result

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
    Extracted text per evidence file, matching the {"name", "content",
    "mime_type"} asset shape run_ai_operation already accepts. Upload-time
    validation (assisted.services.evidence.create_evidence) already proved
    every stored file extracts cleanly, so any failure here is unexpected
    and is left to propagate into run_and_finish's own safety net below
    rather than being handled twice.
    """

    assets = []
    limit = settings.ASSISTED_MAX_EVIDENCE_EXTRACTED_CHARS
    for item in task.evidence.all():
        extracted = extract_text(bytes(item.content), filename=item.original_filename)
        asset = {
            "name": item.original_filename,
            "content": bounded(extracted.text, max_chars=limit),
            "mime_type": extracted.mime_type,
        }
        if extracted.blocks:
            # Structural blocks (ai.services.sources segments them); the
            # bounded flat text stays as the fallback/truncation signal.
            asset["blocks"], truncated = bounded_blocks(extracted.blocks, max_chars=limit)
            if truncated and "[... evidence truncated" not in asset["content"]:
                asset["content"] += f"\n\n[... evidence truncated at {limit} characters]"
        assets.append(asset)
    return assets


def _heartbeat(task_id):
    def beat(stage_id: str) -> None:
        AssistedTask.objects.filter(pk=task_id, status=AssistedTask.Status.RUNNING).update(
            current_stage=stage_id[:30], updated_at=timezone.now()
        )

    return beat


def _still_running(task_id):
    def check() -> bool:
        # Called inside the commit's own transaction: the row lock is held
        # until the Proposal is committed, so a concurrent stale reclaim
        # (assisted.services.lifecycle._reclaim_stale) waits, then sees a
        # fresh heartbeat.
        return (
            AssistedTask.objects.select_for_update()
            .filter(pk=task_id, status=AssistedTask.Status.RUNNING)
            .values_list("pk", flat=True)
            .first()
            is not None
        )

    return check


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
            failure_reason="This user's plan does not include Assisted Work.",
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
            on_progress=_heartbeat(task.pk),
            should_commit=_still_running(task.pk),
        )
    except ProposalLimitReached:
        # The orchestrator's own fail-fast ProposalService.assert_capacity
        # check (an optimisation, not the authoritative gate -- see
        # ai.services.orchestrator) raised before any provider call. Give
        # this a specific message instead of letting it fall into the
        # generic exception handler below.
        _finish_failed(
            task,
            failure_reason_code=AssistedTask.FailureReasonCode.EXECUTION_FAILED,
            failure_reason="This model already has the maximum number of open proposals; "
            "resolve or discard one before running this again.",
        )
        return
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
        _finish_ready(task, result=result, outcome_detail=decision.outcome_detail)
    elif decision.status == AssistedTask.Status.COMPLETED:
        _finish_completed(task, outcome_detail=decision.outcome_detail, result=result)
    else:
        _finish_failed(
            task,
            failure_reason_code=decision.failure_reason_code,
            failure_reason=decision.failure_reason,
            result=result,
        )


@transaction.atomic
def _finish_ready(task, *, result, outcome_detail="") -> None:
    locked = AssistedTask.objects.select_for_update().get(pk=task.pk)
    if locked.status != AssistedTask.Status.RUNNING:
        return  # redelivered/raced; another worker already finished this

    locked.status = AssistedTask.Status.READY_FOR_REVIEW
    locked.proposal_id = result.proposal_id
    locked.ai_execution_id = result.execution_id
    locked.outcome_detail = outcome_detail
    locked.ready_for_review_at = timezone.now()
    locked.save(
        update_fields=[
            "status",
            "proposal",
            "ai_execution",
            "outcome_detail",
            "ready_for_review_at",
            "updated_at",
            *apply_result(locked, result),
        ]
    )


@transaction.atomic
def _finish_completed(task, *, outcome_detail, result) -> None:
    """
    A non-Proposal success (today: Reconcile's NO_CHANGE_REQUIRED/UNRESOLVED/
    NEEDS_USER_CLARIFICATION, per ReconcileOutcomePolicy) -- the only path
    that reaches AssistedTask.Status.COMPLETED directly, rather than via the
    proposal_committed signal in assisted.signals. `proposal` is left
    untouched (None); there is no reviewable artifact.
    """

    locked = AssistedTask.objects.select_for_update().get(pk=task.pk)
    if locked.status != AssistedTask.Status.RUNNING:
        return  # redelivered/raced; another worker already finished this

    locked.status = AssistedTask.Status.COMPLETED
    locked.ai_execution_id = result.execution_id
    locked.outcome_detail = outcome_detail
    locked.completed_at = timezone.now()
    locked.save(
        update_fields=[
            "status",
            "ai_execution",
            "outcome_detail",
            "completed_at",
            "updated_at",
            *apply_result(locked, result),
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
