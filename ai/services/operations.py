"""
The AI operation contract and registry.

This module builds the mechanism only. `create` is the first real operation
registered against it (see ai.services.operation_definitions, wired up from
AiConfig.ready()); `reconcile`/`change`/`assess` remain unregistered.
Operations plug into the common orchestration layer
(ai.services.orchestrator.run_ai_operation) by providing one of these,
without implementing their own provider, context, Proposal or validation
machinery.
"""

from dataclasses import dataclass
from typing import Callable, FrozenSet, Literal, Optional, Type

from pydantic import BaseModel


class UnknownOperation(KeyError):
    """No OperationDefinition is registered under this id."""


class DuplicateOperation(ValueError):
    """An OperationDefinition is already registered under this id."""


@dataclass(frozen=True)
class OperationDefinition:
    operation_id: str
    name: str
    description: str
    evidence: Literal["required", "optional", "none"]
    can_produce_proposal: bool
    required_context_categories: FrozenSet[str]
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    # Optional, operation-specific extension points consumed generically by
    # ai.services.orchestrator.run_ai_operation -- never branched on
    # operation_id there. All three default to a no-op for an operation that
    # doesn't set them (Create today; Change/Assess can opt in later).
    #
    # plan_sufficiency_check: run against the AI's structured ChangePlan
    # after it already passed validate_change_plan's deterministic reference
    # checks; any issues it returns feed back into refinement exactly like
    # every other issue source in the loop.
    plan_sufficiency_check: Optional[Callable[[object], list]] = None
    # prompt_fragment: appended to the shared system prompt
    # (ai.services.orchestrator._system_prompt) after its universal text.
    prompt_fragment: str = ""
    # max_refinement_cycles: this operation's own bounded refinement budget.
    # None means "use the global settings.AI_MAX_REFINEMENT_CYCLES default."
    max_refinement_cycles: Optional[int] = None


_REGISTRY: dict[str, OperationDefinition] = {}


def register_operation(definition: OperationDefinition) -> None:
    if definition.operation_id in _REGISTRY:
        raise DuplicateOperation(
            f"An operation is already registered as '{definition.operation_id}'."
        )
    _REGISTRY[definition.operation_id] = definition


def get_operation(operation_id: str) -> OperationDefinition:
    try:
        return _REGISTRY[operation_id]
    except KeyError:
        raise UnknownOperation(f"No AI operation registered as '{operation_id}'.") from None


def list_operations() -> list[OperationDefinition]:
    return list(_REGISTRY.values())


def _unregister_operation(operation_id: str) -> None:
    """Test-only: undo a register_operation call. Not part of the public contract."""
    _REGISTRY.pop(operation_id, None)
