"""
The final operation result contract.

Execution lifecycle (ExecutionStatus: did the AI run itself finish, fail, or
is it still running) is kept strictly separate from operation outcome
(OperationOutcome: what the run produced) -- a run can COMPLETE with outcome
UNRESOLVED (its bounded stage budgets were exhausted without a valid,
verified result), which is different from the run itself FAILING (a
provider/system error). See ai.services.orchestrator.

The structured provider responses themselves are per-stage artifacts:
ai.services.reconcile.responses (Extraction/Adjudication/Gap Probe/
Verification) and ai.services.change_set.PlanResult (Create's Planning).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ai.services.artifacts import Finding
from ai.services.feedback import AIIssue

__all__ = ["ExecutionStatus", "OperationOutcome", "OperationResult"]


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


@dataclass
class OperationResult:
    """What run_ai_operation returns to its caller."""

    execution_status: ExecutionStatus
    outcome: OperationOutcome
    execution_id: uuid.UUID
    proposal_id: Optional[uuid.UUID]
    explanation: str
    # Total corrections across every stage (deterministic + review-driven).
    refinement_cycles: int
    # Legacy counter, always 0 for staged workflows (kept for AssistedTask's
    # existing denormalized field).
    context_expansions: int = 0
    unresolved_issues: List[AIIssue] = field(default_factory=list)
    # User-facing findings (omitted/unrepresentable evidence, reviewer notes,
    # or -- on UNRESOLVED -- the material problems that remained).
    findings: List[Finding] = field(default_factory=list)
    provider_calls: int = 0
    stage_summary: dict = field(default_factory=dict)
    # READY_FOR_REVIEW only: "complete", or "partial" when some intent targets
    # were left out (blocked) and the Proposal holds the ones that could be
    # reconciled independently (OperationPolicy.partial_outcome).
    completeness: str = ""
    # [{target, cluster_id, type_key, reason, missing_requirements, dependants}]
    blocked_targets: List[dict] = field(default_factory=list)
