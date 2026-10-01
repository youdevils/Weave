"""
Receivers for model's two domain lifecycle signals (proposal_committed,
proposal_abandoned) -- see model/signals.py and the send sites in
model/services/proposal/{submission,proposal}.py. model only emits these; it
never imports anything from assisted. Connected via AssistedConfig.ready().

Both receivers no-op for a Proposal that didn't originate from an
AssistedTask -- Signal.send() with no connected receivers (e.g. this app not
installed) is a documented Django no-op, so every existing model/ingestion
test of submission.py/proposal.py is unaffected by these signals existing.
"""

import logging

from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from model.signals import proposal_abandoned, proposal_committed

from assisted.models import AssistedTask

logger = logging.getLogger(__name__)


@receiver(proposal_committed)
def _on_proposal_committed(sender, *, proposal_id, model_id, **kwargs):
    with transaction.atomic():
        task = (
            AssistedTask.objects.select_for_update()
            .filter(proposal_id=proposal_id, status=AssistedTask.Status.READY_FOR_REVIEW)
            .first()
        )
        if task is None:
            return  # not every submitted Proposal came from an AssistedTask

        task.status = AssistedTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])


@receiver(proposal_abandoned)
def _on_proposal_abandoned(sender, *, proposal_id, model_id, **kwargs):
    with transaction.atomic():
        task = (
            AssistedTask.objects.select_for_update()
            .filter(proposal_id=proposal_id, status=AssistedTask.Status.READY_FOR_REVIEW)
            .first()
        )
        if task is None:
            return

        task.status = AssistedTask.Status.FAILED
        task.failure_reason_code = AssistedTask.FailureReasonCode.PROPOSAL_ABANDONED
        task.failure_reason = "The proposal from this assisted run was declined."
        task.failed_at = timezone.now()
        task.save(update_fields=["status", "failure_reason_code", "failure_reason", "failed_at", "updated_at"])
