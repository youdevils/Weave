from django.contrib import admin

from ai.models import AIExecution


@admin.register(AIExecution)
class AIExecutionAdmin(admin.ModelAdmin):
    list_display = (
        "operation",
        "model",
        "user",
        "execution_status",
        "outcome",
        "proposal",
        "started_at",
        "ended_at",
    )

    list_filter = ("execution_status", "outcome", "operation", "provider")

    search_fields = (
        "operation",
        "model__name",
        "user__email",
    )

    # Observability-only record -- never created or edited by hand.
    readonly_fields = (
        "id",
        "operation",
        "model",
        "user",
        "proposal",
        "execution_status",
        "outcome",
        "provider",
        "provider_model",
        "refinement_cycles",
        "context_expansions",
        "usage",
        "context_digest",
        "result_digest",
        "error",
        "started_at",
        "ended_at",
    )
