"""
The common orchestration entry point: run_ai_operation(...).

Canonical model state is always the source of truth for AI context (see
ai.services.context_builder) -- there is no AI-private snapshot, and no
revision-pinning/auto-restart behaviour. If the canonical model changes
while an operation is running, the orchestrator does not notice or care:
the next refinement cycle's context simply reflects the new current state,
because it was always going to be rebuilt from canonical state anyway. The
one moment correctness is actually checked is exactly the moment it is
checked for a human-authored Proposal: inside compile_and_validate's call to
apply_and_validate, against whatever canonical state exists at that instant.

Intermediate AI iteration state never becomes a visible, capacity-consuming
Proposal -- every refinement attempt is a single self-contained
compile_and_validate() call that either commits a complete, valid Proposal
or leaves no trace at all (ai.services.proposal_compiler). There is
therefore no cleanup step anywhere in this loop.
"""

from __future__ import annotations

import logging

from django.conf import settings

from model.services.model_graph.loader import load_effective_dataset
from model.services.proposal.proposal import ProposalService

from ai.services.change_plan import UnresolvedIssue, validate_change_plan
from ai.services.context_builder import build_context_packet
from ai.services.context_expansion import expand, initial_expansion_state, resolve_context_requests
from ai.services.execution import AIExecutionService
from ai.services.intent import validate_intent
from ai.services.openai_provider import OpenAIProvider
from ai.services.operations import get_operation
from ai.services.proposal_compiler import compile_and_validate
from ai.services.provider import AIProvider, ProviderConfig, ProviderError, ProviderSchemaError
from ai.services.result_schema import (
    AIStructuredResult,
    ExecutionStatus,
    OperationOutcome,
    OperationResult,
)

logger = logging.getLogger(__name__)


