"""
The common orchestration entry point: run_ai_operation(...).

Every Assisted operation runs as a bounded, staged workflow
(ai.services.workflow.engine) built from its OperationDefinition. This module
only validates the request, opens the AIExecution record, runs the workflow,
and maps its terminal Finish -- or a provider/system failure -- onto the
OperationResult contract.

Canonical model state is always the source of truth for AI context: every
stage reloads it (ai.services.semantic.index), and nothing ever becomes
canonical except through a Proposal a human later accepts. If the canonical
model changes mid-run, later stages simply see the new state; correctness is
re-checked authoritatively at the final commit (ai.services.staging).

Intermediate AI state never becomes a visible, capacity-consuming Proposal:
staging always rolls back, and the final commit either keeps a complete,
valid WORKING Proposal or nothing.
"""

from __future__ import annotations

import logging

from django.conf import settings

from model.services.proposal.proposal import ProposalService

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.execution import AIExecutionService
from ai.services.intent import validate_intent
from ai.services.openai_provider import OpenAIProvider
from ai.services.operations import get_operation
from ai.services.provider import AIProvider, ProviderConfig, ProviderError
from ai.services.result_schema import ExecutionStatus, OperationOutcome, OperationResult
from ai.services.workflow.engine import Finish, WorkflowRun, run_workflow

logger = logging.getLogger(__name__)


def run_ai_operation(
    *,
    operation_id: str,
    model,
    user,
    intent_text: str,
    assets=(),
    provider: AIProvider | None = None,
    on_progress=None,
    should_commit=None,
) -> OperationResult:
    """
    `assets`: pre-extracted evidence, [{"name", "content", "mime_type"}].
    `on_progress(stage_id)`: called before every provider call (the caller's
    heartbeat). `should_commit()`: called inside the final commit transaction;
    returning False abandons the commit (see ai.services.staging.commit_proposal).
    """

    provider = provider or OpenAIProvider()
    operation = get_operation(operation_id)
    intent = validate_intent(intent_text)

    if operation.can_produce_proposal:
        # Fail-fast optimisation only; ProposalService.create_working inside
        # staging/commit re-checks capacity and remains the authoritative gate.
        ProposalService.assert_capacity(model, user)

    execution = AIExecutionService.create(operation=operation_id, model=model, user=user)
    run = WorkflowRun(
        operation=operation,
        model=model,
        user=user,
        intent=intent,
        bundle=EvidenceBundle.from_assets(assets),
        provider=provider,
        config=ProviderConfig(
            model=settings.AI_DEFAULT_OPENAI_MODEL,
            timeout_seconds=settings.AI_PROVIDER_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_PROVIDER_RETRIES,
        ),
        execution=execution,
        definition=operation.build_workflow(),
        on_progress=on_progress,
        should_commit=should_commit,
    )

    try:
        finish = run_workflow(run)
    except ProviderError as error:
        logger.exception("AI provider error during operation %s", operation_id)
        finish = Finish(OperationOutcome.FAILED, execution_status=ExecutionStatus.FAILED, error=str(error))
    except Exception:
        # Mirrors model.services.proposal.submission.process()'s own top-level
        # safety net: log server-side, never leak raw exception text into the
        # user-facing result, and always reach a terminal state.
        logger.exception("Unexpected error running AI operation %s", operation_id)
        finish = Finish(
            OperationOutcome.FAILED,
            execution_status=ExecutionStatus.FAILED,
            error="An unexpected error occurred while running this AI operation.",
        )

    proposal = finish.proposal
    AIExecutionService.finish(
        execution,
        execution_status=finish.execution_status,
        outcome=finish.outcome,
        proposal=proposal,
        error=finish.error,
        result_payload=run.state.last_output,
        provider_calls=run.provider_calls,
        stage_summary=run.stage_summary(),
    )
    return OperationResult(
        execution_status=finish.execution_status,
        outcome=finish.outcome,
        execution_id=execution.id,
        proposal_id=proposal.id if proposal is not None else None,
        explanation=finish.explanation,
        refinement_cycles=run.corrections,
        context_expansions=0,
        unresolved_issues=list(finish.unresolved_issues),
        findings=run.user_findings() if finish.execution_status == ExecutionStatus.COMPLETED else [],
        provider_calls=run.provider_calls,
        stage_summary=run.stage_summary(),
        completeness=(finish.completeness or "complete") if proposal is not None else "",
        blocked_targets=list(finish.blocked_targets or run.state.blocked_targets),
    )
