"""
The vocabulary of a planned import, and the small rules every planner shares.

A plan answers one question: *what ProposalChanges would this source produce?*
It is built from canonical data only, never from any proposal, and never asks
whether those changes are allowed; that is the Proposal validator's business.
"""

import uuid
from dataclasses import dataclass, field

from ingestion.services import limits
from ingestion.services.errors import ImportProblem

CREATE = "create"
UPDATE = "update"

PREVIEW_ITEMS_SHOWN = 25
_SNIPPET_LENGTH = 80


@dataclass
class PlannedChange:
    """One ProposalChange, in the shape ProposalService.record_changes_bulk takes."""

    operation: str
    target_type: str
    target_id: uuid.UUID
    parent_type: str
    parent_id: uuid.UUID
    before: dict | None
    after: dict

    def to_spec(self) -> dict:
        return {
            "operation": self.operation,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "parent_type": self.parent_type,
            "parent_id": self.parent_id,
            "before": self.before,
            "after": self.after,
        }


@dataclass
class PreviewItem:
    """One record's outcome, for display."""

    operation: str  # create | update
    label: str
    row: int
    rows: int
    fields: list  # [{"field", "before", "after"}]

    def to_dict(self):
        return {
            "operation": self.operation,
            "label": self.label,
            "row": self.row,
            "rows": self.rows,
            "fields": self.fields,
        }


@dataclass
class PlanSummary:
    kind: str
    rows: int = 0
    creates: int = 0
    updates: int = 0
    no_ops: int = 0
    field_changes: int = 0
    duplicate_identities: int = 0
    duplicate_rows: int = 0
    unconverted_cells: int = 0
    warnings: list = field(default_factory=list)

    @property
    def change_count(self) -> int:
        return self.creates + self.field_changes

    def to_dict(self):
        return {
            "kind": self.kind,
            "rows": self.rows,
            "creates": self.creates,
            "updates": self.updates,
            "no_ops": self.no_ops,
            "field_changes": self.field_changes,
            "duplicate_identities": self.duplicate_identities,
            "duplicate_rows": self.duplicate_rows,
            "unconverted_cells": self.unconverted_cells,
            "warnings": list(self.warnings),
        }


@dataclass
class ImportPlan:
    summary: PlanSummary
    changes: list = field(default_factory=list)  # PlannedChange, in emission order
    problems: list = field(default_factory=list)  # ImportProblem (blocking)
    items: list = field(default_factory=list)  # PreviewItem (first few)

    @property
    def blocked(self) -> bool:
        return bool(self.problems)

    def to_preview(self) -> dict:
        shown = limits.problems_shown()

        return {
            "summary": self.summary.to_dict(),
            "blocked": self.blocked,
            "problem_count": len(self.problems),
            "problems": [problem.to_dict() for problem in self.problems[:shown]],
            "items": [item.to_dict() for item in self.items],
            "change_count": len(self.changes),
        }


class Target:
    """
    Everything the source says about one canonical record (or one new record),
    accumulated in file order. `assign` holds the latest value assigned to each
    mapped field, so a later row overwrites an earlier one and only the final
    value is ever compared with the canonical one.
    """

    __slots__ = ("existing_id", "new_id", "rows", "assign", "identified", "extra")

    def __init__(self, existing_id=None, identified=True, extra=None):
        self.existing_id = existing_id
        self.new_id = None if existing_id else uuid.uuid4()
        self.rows = []
        self.assign = {}
        # False for a new record with no identity: every such row stands alone.
        self.identified = identified
        self.extra = extra or {}

    @property
    def target_id(self):
        return self.existing_id or self.new_id


class Accumulator:
    """Targets in order of first appearance in the file."""

    def __init__(self):
        self.targets = {}

    def target(self, key, *, existing_id=None, identified=True, extra=None) -> Target:
        found = self.targets.get(key)

        if found is None:
            found = self.targets[key] = Target(existing_id, identified, extra)

        return found


def identity_key(value):
    """
    The key two identity values must share to count as equal: exact, type-strict
    (a boolean is never a number), and case-sensitive. None means the value
    cannot serve as an identity.
    """

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, str):
        return ("s", value)

    if isinstance(value, (int, float)):
        return ("n", value)

    return None


def values_equal(a, b) -> bool:
    """
    Canonical-vs-imported comparison. Absent and None are the same "empty";
    booleans equal only booleans; 1 equals 1.0.
    """

    if a is None or b is None:
        return a is None and b is None

    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b

    return a == b


def parse_uuid(value):
    """A UUID from a cell, or None if it is not one."""

    from ingestion.services.coercion import cell_text

    try:
        return uuid.UUID(cell_text(value).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def snippet(value) -> str:
    """A short, single-line rendition of an untrusted value for messages."""

    from ingestion.services.coercion import cell_text

    text = " ".join(cell_text(value).split())

    return text if len(text) <= _SNIPPET_LENGTH else text[: _SNIPPET_LENGTH - 1] + "…"


def problem(code, message, row=None) -> ImportProblem:
    return ImportProblem(code=code, message=message, row=row)


def enforce_change_limit(plan):
    """
    An import may produce at most IMPORT_MAX_CHANGES changes (an UPDATE is one
    change per field). Over the limit the import is blocked, not truncated.
    """

    maximum = limits.max_changes()

    if len(plan.changes) > maximum:
        plan.problems.append(
            problem(
                "too_many_changes",
                f"This import would produce {len(plan.changes)} changes; the limit is "
                f"{maximum}. Split the file into smaller imports.",
            )
        )
        plan.changes = []

    return plan
