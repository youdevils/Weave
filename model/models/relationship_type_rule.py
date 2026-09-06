import uuid

from django.db import models


class RelationshipTypeRule(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    relationship_type = models.ForeignKey(
        "model.RelationshipType",
        on_delete=models.CASCADE,
        related_name="rules",
    )

    subject_type = models.ForeignKey(
        "model.ObjectType",
        on_delete=models.CASCADE,
        related_name="subject_rules",
    )

    object_type = models.ForeignKey(
        "model.ObjectType",
        on_delete=models.CASCADE,
        related_name="object_rules",
    )

    subject_min = models.PositiveIntegerField(
        default=0,
    )

    subject_max = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    object_min = models.PositiveIntegerField(
        default=0,
    )

    object_max = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.relationship_type.name}: "
            f"{self.subject_type.name} → {self.object_type.name}"
        )
