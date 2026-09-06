import uuid

from django.core.exceptions import ValidationError
from django.db import models


class AttributeDefinition(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    object_type = models.ForeignKey(
        "model.ObjectType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attribute_definitions",
    )

    relationship_type = models.ForeignKey(
        "model.RelationshipType",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="relationship_definitions",
    )

    name = models.CharField(
        max_length=100,
    )

    key = models.SlugField(
        max_length=100,
    )

    data_type = models.CharField(
        max_length=20,
        choices=DataType.choices,
        default=DataType.TEXT,
    )

    description = models.TextField(
        blank=True,
    )

    required = models.BooleanField(
        default=False,
    )

    default_value = models.JSONField(
        null=True,
        blank=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    config = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["sort_order", "name"]

    def clean(self):
        super().clean()

        if bool(self.object_type) == bool(self.relationship_type):
            raise ValidationError(
                "An attribute definition must belong to exactly one "
                "object type or relationship type."
            )

    def __str__(self):
        return self.name
