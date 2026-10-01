import uuid

from django.conf import settings
from django.db import models


class AIExecution(models.Model):
    """
    Internal execution metadata for one run of an AI operation --
    observability/troubleshooting only. This is not the source of truth for
    model lineage: that remains Proposal/ProposalChange, via `proposal` below.

    `execution_status` (RUNNING/COMPLETED/FAILED) describes whether the AI
    run itself finished; `outcome` describes what it produced. These are
    kept separate on purpose -- a run can COMPLETE with outcome UNRESOLVED
    (every bounded refinement attempt exhausted without a valid result), and
    that is different from the run itself FAILING (a provider/system error).

    `proposal` is set only once, and only when `outcome == READY_FOR_REVIEW`
    -- every other outcome leaves it NULL, by design: no partially-generated
    AI proposal is ever left behind for the normal Proposal experience to
    stumble over (see ai.services.proposal_compiler.compile_and_validate).

    Deliberately does not store raw prompts, full context packets, or raw
    provider responses -- only digests (context_digest/result_digest).
    """

    class ExecutionStatus(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Outcome(models.TextChoices):
        READY_FOR_REVIEW = "ready_for_review", "Ready for review"
        NO_CHANGE_REQUIRED = "no_change_required", "No change required"
        NEEDS_USER_CLARIFICATION = "needs_user_clarification", "Needs user clarification"
        UNRESOLVED = "unresolved", "Unresolved"
        FAILED = "failed", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    operation = models.CharField(max_length=50)

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="ai_executions",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ai_executions",
    )

    proposal = models.ForeignKey(
        "model.Proposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_executions",
    )

    execution_status = models.CharField(
        max_length=20,
        choices=ExecutionStatus.choices,
        default=ExecutionStatus.RUNNING,
    )

    outcome = models.CharField(
        max_length=30,
        choices=Outcome.choices,
        null=True,
        blank=True,
    )

    provider = models.CharField(max_length=50, default="openai")
    provider_model = models.CharField(max_length=100, blank=True)

    refinement_cycles = models.PositiveIntegerField(default=0)
    context_expansions = models.PositiveIntegerField(default=0)

    usage = models.JSONField(default=dict, blank=True)

    context_digest = models.CharField(max_length=64, blank=True)
    result_digest = models.CharField(max_length=64, blank=True)

    error = models.TextField(blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.operation} ({self.execution_status})"
