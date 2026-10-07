from django.contrib import admin

from ai.models import AIExecution, AIExecutionStep


class AIExecutionStepInline(admin.TabularInline):
    model = AIExecutionStep
    extra = 0
    can_delete = False
    ordering = ("sequence", "call_index")
    fields = (
        "sequence",
        "call_index",
        "provider_call",
        "stage",
        "stage_attempt",
        "decision",
        "verdict",
        "issue_codes",
        "usage",
        "started_at",
        "ended_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AIExecution)
class AIExecutionAdmin(admin.ModelAdmin):
    inlines = [AIExecutionStepInline]
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
        "provider_calls",
        "stage_summary",
        "refinement_cycles",
        "context_expansions",
        "usage",
        "context_digest",
        "result_digest",
        "error",
        "started_at",
        "ended_at",
    )
