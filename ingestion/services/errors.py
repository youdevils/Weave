"""
Import failures, in the three shapes the workflow distinguishes.

  * SourceFileError  -- the file itself cannot be used (format, size, structure).
  * MappingError     -- the target/mapping is malformed.
  * ImportProblem    -- a *row* cannot be turned into a change deterministically
                        (unresolved / ambiguous identity, ...). Blocking, but
                        not an exception: a plan collects every one of them.

None of these is a Proposal validation error. Those ask "is this change
allowed?", after the change is known; these mean "I cannot tell what change
the source represents".
"""

from dataclasses import dataclass


class ImportError_(Exception):
    """Base for import failures raised as exceptions."""

    code = "import_error"

    def __init__(self, message, *, code=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class SourceFileError(ImportError_):
    code = "invalid_file"


class TargetError(ImportError_):
    code = "invalid_target"


class MappingError(ImportError_):
    """Carries every problem found, not just the first."""

    code = "invalid_mapping"

    def __init__(self, messages):
        messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("; ".join(messages))
        self.messages = messages


@dataclass(frozen=True)
class ImportProblem:
    code: str
    message: str
    row: int | None = None  # the source row number (header = first non-blank row)

    def to_dict(self):
        return {"code": self.code, "message": self.message, "row": self.row}


class ImportBlocked(ImportError_):
    """The plan has blocking problems; nothing was created."""

    code = "import_blocked"

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__(f"{len(self.problems)} problem(s) prevent this import.")
