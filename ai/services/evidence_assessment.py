"""
The deterministic, OJ-side backstop over a Change Plan's self-reported
EvidenceAssessment verdicts -- an OperationDefinition.plan_sufficiency_check
implementation (see ai.services.orchestrator), not Reconcile-specific
machinery, even though Reconcile is its first real caller.

The AI is not the orchestrator: a candidate's own "supported" verdict is
never trusted at face value when a cheap, deterministic check can catch it
being wrong. Today that means exactly one hard rule (a delete/retire action
must cite at least one evidence item -- "this new document doesn't mention
it" is never, by itself, grounds for removing something); everything else
about whether cited evidence is *accurate* is a prompt instruction
(ai.services.operation_definitions.RECONCILE_PROMPT_FRAGMENT), not something
this function can cheaply verify.

Any non-empty result here blocks the whole Change Plan from compiling this
cycle -- the same all-or-nothing shape ai.services.change_plan.validate_change_plan
already uses. This function never edits the plan; it only gates it.
"""

from __future__ import annotations

from ai.services.change_plan import ChangePlan, UnresolvedIssue


def assess_change_plan(plan: ChangePlan) -> list[UnresolvedIssue]:
    issues: list[UnresolvedIssue] = []

    for action in plan.actions:
        if action.assessment.verdict != "supported":
            issues.append(
                UnresolvedIssue(
                    code="candidate_not_supported",
                    message=(
                        f"Candidate action on {action.target_ref.id} was assessed as "
                        f"'{action.assessment.verdict}': {action.assessment.reasoning}"
                    ),
                    target_ref=action.target_ref,
                )
            )
            continue

        if action.operation == "delete" and not action.evidence:
            issues.append(
                UnresolvedIssue(
                    code="delete_requires_evidence",
                    message=(
                        "A delete/retire action must be backed by at least one evidence "
                        "item; absence of mention in new evidence is never by itself "
                        "sufficient grounds for deletion."
                    ),
                    target_ref=action.target_ref,
                )
            )

    return issues
