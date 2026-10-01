"""
Structured AI output and the final operation result contract.

Execution lifecycle (ExecutionStatus: did the AI run itself finish, fail, or
is it still running) is kept strictly separate from operation outcome
(OperationOutcome: what the run produced) -- a run can COMPLETE with outcome
UNRESOLVED (every bounded refinement attempt exhausted without a valid
result), which is different from the run itself FAILING (a provider/system
error). See ai.services.orchestrator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from ai.services.change_plan import ChangePlan, EntityRef, UnresolvedIssue

__all__ = [
    "ExecutionStatus",
    "OperationOutcome",
    "Interpretation",
    "Finding",
    "ContextRequest",
    "UnresolvedIssue",
    "AIStructuredResult",
    "OperationResult",
]


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class OperationOutcome(str, Enum):
    READY_FOR_REVIEW = "ready_for_review"
    NO_CHANGE_REQUIRED = "no_change_required"
    NEEDS_USER_CLARIFICATION = "needs_user_clarification"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class Interpretation(BaseModel):
    restated_intent: str = ""
    assumptions: List[str] = Field(default_factory=list)


class Finding(BaseModel):
    message: str
    severity: Literal["info", "warning"] = "info"


class ContextRequest(BaseModel):
    """
    A structured request from the AI for more context about a specific,
    named reference -- resolved and bounded entirely by OnyxJar
    (ai.services.context_expansion.resolve_context_requests), never raw
    retrieval. `reference` is only actionable when kind="existing"; a "new"
    reference can never be something the AI needs more canonical context
    about, since it doesn't exist yet.
    """

    reference: EntityRef
    reason: str = ""


class AIStructuredResult(BaseModel):
    """The literal schema a provider call must return (passed as response_schema)."""

    schema_version: str = "1.0"
    interpretation: Interpretation = Field(default_factory=Interpretation)
    findings: List[Finding] = Field(default_factory=list)
    context_requests: List[ContextRequest] = Field(default_factory=list)
    change_plan: Optional[ChangePlan] = None
    unresolved_issues: List[UnresolvedIssue] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


@dataclass
class OperationResult:
    """What run_ai_operation returns to its caller."""

    execution_status: ExecutionStatus
    outcome: OperationOutcome
    execution_id: uuid.UUID
    proposal_id: Optional[uuid.UUID]
    explanation: str
    refinement_cycles: int
    context_expansions: int
    unresolved_issues: List[UnresolvedIssue] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
