"""
AIExecution record keeping: internal execution metadata for development,
observability and troubleshooting. Not the source of truth for model
lineage -- Proposal/ProposalChange remains that. Deliberately never
persists raw prompts, full context packets, or raw provider responses --
only digests.
"""

from __future__ import annotations

import hashlib

from django.utils import timezone

from publication.services.bundle import canonical_json

from ai.models import AIExecution


def _digest(payload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class AIExecutionService:

    @staticmethod
    def create(*, operation, model, user) -> AIExecution:
        return AIExecution.objects.create(
            operation=operation,
            model=model,
            user=user,
            execution_status=AIExecution.ExecutionStatus.RUNNING,
        )

    @staticmethod
    def record_context_digest(execution: AIExecution, context) -> None:
        """Overwrites context_digest each cycle -- latest-wins, not a
        history. Persists only the digest, never the packet."""

        execution.context_digest = _digest(context.model_dump(mode="json"))
        execution.save(update_fields=["context_digest"])

    @staticmethod
    def accumulate_usage(execution: AIExecution, provider_result) -> None:
        usage = dict(execution.usage or {})
        for key, value in (provider_result.usage or {}).items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
            else:
                usage[key] = value
        execution.usage = usage

        if provider_result.provider:
            execution.provider = provider_result.provider
        if provider_result.provider_model and not execution.provider_model:
            execution.provider_model = provider_result.provider_model

        execution.save(update_fields=["usage", "provider", "provider_model"])

    @staticmethod
    def increment_refinement_cycle(execution: AIExecution) -> None:
        execution.refinement_cycles += 1
        execution.save(update_fields=["refinement_cycles"])

    @staticmethod
    def increment_context_expansion(execution: AIExecution) -> None:
        execution.context_expansions += 1
        execution.save(update_fields=["context_expansions"])

    @staticmethod
    def finish(
        execution: AIExecution,
        *,
        execution_status,
        outcome,
        proposal=None,
        result_payload=None,
        error="",
    ) -> None:
        """
        result_digest semantics: populated when `result_payload` (the final
        AIStructuredResult) is given, left blank otherwise -- never
        fabricated. This covers every terminal path uniformly: READY_FOR_REVIEW,
        NO_CHANGE_REQUIRED, NEEDS_USER_CLARIFICATION and UNRESOLVED always have
        a structured result by the time they're reached; FAILED populates it
        too if the failure happened after one was already parsed, and leaves
        it blank for a provider/system failure before any structured result
        ever existed.
        """

        execution.execution_status = execution_status
        execution.outcome = outcome
        execution.proposal = proposal
        execution.error = error
        execution.ended_at = timezone.now()

        if result_payload is not None:
            execution.result_digest = _digest(result_payload.model_dump(mode="json"))

        execution.save(
            update_fields=[
                "execution_status",
                "outcome",
                "proposal",
                "error",
                "ended_at",
                "result_digest",
            ]
        )
