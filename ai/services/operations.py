"""
The AI operation contract and registry.

An operation plugs into the common orchestration layer
(ai.services.orchestrator.run_ai_operation) by providing an
OperationDefinition: a ChangeSet policy (what its ChangeSets may contain --
ai.services.resolution.OperationPolicy) and a factory for its staged
WorkflowDefinition (ai.services.workflow.engine). It never implements its own
provider, context, resolution, Proposal or validation machinery. Real
operations are registered in ai.services.operation_definitions, wired up from
AiConfig.ready().
"""

from dataclasses import dataclass
from typing import Callable, Literal


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
    # ai.services.resolution.OperationPolicy
    policy: object
    # () -> ai.services.workflow.engine.WorkflowDefinition. A factory, not an
    # instance: budgets are read from settings at run time.
    build_workflow: Callable[[], object]


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
