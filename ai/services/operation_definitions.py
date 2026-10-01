"""
Registers the real AI operations with ai.services.operations' registry.
Phase 1 built the registry mechanism only (see that module's docstring) --
this is the first operation plugged into it.
"""

from ai.services.change_plan import ChangePlan
from ai.services.operations import DuplicateOperation, OperationDefinition, register_operation

CREATE = OperationDefinition(
    operation_id="create",
    name="Assisted Create",
    description=(
        "Creates an initial model structure (object types, relationship "
        "types, rules, and optionally example objects/relationships) from "
        "a natural-language intent and user-supplied evidence."
    ),
    evidence="optional",
    can_produce_proposal=True,
    required_context_categories=frozenset(),
    # Neither field is read anywhere in orchestrator.py/proposal_compiler.py
    # today -- ChangePlan is the de facto placeholder ai.tests.support's
    # fake_operation already uses for both.
    input_schema=ChangePlan,
    output_schema=ChangePlan,
)


def register_all() -> None:
    try:
        register_operation(CREATE)
    except DuplicateOperation:
        pass  # already registered in this process (e.g. autoreload)
