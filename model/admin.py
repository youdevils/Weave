from django.contrib import admin

from .models import model
from .models import object_type
from .models import attribute_definition
from .models import relationship_type
from .models import relationship_type_rule
from .models import object
from .models import relationship


@admin.register(model.Model)
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


@admin.register(object_type.ObjectType)
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


@admin.register(attribute_definition.AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "key",
        "data_type",
        "required",
        "object_type",
        "relationship_type",
    )

    list_filter = (
        "data_type",
        "required",
    )

    search_fields = (
        "name",
        "key",
        "description",
    )


@admin.register(relationship_type.RelationshipType)
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


@admin.register(relationship_type_rule.RelationshipTypeRule)
class RelationshipTypeRuleAdmin(admin.ModelAdmin):
    list_display = (
        "relationship_type",
        "subject_type",
        "object_type",
        "subject_min",
        "subject_max",
        "object_min",
        "object_max",
    )

    search_fields = (
        "relationship_type__name",
        "subject_type__name",
        "object_type__name",
    )


@admin.register(object.Object)
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


@admin.register(relationship.Relationship)
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
