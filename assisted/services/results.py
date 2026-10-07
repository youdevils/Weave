"""
Copying an OperationResult's small, durable fields onto an AssistedTask --
shared by every terminal transition (READY_FOR_REVIEW, COMPLETED, FAILED),
so they can never drift apart. Runs before any bootstrap-Model deletion
(assisted.services.cleanup), since ai.AIExecution.model is CASCADE and would
otherwise take its usage data with it.
"""

from __future__ import annotations

from django.conf import settings

from ai.models import AIExecution


def apply_result(task, result) -> list[str]:
    """Sets the result-derived fields on `task` (unsaved) and returns their names."""

    usage = AIExecution.objects.filter(pk=result.execution_id).values_list("usage", flat=True).first()

    task.ai_outcome = result.outcome.value if result.outcome else ""
    task.refinement_cycles = result.refinement_cycles
    task.context_expansions = result.context_expansions
    task.tokens_used = (usage or {}).get("total_tokens", 0)
    task.provider_calls = getattr(result, "provider_calls", 0) or 0
    task.stage_summary = dict(getattr(result, "stage_summary", {}) or {})
    task.findings = [
        {"severity": finding.severity, "message": finding.message[:1000]}
        for finding in (getattr(result, "findings", None) or [])[: settings.AI_MAX_TASK_FINDINGS]
    ]
    task.current_stage = ""
    task.completeness = getattr(result, "completeness", "") or ""

    return [
        "ai_outcome",
        "refinement_cycles",
        "context_expansions",
        "tokens_used",
        "provider_calls",
        "stage_summary",
        "findings",
        "current_stage",
        "completeness",
    ]
