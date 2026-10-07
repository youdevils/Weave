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

from ai.models import AIExecution, AIExecutionStep


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
    def record_context_digest(execution: AIExecution, payload: dict) -> None:
        """Overwrites context_digest each call -- latest-wins, not a
        history. Persists only the digest, never the payload."""

        execution.context_digest = _digest(payload)
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
    def record_step(
        execution: AIExecution,
        *,
        call_index,
        stage,
        stage_attempt,
        decision,
        started_at,
        ended_at=None,
        issue_codes=None,
        verdict="",
        usage=None,
        input_payload=None,
        output_payload=None,
        sequence=0,
        provider_call=True,
    ) -> AIExecutionStep:
        """One workflow step's observability row (a provider call, or an
        OnyxJar-only deterministic step): digests and codes only. `ended_at`
        is the caller's own genuine end-of-call timestamp when it has one
        (a provider call's own end); otherwise this is recorded now."""

        return AIExecutionStep.objects.create(
            execution=execution,
            sequence=sequence,
            provider_call=provider_call,
            call_index=call_index,
            stage=stage,
            stage_attempt=stage_attempt,
            decision=decision,
            issue_codes=dict(issue_codes or {}),
            verdict=verdict or "",
            usage=dict(usage or {}),
            input_digest=_digest(input_payload) if input_payload is not None else "",
            output_digest=_digest(output_payload) if output_payload is not None else "",
            started_at=started_at,
            ended_at=ended_at if ended_at is not None else timezone.now(),
        )

    @staticmethod
    def finish(
        execution: AIExecution,
        *,
        execution_status,
        outcome,
        proposal=None,
        result_payload=None,
        error="",
        provider_calls=None,
        stage_summary=None,
    ) -> None:
        """
        result_digest semantics: populated when `result_payload` (the final
        last stage's structured output) is given, left blank otherwise --
        never fabricated. A FAILED run before any structured output was
        parsed leaves it blank.
        """

        execution.execution_status = execution_status
        execution.outcome = outcome
        execution.proposal = proposal
        execution.error = error
        execution.ended_at = timezone.now()

        if result_payload is not None:
            execution.result_digest = _digest(result_payload.model_dump(mode="json"))
        if provider_calls is not None:
            execution.provider_calls = provider_calls
        if stage_summary is not None:
            execution.stage_summary = dict(stage_summary)

        execution.save(
            update_fields=[
                "provider_calls",
                "stage_summary",
                "execution_status",
                "outcome",
                "proposal",
                "error",
                "ended_at",
                "result_digest",
            ]
        )