def run_ai_operation(
    *,
    operation_id: str,
    model,
    user,
    intent_text: str,
    assets=(),
    provider: AIProvider | None = None,
) -> OperationResult:
    provider = provider or OpenAIProvider()
    operation = get_operation(operation_id)
    intent = validate_intent(intent_text)
    max_refinement_cycles = (
        operation.max_refinement_cycles
        if operation.max_refinement_cycles is not None
        else settings.AI_MAX_REFINEMENT_CYCLES
    )

    if operation.can_produce_proposal:
        # Fail-fast optimisation only; ProposalService.create_working inside
        # compile_and_validate re-checks capacity at the actual moment of
        # creation and remains the authoritative gate.
        ProposalService.assert_capacity(model, user)

    execution = AIExecutionService.create(operation=operation_id, model=model, user=user)
    provider_config = ProviderConfig(
        model=settings.AI_DEFAULT_OPENAI_MODEL,
        timeout_seconds=settings.AI_PROVIDER_TIMEOUT_SECONDS,
        max_retries=settings.AI_MAX_PROVIDER_RETRIES,
    )

    refinement_cycle = 0
    expansion_cycle = 0
    expansion_state = initial_expansion_state()
    previous_issues: list = []
    # The last successfully parsed structured result -- drives result_digest
    # and the findings passthrough. Overwritten (never accumulated) each
    # cycle, so it always reflects exactly the result that led to whatever
    # terminal state is ultimately reached.
    structured: AIStructuredResult | None = None

    def _finish(execution_status, outcome, *, proposal=None, explanation="", error="", unresolved_issues=None):
        AIExecutionService.finish(
            execution,
            execution_status=execution_status,
            outcome=outcome,
            proposal=proposal,
            error=error,
            result_payload=structured,
        )
        return OperationResult(
            execution_status=execution_status,
            outcome=outcome,
            execution_id=execution.id,
            proposal_id=proposal.id if proposal else None,
            explanation=explanation,
            refinement_cycles=refinement_cycle,
            context_expansions=expansion_cycle,
            unresolved_issues=list(unresolved_issues or []),
            findings=list(structured.findings) if structured else [],
        )

    try:
        context = None
        while True:
            context = build_context_packet(
                model=model,
                intent=intent,
                assets=assets,
                previous_issues=previous_issues,
                expansion_state=expansion_state,
            )
            AIExecutionService.record_context_digest(execution, context)

            provider_result = provider.generate_structured(
                system_prompt=_system_prompt(operation, context),
                user_payload=context.model_dump(mode="json"),
                response_schema=AIStructuredResult,
                config=provider_config,
            )
            AIExecutionService.accumulate_usage(execution, provider_result)

            if provider_result.parsed is None:
                raise ProviderSchemaError("Provider returned no structured result.")

            structured = provider_result.parsed

            if structured.needs_clarification:
                return _finish(
                    ExecutionStatus.COMPLETED,
                    OperationOutcome.NEEDS_USER_CLARIFICATION,
                    explanation=structured.clarification_question or "",
                )

            if structured.context_requests:
                dataset = load_effective_dataset(model, proposal=None)
                resolution = resolve_context_requests(structured.context_requests, dataset=dataset)

                if resolution.seeds and expansion_cycle < settings.AI_MAX_CONTEXT_EXPANSIONS:
                    expansion_state = expand(expansion_state, resolution.seeds)
                    expansion_cycle += 1
                    AIExecutionService.increment_context_expansion(execution)
                    previous_issues = resolution.unresolved
                    continue

                previous_issues = resolution.unresolved or [
                    UnresolvedIssue(
                        code="context_expansion_exhausted",
                        message="The AI requested context that could not be resolved or expanded further.",
                    )
                ]
                refinement_cycle += 1
                AIExecutionService.increment_refinement_cycle(execution)
                if refinement_cycle >= max_refinement_cycles:
                    break
                continue

            if structured.change_plan is None or not structured.change_plan.actions:
                if structured.unresolved_issues:
                    # An explicitly empty plan accompanied by flagged issues
                    # is NOT a clean no-op -- ordinary bounded refinement
                    # feedback, never NO_CHANGE_REQUIRED.
                    previous_issues = structured.unresolved_issues
                    refinement_cycle += 1
                    AIExecutionService.increment_refinement_cycle(execution)
                    if refinement_cycle >= max_refinement_cycles:
                        break
                    continue

                return _finish(
                    ExecutionStatus.COMPLETED,
                    OperationOutcome.NO_CHANGE_REQUIRED,
                    explanation=structured.interpretation.restated_intent,
                )

            dataset = load_effective_dataset(model, proposal=None)
            plan_issues = validate_change_plan(structured.change_plan, dataset=dataset)
            if plan_issues:
                previous_issues = plan_issues
                refinement_cycle += 1
                AIExecutionService.increment_refinement_cycle(execution)
                if refinement_cycle >= max_refinement_cycles:
                    break
                continue

            if operation.plan_sufficiency_check is not None:
                sufficiency_issues = operation.plan_sufficiency_check(structured.change_plan)
                if sufficiency_issues:
                    previous_issues = sufficiency_issues
                    refinement_cycle += 1
                    AIExecutionService.increment_refinement_cycle(execution)
                    if refinement_cycle >= max_refinement_cycles:
                        break
                    continue

            if not operation.can_produce_proposal:
                previous_issues = [
                    UnresolvedIssue(
                        code="operation_cannot_produce_proposal",
                        message=f"Operation '{operation.operation_id}' cannot produce a Proposal.",
                    )
                ]
                break

            result = compile_and_validate(
                model=model, user=user, operation=operation, change_plan=structured.change_plan
            )
            if not result.issues:
                # structured.unresolved_issues, if any, are informational
                # here -- the plan validated/compiled cleanly regardless;
                # surfaced, not discarded.
                return _finish(
                    ExecutionStatus.COMPLETED,
                    OperationOutcome.READY_FOR_REVIEW,
                    proposal=result.proposal,
                    explanation=structured.interpretation.restated_intent,
                    unresolved_issues=structured.unresolved_issues,
                )

            previous_issues = result.issues
            refinement_cycle += 1
            AIExecutionService.increment_refinement_cycle(execution)
            if refinement_cycle >= max_refinement_cycles:
                break

        explanation = ""
        if settings.AI_FINAL_EXPLANATION_ENABLED:
            try:
                explanation = provider.explain(context=context, issues=previous_issues, config=provider_config)
            except ProviderError:
                explanation = ""  # best-effort only; never escalate UNRESOLVED into FAILED

        return _finish(
            ExecutionStatus.COMPLETED,
            OperationOutcome.UNRESOLVED,
            explanation=explanation,
            unresolved_issues=previous_issues,
        )

    except ProviderError as error:
        logger.exception("AI provider error during operation %s", operation_id)
        return _finish(ExecutionStatus.FAILED, OperationOutcome.FAILED, explanation="", error=str(error))

    except Exception:
        # Mirrors model.services.proposal.submission.process()'s own
        # top-level safety net: log the full traceback server-side, never
        # leak raw exception text into the user-facing result, and always
        # reach a terminal state -- an AIExecution must never be left
        # permanently RUNNING.
        logger.exception("Unexpected error running AI operation %s", operation_id)
        return _finish(
            ExecutionStatus.FAILED,
            OperationOutcome.FAILED,
            explanation="",
            error="An unexpected error occurred while running this AI operation.",
        )


