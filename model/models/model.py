import uuid

from django.db import models


class Model(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey(
        "workspace.Workspace",
        on_delete=models.CASCADE,
        related_name="models",
    )

    name = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
    )

    purpose = models.TextField(
        blank=True,
    )

    scope = models.TextField(
        blank=True,
    )

    exclusions = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    revision = models.PositiveIntegerField(
        default=0,
    )

    # Visual customisation document. Its structure is private to
    # model.services.appearance.AppearanceService; nothing else reads or
    # writes its keys. Not governed by the Proposal system.
    appearance = models.JSONField(
        default=dict,
        blank=True,
    )

    def __str__(self):
        return self.name
