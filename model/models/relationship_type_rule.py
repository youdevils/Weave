import uuid

from django.core.exceptions import ValidationError
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

    # ---------------------------------------------------------
    # Subject cardinality
    # ---------------------------------------------------------

    subject_minimum = models.PositiveIntegerField(
        default=0,
    )

    subject_maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    subject_required = models.BooleanField(
        default=False,
    )

    # ---------------------------------------------------------
    # Object cardinality
    # ---------------------------------------------------------

    object_minimum = models.PositiveIntegerField(
        default=0,
    )

    object_maximum = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    object_required = models.BooleanField(
        default=False,
    )

    # ---------------------------------------------------------
    # Timestamps
    # ---------------------------------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "relationship_type",
                    "subject_type",
                    "object_type",
                ],
                name="unique_relationship_type_rule",
            ),
        ]

    def clean(self):
        super().clean()

        # -----------------------------------------------------
        # Subject cardinality
        # -----------------------------------------------------

        if (
            self.subject_maximum is not None
            and self.subject_minimum > self.subject_maximum
        ):
            raise ValidationError(
                "Subject minimum cannot be greater than subject maximum."
            )

        # -----------------------------------------------------
        # Object cardinality
        # -----------------------------------------------------

        if (
            self.object_maximum is not None
            and self.object_minimum > self.object_maximum
        ):
            raise ValidationError(
                "Object minimum cannot be greater than object maximum."
            )

    def __str__(self):
        return (
            f"{self.relationship_type.name}: "
            f"{self.subject_type.name} → {self.object_type.name}"
        )
