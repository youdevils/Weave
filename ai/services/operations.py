"""
The AI operation contract and registry.

Phase 1 builds this mechanism only -- no real `create`/`reconcile`/`change`/
`assess` operation is registered here. Future operations plug into the common
orchestration layer (ai.services.orchestrator.run_ai_operation) by providing
one of these, without implementing their own provider, context, Proposal or
validation machinery.
"""

from dataclasses import dataclass
from typing import FrozenSet, Literal, Type

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
