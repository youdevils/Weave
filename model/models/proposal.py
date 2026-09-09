import uuid

from django.conf import settings
from django.db import models


class Proposal(models.Model):

    class Status(models.TextChoices):
        WORKING = "working", "Working"
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        WITHDRAWN = "withdrawn", "Withdrawn"

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

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WORKING,
    )

    base_revision = models.PositiveIntegerField(
        default=1,
    )

    title = models.CharField(
        max_length=200,
        blank=True,
    )

    summary = models.TextField(
        blank=True,
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

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Proposal for {self.model.name}"


class ProposalChange(models.Model):

    class Operation(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

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

    before = models.JSONField(
        null=True,
        blank=True,
    )

    after = models.JSONField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.operation} " f"{self.target_type} " f"{self.target_id}"
