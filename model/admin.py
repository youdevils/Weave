from django.contrib import admin

from .models import (
    AttributeDefinition,
    EvidenceReference,
    Model,
    Object,
    ObjectType,
    Proposal,
    ProposalChange,
    ProposalSubmissionResult,
    ProposalValidationError,
    Relationship,
    RelationshipType,
    RelationshipTypeRule,
)


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "workspace",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "description",
        "workspace__name",
    )

    autocomplete_fields = ("workspace",)


@admin.register(ObjectType)
class ObjectTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "model",
        "key",
        "is_active",
        "sort_order",
    )

    list_filter = ("is_active",)

    search_fields = (
        "name",
        "key",
        "description",
    )

    autocomplete_fields = ("model",)


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "key",
        "data_type",
        "required",
        "nullable",
        "object_type",
        "relationship_type",
    )

    list_filter = (
        "data_type",
        "required",
        "nullable",
    )

    search_fields = (
        "name",
        "key",
        "description",
    )

    autocomplete_fields = ("object_type", "relationship_type")


@admin.register(RelationshipType)
class RelationshipTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "model",
        "key",
        "is_active",
        "sort_order",
    )

    list_filter = ("is_active",)

    search_fields = (
        "name",
        "key",
        "description",
    )

    autocomplete_fields = ("model",)


@admin.register(RelationshipTypeRule)
class RelationshipTypeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "relationship_type",
        "subject_type",
        "object_type",
        "subject_minimum",
        "subject_maximum",
        "object_minimum",
        "object_maximum",
    )

    search_fields = (
        "relationship_type__name",
        "subject_type__name",
        "object_type__name",
    )

    autocomplete_fields = ("relationship_type", "subject_type", "object_type")


@admin.register(Object)
class ObjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "model",
        "object_type",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "description",
    )

    list_filter = ("object_type",)

    autocomplete_fields = ("model", "object_type")


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "relationship_type",
        "object",
        "model",
        "valid_from",
        "valid_to",
    )

    search_fields = (
        "subject__name",
        "object__name",
        "relationship_type__name",
    )

    list_filter = ("relationship_type",)

    autocomplete_fields = ("model", "relationship_type", "subject", "object")


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "model",
        "created_by",
        "status",
        "base_revision",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "title",
        "summary",
        "model__name",
        "created_by__email",
    )

    autocomplete_fields = ("model", "created_by")

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "submitted_at",
        "completed_at",
    )


class EvidenceReferenceInline(admin.TabularInline):
    model = EvidenceReference
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ProposalChange)
class ProposalChangeAdmin(admin.ModelAdmin):
    inlines = (EvidenceReferenceInline,)

    list_display = (
        "proposal",
        "operation",
        "target_type",
        "target_id",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "operation",
        "target_type",
        "created_at",
    )

    search_fields = (
        "proposal__title",
        "target_type",
        "target_id",
    )

    autocomplete_fields = ("proposal",)

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )


@admin.register(EvidenceReference)
class EvidenceReferenceAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "locator",
        "change",
        "created_at",
    )

    search_fields = (
        "source",
        "locator",
        "note",
    )

    autocomplete_fields = ("change",)

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )


@admin.register(ProposalSubmissionResult)
class ProposalSubmissionResultAdmin(admin.ModelAdmin):
    list_display = (
        "proposal",
        "outcome",
        "before_revision",
        "after_revision",
        "created_at",
    )

    list_filter = ("outcome",)

    search_fields = (
        "proposal__title",
        "message",
    )

    autocomplete_fields = ("proposal",)

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )


@admin.register(ProposalValidationError)
class ProposalValidationErrorAdmin(admin.ModelAdmin):
    list_display = (
        "result",
        "code",
        "severity",
        "target_type",
        "target_id",
        "change",
    )

    list_filter = (
        "severity",
        "target_type",
    )

    search_fields = (
        "code",
        "message",
    )

    autocomplete_fields = ("result", "change")

    readonly_fields = (
        "id",
        "created_at",
    )
