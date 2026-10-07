"""
The final deterministic gate shared by every proposal-producing workflow:
re-resolve the accepted ChangeSet against canonical state as it stands now,
then compile + apply + validate + commit it atomically
(ai.services.staging.commit_proposal).
"""

from __future__ import annotations

from dataclasses import dataclass

from model.services.proposal.evidence import CHANGE_NOTE_MAX_LENGTH

from ai.services.feedback import AIIssue, translate_validation_issues
from ai.services.resolution import resolve_change_set
from ai.services.result_schema import ExecutionStatus, OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.staging import commit_proposal
from ai.services.workflow.engine import Finish


@dataclass
class CommitOutcome:
    proposal: object = None
    issues: list[AIIssue] | None = None
    aborted: bool = False  # the caller no longer wants a Proposal (task reclaimed)


def proposal_summary(run) -> str:
    state = run.state
    parts = [state.change_set.summary.strip() if state.change_set and state.change_set.summary else ""]
    if state.blocked_targets:
        parts.append(
            "Not included (could not be reconciled from the evidence):\n"
            + "\n".join(f"- {b['type_key']} '{b['target']}'" + (f" (and {', '.join(b['dependants'])})" if b["dependants"] else "") for b in state.blocked_targets)
        )
    notes = [f.message for f in (*state.review_notes, *state.plan_findings)]
    if notes:
        parts.append("Review notes:\n" + "\n".join(f"- {note}" for note in notes))
    text = "\n\n".join(part for part in parts if part)
    if len(text) > CHANGE_NOTE_MAX_LENGTH:
        text = text[: CHANGE_NOTE_MAX_LENGTH - 1] + "…"
    return text


def commit(run, *, resolution=None, index=None) -> CommitOutcome:
    """`resolution`/`index` may be passed when they were computed against
    canonical state moments ago in this same stage; otherwise both are
    rebuilt fresh, since canonical state may have moved since staging."""

    state = run.state
    if resolution is None:
        index = SemanticModelIndex.load(run.model)
        resolution = resolve_change_set(
            state.change_set,
            model=run.model,
            index=index,
            policy=run.operation.policy,
            bundle=run.bundle,
            intent_text=run.intent.text,
        )
        if resolution.issues:
            return CommitOutcome(issues=resolution.issues)

    result = commit_proposal(
        model=run.model,
        user=run.user,
        operation=run.operation,
        resolution=resolution,
        summary=proposal_summary(run),
        should_commit=run.should_commit,
    )
    if result.proposal is not None:
        return CommitOutcome(proposal=result.proposal)
    if not result.issues:
        return CommitOutcome(aborted=True)
    return CommitOutcome(issues=translate_validation_issues(result.issues, ref_map=resolution.ref_map, index=index))


def commit_decision(run, outcome: CommitOutcome, *, on_issues):
    if outcome.proposal is not None:
        return Finish(OperationOutcome.READY_FOR_REVIEW, explanation=run.state.interpretation, proposal=outcome.proposal)
    if outcome.aborted:
        return Finish(
            OperationOutcome.FAILED,
            execution_status=ExecutionStatus.FAILED,
            error="The assisted task stopped running before its proposal could be saved.",
        )
    return on_issues(outcome.issues)
