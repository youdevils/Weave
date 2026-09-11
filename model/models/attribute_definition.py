import uuid

from django.core.exceptions import ValidationError
from django.db import models


class AttributeDefinition(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        DATE = "date", "Date"
        DATETIME = "datetime", "Date & time"
        CHOICE = "choice", "Choice"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    is_active = models.BooleanField(
        default=True,
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

    nullable = models.BooleanField(
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

        # An attribute definition must belong to exactly one type.
        if bool(self.object_type) == bool(self.relationship_type):
            raise ValidationError(
                "An attribute definition must belong to exactly one "
                "object type or relationship type."
            )

        # Configuration must be valid for the selected data type.
        config = self.config or {}

        if self.data_type == self.DataType.TEXT:
            self._validate_text_config(config)

        elif self.data_type == self.DataType.NUMBER:
            self._validate_number_config(config)

        elif self.data_type == self.DataType.CHOICE:
            self._validate_choice_config(config)

        elif self.data_type in {
            self.DataType.BOOLEAN,
            self.DataType.DATE,
            self.DataType.DATETIME,
        }:
            if config:
                raise ValidationError(
                    f"{self.get_data_type_display()} does not currently "
                    "support configuration."
                )

        # Validate the default value against the definition itself.
        if self.default_value is not None:
            if not self._is_nullable_default():
                self._validate_default_value()

        elif self.required and not self.nullable:
            # No default is not necessarily an error. Required simply means
            # an instance must eventually provide a value.
            pass

    def _validate_text_config(self, config: dict) -> None:
        allowed_keys = {"min_length", "max_length"}

        unknown_keys = set(config) - allowed_keys
        if unknown_keys:
            raise ValidationError(
                f"Unsupported text configuration: "
                f"{', '.join(sorted(unknown_keys))}."
            )

        min_length = config.get("min_length")
        max_length = config.get("max_length")

        if min_length is not None:
            if not isinstance(min_length, int) or isinstance(min_length, bool):
                raise ValidationError("Text min_length must be an integer.")

            if min_length < 0:
                raise ValidationError("Text min_length cannot be negative.")

        if max_length is not None:
            if not isinstance(max_length, int) or isinstance(max_length, bool):
                raise ValidationError("Text max_length must be an integer.")

            if max_length < 0:
                raise ValidationError("Text max_length cannot be negative.")

        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise ValidationError("Text min_length cannot be greater than max_length.")

    def _validate_number_config(self, config: dict) -> None:
        allowed_keys = {"min", "max"}

        unknown_keys = set(config) - allowed_keys
        if unknown_keys:
            raise ValidationError(
                f"Unsupported number configuration: "
                f"{', '.join(sorted(unknown_keys))}."
            )

        minimum = config.get("min")
        maximum = config.get("max")

        if minimum is not None:
            if not self._is_json_number(minimum):
                raise ValidationError("Number min must be a number.")

        if maximum is not None:
            if not self._is_json_number(maximum):
                raise ValidationError("Number max must be a number.")

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValidationError("Number min cannot be greater than max.")

    def _validate_choice_config(self, config: dict) -> None:
        allowed_keys = {"choices"}

        unknown_keys = set(config) - allowed_keys
        if unknown_keys:
            raise ValidationError(
                f"Unsupported choice configuration: "
                f"{', '.join(sorted(unknown_keys))}."
            )

        choices = config.get("choices")

        if not isinstance(choices, list):
            raise ValidationError("Choice configuration must contain a 'choices' list.")

        if not choices:
            raise ValidationError(
                "Choice configuration must contain at least one choice."
            )

        if not all(isinstance(choice, str) for choice in choices):
            raise ValidationError("All choices must be strings.")

        if len(choices) != len(set(choices)):
            raise ValidationError("Choice values must be unique.")

    def _validate_default_value(self) -> None:
        from model.services.validation.attributes import validate_attribute_value

        issue = validate_attribute_value(
            definition=self,
            value=self.default_value,
            field=self.key,
        )

        if issue is not None:
            raise ValidationError(issue.message)

    def _is_nullable_default(self) -> bool:
        return self.default_value is None and self.nullable

    @staticmethod
    def _is_json_number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def __str__(self):
        return self.name
