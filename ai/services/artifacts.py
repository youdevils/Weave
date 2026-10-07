"""
Small structured shapes shared by every stage's response schema (see
ai.services.change_set for the ChangeSet, ai.services.evidence_graph /
ai.services.intent_frame for Reconcile's evidence-side contracts, and
ai.services.reconcile.responses for the remaining stage responses).

Every model here is a closed, strict-structured-output-compatible shape: it
is passed (nested) as an OpenAI `response_schema` (see
ai.tests.test_structured_output_schema).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    # An EvidenceBundle source id ("S1", ...) or "intent".
    source_id: str
    # Verbatim text from that source -- OnyxJar checks that it really occurs
    # there (within `segment_id`, when one is cited).
    excerpt: str
    # The source segment the excerpt is quoted from ("S1#4", "S1#t2.r3").
    segment_id: Optional[str] = None
    locator: Optional[str] = None


class Finding(BaseModel):
    """A user-facing observation. AI stages may only emit info/warning;
    OnyxJar also produces minor/material ones."""

    message: str
    severity: Literal["info", "warning", "minor", "material"] = "info"


class Clarification(BaseModel):
    needed: bool = False
    question: str = ""


class Interpretation(BaseModel):
    restated_intent: str = ""
    requested_outcomes: list[str] = Field(default_factory=list)
