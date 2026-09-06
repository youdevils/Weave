import uuid

from django.db import models


class Relationship(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="model_relationships",
    )

    relationship_type = models.ForeignKey(
        "model.RelationshipType",
        on_delete=models.PROTECT,
        related_name="relationships",
    )

    subject = models.ForeignKey(
        "model.Object",
        on_delete=models.CASCADE,
        related_name="subject_relationships",
    )

    object = models.ForeignKey(
        "model.Object",
        on_delete=models.CASCADE,
        related_name="object_relationships",
    )

    attributes = models.JSONField(
        default=dict,
        blank=True,
    )

    valid_from = models.DateTimeField(
        null=True,
        blank=True,
    )

    valid_to = models.DateTimeField(
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
            f"{self.subject.name} "
            f"{self.relationship_type.name} "
            f"{self.object.name}"
        )
