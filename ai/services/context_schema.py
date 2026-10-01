"""
The AI context packet: a deliberately bounded, versioned snapshot of
canonical model state, assembled by ai.services.context_builder. Never built
from, or overlaid with, an in-progress AI candidate -- see
ai.services.orchestrator and ai.services.proposal_compiler.compile_and_validate
for why there is never one to overlay.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ContextPacket(BaseModel):
    schema_version: str = "1.0"
    intent: str
    model_id: str
    model_name: str
    model_purpose: str = ""
    model_scope: str = ""
    model_exclusions: str = ""
    # Which canonical revision this packet was built from -- observability
    # only. Never compared against a later revision to reject or restart an
    # in-flight operation; see the orchestrator's module docstring.
    model_revision: int

    ontology: Dict[str, Any] = Field(default_factory=dict)
    objects: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)

    evidence_context: List[Dict[str, Any]] = Field(default_factory=list)
    # Pre-resolved, bounded content only -- {"name", "content", "mime_type"}.
    # The AI service never fetches a URL itself.
    assets: List[Dict[str, Any]] = Field(default_factory=list)

    # Plain dicts derived from the previous cycle's ValidationIssue/
    # UnresolvedIssue objects -- the one feedback channel refinement uses,
    # reusing the context packet that is rebuilt every cycle anyway rather
    # than inventing a second mechanism.
    previous_attempt_issues: List[Dict[str, Any]] = Field(default_factory=list)

    # True only when a configured limit (AI_CONTEXT_MAX_OBJECTS/
    # AI_CONTEXT_MAX_HOPS/AI_CONTEXT_MAX_BYTES) was actually hit while
    # building this packet. Informational -- never a failure or
    # semantic-completeness signal on its own.
    truncated: bool = False
    byte_size: int = 0
