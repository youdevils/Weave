from django.contrib import admin

from .models import Workspace, WorkspaceMember


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "description")


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("workspace__name", "user__email")
    autocomplete_fields = ("workspace", "user")
