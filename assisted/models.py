"""
The durable, user-facing record of one Assisted operation.

AssistedTask wraps ai.AIExecution (internal, observability-only, hard-deleted
when its Model cascades) and model.Proposal (the reviewable artifact) without
duplicating either's payloads -- see ai.services.execution's module docstring
for why AIExecution never stores raw prompts/responses; this model goes one
step further and never stores raw AI payloads at all, only the small
denormalized outcome/failure fields that must survive a FAILED Assisted
Create, which deletes its own bootstrap Model (and therefore its AIExecution,
since ai.AIExecution.model is CASCADE, not SET_NULL).

Kept deliberately simpler than ai.AIExecution's own execution_status/outcome
split: QUEUED -> RUNNING -> READY_FOR_REVIEW -> COMPLETED, with a terminal
FAILED that carries a structured failure_reason_code/failure_reason instead
of becoming its own status. The AI-outcome -> AssistedTask mapping is a
per-operation policy (assisted.services.outcome_policy), not a global switch,
so a future ASSESS (no Proposal gate) can plug in without changing this model.
"""

import uuid

from django.conf import settings
from django.db import models


class AssistedTask(models.Model):

    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        RECONCILE = "reconcile", "Reconcile"
        CHANGE = "change", "Change"
        ASSESS = "assess", "Assess"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        READY_FOR_REVIEW = "ready_for_review", "Ready for review"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class FailureReasonCode(models.TextChoices):
        EXECUTION_FAILED = "execution_failed", "Execution failed"
        UNRESOLVED = "unresolved", "Unresolved"
        NEEDS_CLARIFICATION = "needs_clarification", "Needs clarification"
        NO_CHANGE_PRODUCED = "no_change_produced", "No change produced"
        PROPOSAL_ABANDONED = "proposal_abandoned", "Proposal abandoned"
        STALE_TIMED_OUT = "stale_timed_out", "Stale / timed out"

    ACTIVE_STATUSES = (Status.QUEUED, Status.RUNNING, Status.READY_FOR_REVIEW)

    # Operations whose `model` is a disposable artifact created *by* the
    # operation itself (today: CREATE's bootstrap Model) -- these get their
    # Model deleted on FAILED (see assisted.services.cleanup.fail_task).
    # RECONCILE/CHANGE/ASSESS operate against a Model that existed before
    # the task was ever created and must survive a FAILED task untouched.
    BOOTSTRAP_MODEL_OPERATIONS = (Operation.CREATE,)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    workspace = models.ForeignKey(
        "workspace.Workspace",
        on_delete=models.CASCADE,
        related_name="assisted_tasks",
    )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assisted_tasks",
    )

    operation = models.CharField(max_length=20, choices=Operation.choices)

    # SET_NULL (not CASCADE): gives "AssistedTask.model=NULL after the
    # bootstrap Model is deleted" for free, mirroring ai.AIExecution.proposal
    # / ingestion.ImportSource.proposal's own SET_NULL convention.
    model = models.ForeignKey(
        "model.Model",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assisted_tasks",
    )

    # OneToOne: exactly one Proposal per task in the Create case; makes the
    # proposal_committed/proposal_abandoned receiver lookup a trivial filter.
    proposal = models.OneToOneField(
        "model.Proposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assisted_task",
    )

    # ai.AIExecution.model is CASCADE -- this row is hard-deleted along with
    # the bootstrap Model on a FAILED Create. SET_NULL here just means the
    # pointer goes stale cleanly; the denormalized fields below are what
    # actually have to survive, copied over before that deletion happens.
    ai_execution = models.OneToOneField(
        "ai.AIExecution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assisted_task",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)

    # Denormalized copy of ai.AIExecution.Outcome's value at finish time --
    # never read back from AIExecution, which may no longer exist.
    ai_outcome = models.CharField(max_length=30, blank=True)

    failure_reason_code = models.CharField(max_length=30, choices=FailureReasonCode.choices, blank=True)
    failure_reason = models.TextField(blank=True)

    # Denormalized copies of AIExecution's own counters -- small integers,
    # not a "large AI payload", safe to duplicate for post-deletion history.
    refinement_cycles = models.PositiveIntegerField(default=0)
    context_expansions = models.PositiveIntegerField(default=0)

    # A single bounded natural-language statement (ai.services.intent caps it
    # at settings.AI_MAX_INTENT_CHARS) -- small and user-authored, kept here
    # so workspace history remains meaningful even once the Model is gone.
    submitted_intent = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ready_for_review_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["model", "status"]),
        ]
        constraints = [
            # Defense-in-depth, not a substitute for the lock in
            # assisted.services.lifecycle.start_assisted_create: this rule is
            # a boolean existence check (unlike PROPOSAL_MAX_LIVE_PER_MODEL,
            # a count, which is why that one has no DB constraint anywhere in
            # this codebase). Converts a lock-path bug into an
            # IntegrityError instead of silent double-creation.
            models.UniqueConstraint(
                fields=["model"],
                condition=models.Q(status__in=["queued", "running", "ready_for_review"]),
                name="unique_active_assisted_task_per_model",
            ),
        ]

    def __str__(self):
        return f"{self.operation} ({self.status})"


class AssistedTaskEvidence(models.Model):
    """
    One uploaded evidence file for an Assisted Create setup request. CASCADE
    from AssistedTask (durable, never deleted): the evidence is inseparable
    history of that one request. Not a second ingestion subsystem -- no
    parsing, no staging/sweep lifecycle, just "store it so the Celery worker,
    in a different process, can read it."
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    task = models.ForeignKey(
        "assisted.AssistedTask",
        on_delete=models.CASCADE,
        related_name="evidence",
    )

    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField(editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_filename
