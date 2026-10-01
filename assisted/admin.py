from django.contrib import admin

from assisted.models import AssistedTask, AssistedTaskEvidence


class AssistedTaskEvidenceInline(admin.TabularInline):
    model = AssistedTaskEvidence
    extra = 0
    fields = ("original_filename", "content_type", "size_bytes", "sha256", "created_at")
    readonly_fields = fields
    can_delete = False


@admin.register(AssistedTask)
class AssistedTaskAdmin(admin.ModelAdmin):
    list_display = (
        "operation",
        "workspace",
        "model",
        "creator",
        "status",
        "failure_reason_code",
        "created_at",
        "updated_at",
    )

    list_filter = ("operation", "status", "failure_reason_code")

    search_fields = ("workspace__name", "model__name", "creator__email")

    # Durable history record -- never created or edited by hand.
    readonly_fields = [f.name for f in AssistedTask._meta.fields]

    inlines = [AssistedTaskEvidenceInline]
