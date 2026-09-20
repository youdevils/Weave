import uuid

from django.conf import settings
from django.db import models


class Proposal(models.Model):

    class Source(models.TextChoices):
        USER = "user", "User"
        AI = "ai", "AI"

    class Status(models.TextChoices):
        WORKING = "working", "Working"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    class ValidationStatus(models.TextChoices):
        NOT_VALIDATED = "not_validated", "Not validated"
        VALID = "valid", "Valid"
        INVALID = "invalid", "Invalid"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="proposals",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_proposals",
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.USER,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WORKING,
    )

    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.NOT_VALIDATED,
    )

    base_revision = models.PositiveIntegerField(
        default=1,
    )

    title = models.CharField(
        max_length=200,
        blank=True,
    )

    # The proposal-level "Change note": optional, human-entered context for
    # why the proposal exists. Not evidence, and never required.
    summary = models.TextField(
        blank=True,
        verbose_name="Change note",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # When validation passed and the changes were committed (status
    # COMPLETED). Distinct from acknowledged_at, which is the proposer
    # dismissing the result, and from updated_at, which moves on rename.
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model", "status"]),
        ]

    def __str__(self):
        return self.title or f"Proposal for {self.model.name}"


class ProposalChange(models.Model):

    class Source(models.TextChoices):
        USER = "user", "User"
        AI = "ai", "AI"

    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    class ReviewStatus(models.TextChoices):
        UNREVIEWED = "unreviewed", "Unreviewed"
        REVIEWED = "reviewed", "Reviewed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    proposal = models.ForeignKey(
        "model.Proposal",
        on_delete=models.CASCADE,
        related_name="changes",
    )

    source = models.CharField(
        max_length=20,
        choices=Source.choices,
    )

    operation = models.CharField(
        max_length=20,
        choices=Operation.choices,
    )

    target_type = models.CharField(
        max_length=50,
    )

    target_id = models.UUIDField(
        null=True,
        blank=True,
    )

    parent_type = models.CharField(
        max_length=50,
        blank=True,
    )

    parent_id = models.UUIDField(
        null=True,
        blank=True,
    )

    before = models.JSONField(
        null=True,
        blank=True,
    )

    after = models.JSONField(
        null=True,
        blank=True,
    )

    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.UNREVIEWED,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            # Provenance looks a target's changes up across proposals.
            models.Index(fields=["target_id", "target_type"]),
        ]

    def __str__(self):
        return f"{self.operation} {self.target_type} {self.target_id}"
