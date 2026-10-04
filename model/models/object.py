import uuid

from django.db import models


class Object(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="model_objects",
    )

    object_type = models.ForeignKey(
        "model.ObjectType",
        on_delete=models.PROTECT,
        related_name="typed_objects",
    )

    is_active = models.BooleanField(
        default=True,
    )

    name = models.CharField(
        max_length=255,
    )

    # Application-assigned, immutable identity (model.services.keys) --
    # the user-facing counterpart to `id`. Scoped per (model, object_type),
    # not globally: see uniq_object_model_type_key.
    key = models.SlugField(
        max_length=100,
    )

    description = models.TextField(
        blank=True,
    )

    attributes = models.JSONField(
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
        constraints = [
            models.UniqueConstraint(
                fields=["model", "object_type", "key"],
                name="uniq_object_model_type_key",
            ),
        ]

    def save(self, *args, **kwargs):
        # The real application flow (model.views.data_object_editor,
        # model.services.proposal.submission, ingestion, model_template)
        # always assigns `key` via model.services.keys before this ever
        # runs, so this fallback is never exercised there -- it only
        # covers direct ORM writes (scripts, test fixtures) that bypass
        # that flow entirely. Still the one source of truth: calls the
        # same service, just lazily, to avoid model -> service -> model
        # import cycle (model.services.keys imports this module).
        if not self.key:
            from model.services import keys

            self.key = keys.generate_key(
                "Object", self.name, model=self.model_id, parent_id=self.object_type_id,
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
