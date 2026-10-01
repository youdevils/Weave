from celery import shared_task

from assisted.services import execution


@shared_task
def run_assisted_create(assisted_task_id):
    """
    Not acks_late/autoretry_for -- redelivery-safety comes from
    execution.claim()'s re-check-under-lock, the same convention
    model.tasks.proposal_tasks already uses (no retry decorators anywhere in
    this codebase; redelivery-safe by construction instead).
    """

    execution.run_and_finish(assisted_task_id)