def _system_prompt(operation, context) -> str:
    prompt = (
        f"You are assisting with the OnyxJar AI operation '{operation.operation_id}' "
        f"({operation.description}). Respond only with the requested structured "
        "schema. Only reference entities that appear in the supplied context, or "
        "name them via context_requests; never invent one. "
        "Every entity reference (a ChangeAction's target_ref/parent_ref, or a "
        "field like subject_type_ref/object_type_ref/subject_ref/object_ref) is "
        "an EntityRef, never a bare string or number: use "
        "{\"kind\": \"new\", \"id\": \"<a token you choose>\"} for an entity you are "
        "creating in this same Change Plan -- OnyxJar, not you, mints its real "
        "database id. A \"new\" token may be referenced by any later action in the "
        "same plan (e.g. an Object's parent_ref, or a RelationshipTypeRule's "
        "subject_type_ref/object_type_ref) to build on an entity you just created. "
        "For an entity that already exists, use {\"kind\": \"existing\", \"id\": "
        "\"<exact key or ref from context>\"}. `id` here is never a database id -- "
        "it is the exact `key` (for an ObjectType/RelationshipType, e.g. \"venue\") "
        "or the exact `ref`/`definitionRef` composite string OnyxJar shows you in "
        "context for that entity (for example \"venue:eden_park\" for an Object, or "
        "\"has_stage:tournament:stage\" for a RelationshipTypeRule). Copy it "
        "verbatim, character for character -- never invent one, never shorten or "
        "reformat it, and never assemble one yourself by concatenating pieces you "
        "saw separately (e.g. a type's key plus an instance's key) -- always use "
        "the single precomposed string OnyxJar already gave you. The one "
        "exception: an existing Relationship is referenced by the real id OnyxJar "
        "shows for it, because a Relationship has no key of its own. "
        "When creating a new ObjectType, RelationshipType, AttributeDefinition or "
        "Object, never supply its `key` -- OnyxJar always assigns one from the name "
        "itself, and any key you do supply is ignored. A RelationshipType itself has no subject/object fields: to "
        "constrain which ObjectTypes it may link, and with what cardinality, "
        "create a separate RelationshipTypeRule action parented to it, with "
        "`subject_type_ref`, `object_type_ref`, `subject_minimum`, "
        "`subject_maximum`, `object_minimum`, `object_maximum`. "
        "An ObjectType's or RelationshipType's own key identifies the type/schema "
        "itself, never a specific instance of it: never use a type's key as an "
        "existing-kind EntityRef for an Object or Relationship, and never put it in "
        "a context_request as if it were an instance you need more context about -- "
        "a context_request must name an actual Object or Relationship instance "
        "already present in context. A Relationship action's parent_ref is always "
        "its RelationshipType's own key (for example \"has_stage\"), never a "
        "RelationshipTypeRule's composite ref (for example "
        "\"has_stage:tournament:stage\") even though both appear together in "
        "context and the rule's ref is built from that same RelationshipType key: "
        "the RelationshipTypeRule only constrains which ObjectTypes the "
        "relationship may connect and with what cardinality -- useful for choosing "
        "and validating the subject/object endpoints -- but it is never itself the "
        "parent of a Relationship. If previous-attempt feedback reports a "
        "reference as not existing (an \"unresolvable_existing_reference\" or "
        "\"unresolvable_context_reference\" issue), treat that as proof the "
        "reference itself was wrong -- most likely a type key used where an "
        "instance's ref was needed, or a RelationshipTypeRule composite used where "
        "a RelationshipType key was needed -- and correct it; never treat it as "
        "evidence the entity exists somewhere just out of reach."
    )
    if context.model_is_empty:
        prompt += (
            " This model currently has no ObjectTypes, RelationshipTypes, Rules, "
            "Objects, or Relationships at all -- you are defining its initial "
            "ontology from scratch, entirely via \"new\" EntityRef tokens."
        )
    if operation.prompt_fragment:
        prompt += " " + operation.prompt_fragment
    return prompt
