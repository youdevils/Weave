from django.contrib import admin

from .models import ImportSource


@admin.register(ImportSource)
class ImportSourceAdmin(admin.ModelAdmin):
    """Read-only. The file's bytes are deliberately never loaded or shown."""

    list_display = (
        "original_filename",
        "model",
        "file_format",
        "size_bytes",
        "uploaded_by",
        "imported_at",
        "created_at",
    )
    list_select_related = ("model", "uploaded_by")
    exclude = ("content",)

    def get_queryset(self, request):
        return super().get_queryset(request).defer("content")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
