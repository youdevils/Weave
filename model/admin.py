from django.contrib import admin

from .models import Model


@admin.register(Model)
class ModelAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "created_at", "updated_at")
    search_fields = ("name", "description", "workspace__name")
