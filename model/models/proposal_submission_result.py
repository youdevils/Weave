import uuid

from django.db import models


class ProposalSubmissionResult(models.Model):

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        VALIDATION_FAILED = "validation_failed", "Validation failed"
        SYSTEM_ERROR = "system_error", "System error"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    proposal = models.OneToOneField(
        "model.Proposal",
        on_delete=models.CASCADE,
        related_name="submission_result",
    )

    outcome = models.CharField(
        max_length=20,
        choices=Outcome.choices,
    )

    before_revision = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    after_revision = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    message = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return f"{self.outcome} for {self.proposal_id}"


class ProposalValidationError(models.Model):

    class Severity(models.TextChoices):
        ERROR = "error", "Error"
        WARNING = "warning", "Warning"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    result = models.ForeignKey(
        "model.ProposalSubmissionResult",
        on_delete=models.CASCADE,
        related_name="errors",
    )

    change = models.ForeignKey(
        "model.ProposalChange",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="validation_errors",
    )

    code = models.CharField(
        max_length=100,
    )

    message = models.TextField()

    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.ERROR,
    )

    target_type = models.CharField(
        max_length=50,
        blank=True,
    )

    target_id = models.UUIDField(
        null=True,
        blank=True,
    )

    field = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.code}: {self.message}"
