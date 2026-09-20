from django.contrib import admin

from .models import Publication


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """
    Read-only: publications are immutable snapshots and are never created or
    edited by hand. Deletion is left to Django's default so that deleting a
    Model in the admin can still cascade to its publications.
    """

    list_display = ("title", "model", "sequence", "source_revision", "published_by", "published_at")
    list_filter = ("published_at",)
    search_fields = ("title", "model__name", "content_digest")
    ordering = ("-published_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
