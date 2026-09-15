import uuid
from dataclasses import dataclass


@dataclass
class ValidationIssue:
    code: str
    message: str
    field: str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None


@dataclass
class ValidationResult:
    issues: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return not self.issues
