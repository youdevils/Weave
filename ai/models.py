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

    Each provider call of a staged run is an AIExecutionStep (`steps`).

    `proposal` is set only once, and only when `outcome == READY_FOR_REVIEW`
    -- every other outcome leaves it NULL, by design: no partially-generated
    AI proposal is ever left behind for the normal Proposal experience to
    stumble over (see ai.services.staging.commit_proposal).

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

    # Total corrections across every stage (deterministic + review-driven).
    refinement_cycles = models.PositiveIntegerField(default=0)
    # Legacy (pre-staged-workflow) counter; always 0 for staged runs.
    context_expansions = models.PositiveIntegerField(default=0)
    # Logical provider calls (workflow stages + any terminal explanation).
    provider_calls = models.PositiveIntegerField(default=0)
    # {stage_id: {"calls": n, "corrections": n}} -- counters only.
    stage_summary = models.JSONField(default=dict, blank=True)

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


class AIExecutionStep(models.Model):
    """
    One step of a staged AI workflow (ai.services.workflow) -- a provider
    call (which stage, which attempt, what OnyxJar decided about the result,
    the deterministic issue codes that drove a correction, the reviewer's
    verdict, and the call's token usage) or an OnyxJar-only deterministic
    step (provider_call=False, no usage). Like AIExecution itself: digests
    and codes only, never raw prompts, payloads or responses.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    execution = models.ForeignKey(
        AIExecution,
        on_delete=models.CASCADE,
        related_name="steps",
    )

    # Order of this step within the run (provider and deterministic steps alike).
    sequence = models.PositiveIntegerField(default=0)
    provider_call = models.BooleanField(default=True)
    # Provider calls made so far in the run (a deterministic step shares the
    # count of the provider call before it).
    call_index = models.PositiveIntegerField()
    stage = models.CharField(max_length=30)
    stage_attempt = models.PositiveIntegerField(default=1)
    # advance | correct | send_back | finish | provider_error | explain
    decision = models.CharField(max_length=30)
    # {issue_code: count} -- never issue messages.
    issue_codes = models.JSONField(default=dict, blank=True)
    verdict = models.CharField(max_length=30, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    input_digest = models.CharField(max_length=64, blank=True)
    output_digest = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["execution", "sequence", "call_index"]

    def __str__(self):
        return f"{self.stage} #{self.stage_attempt} ({self.decision})"
