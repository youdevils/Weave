from celery import shared_task

from model.services.proposal import submission


@shared_task
def process_next_for_model(model_id):
    """
    Claim and dispatch the next QUEUED proposal for a Model (or
    reclaim a stale PROCESSING one). Not acks_late: if this task dies
    after committing a claim but before dispatching process_proposal,
    that proposal is picked up by claim_next()'s own stale-PROCESSING
    reclaim the next time this task (or submit()) runs.
    """

    submission.claim_next(model_id)


@shared_task(acks_late=True, reject_on_worker_lost=True)
def process_proposal(proposal_id):
    """
    Apply, validate, and commit-or-fail a single proposal. acks_late +
    reject_on_worker_lost so a killed worker's in-flight message is
    redelivered to another worker rather than lost -- the re-run is
    safe because nothing is durably written beyond the PROCESSING
    marker until the apply/validate/commit transaction itself commits.
    """

    submission.process(proposal_id)
