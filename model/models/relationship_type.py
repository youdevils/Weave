import uuid

from django.db import models


class RelationshipType(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="relationship_types",
    )

    name = models.CharField(
        max_length=100,
    )

    key = models.SlugField(
        max_length=100,
    )

    description = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["model", "key"],
                name="unique_relationship_type_key_per_model",
            ),
        ]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
