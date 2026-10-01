"""
Shared apply-and-validate step for a Proposal's changes.

This is the one place that both the real commit pipeline (submission.process)
and anything that needs to speculatively check a candidate Proposal without
committing it (e.g. the ai app's compile_and_validate) go through -- so there
is exactly one implementation of "apply this proposal's changes to canonical
tables, then validate the result", not two.

Writes nothing durable on its own: the caller decides, inside its own open
transaction, whether to keep or discard what apply_and_validate did.
"""

from dataclasses import dataclass

from model.services.proposal.submission import _apply_changes
from model.services.validation.model_validation import validate_model
from model.services.validation.result import ValidationIssue


@dataclass
class ApplyAndValidateResult:
    issues: list[ValidationIssue]
    before_revision: int


def apply_and_validate(model, proposal) -> ApplyAndValidateResult:
    """
    Apply every change in `proposal` to `model`'s canonical tables, still
    inside the caller's open transaction, then run validate_model(model).
    Returns the combined issues and the model's revision as it stood when
    called.
    """

    before_revision = model.revision
    apply_issues = _apply_changes(model, proposal)
    result = validate_model(model)

    return ApplyAndValidateResult(
        issues=apply_issues + result.issues,
        before_revision=before_revision,
    )
