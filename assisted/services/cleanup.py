"""
The single place that performs a terminal FAILED transition for an
AssistedTask -- called by both the Celery execution path
(assisted.services.execution._finish_failed) and the lazy stale-reclaim path
(assisted.services.lifecycle._reclaim_stale), so a task that fails because
the AI run itself failed and a task that fails because nobody ever reported
back end up in exactly the same state, through exactly the same code.

Both callers already hold a row lock on the specific AssistedTask before
calling fail_task (a Txn re-check in execution.py, the select_for_update()
queryset in lifecycle.py) -- fail_task itself does not re-lock, it only needs
to run while that lock is held.
"""

import logging

from django.utils import timezone

from model.services.model_deletion import ModelDeletionBlocked, delete_model

from assisted.models import AssistedTask

logger = logging.getLogger(__name__)


def fail_task(task: AssistedTask, *, failure_reason_code, failure_reason, result=None) -> None:
    task.status = AssistedTask.Status.FAILED
    task.failure_reason_code = failure_reason_code
    task.failure_reason = failure_reason
    task.failed_at = timezone.now()

    update_fields = ["status", "failure_reason_code", "failure_reason", "failed_at", "updated_at"]

    if result is not None:
        task.ai_outcome = result.outcome.value if result.outcome else ""
        task.refinement_cycles = result.refinement_cycles
        task.context_expansions = result.context_expansions
        update_fields += ["ai_outcome", "refinement_cycles", "context_expansions"]

    task.save(update_fields=update_fields)

    # Operation-gated: only an operation whose Model is a disposable artifact
    # of the operation itself (today: CREATE) gets that Model deleted here.
    # RECONCILE/CHANGE/ASSESS operate against a pre-existing Model that must
    # survive a FAILED task untouched.
    if task.operation not in AssistedTask.BOOTSTRAP_MODEL_OPERATIONS or task.model_id is None:
        return

    model = task.model

    try:
        delete_model(model)
    except ModelDeletionBlocked:
        logger.error(
            "Could not delete bootstrap model %s after failed assisted task %s.",
            model.id,
            task.id,
        )
