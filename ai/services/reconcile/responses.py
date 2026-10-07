"""
The literal response schemas of Reconcile's AI stages. Each is a closed,
strict-structured-output-compatible shape (ai.tests.test_structured_output_schema),
and each carries only *claims* -- evidence items, framing, chosen option ids,
objections -- never a mutation (no ChangeSet field anywhere).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from ai.services.artifacts import Clarification, Finding
from ai.services.evidence_graph import EvidenceGraph
from ai.services.intent_frame import FrameAmendment, IntentFrame


class SegmentDismissal(BaseModel):
    """A coverage decision -- "this segment says nothing relevant to the
    request" -- never a claim about the domain."""

    segment_id: str
    reason: str


class ExtractionResult(BaseModel):
    """Framing (first batch only) + Extraction of one batch of segments."""

    schema_version: str = "3.0"
    intent_frame: IntentFrame = Field(default_factory=IntentFrame)
    evidence: EvidenceGraph = Field(default_factory=EvidenceGraph)
    dismissed_segments: list[SegmentDismissal] = Field(default_factory=list)
    clarification: Clarification = Field(default_factory=Clarification)
    findings: list[Finding] = Field(default_factory=list)


class Citation(BaseModel):
    segment_id: str
    # Verbatim text of THAT segment.
    excerpt: str


class AdjudicationAnswer(BaseModel):
    question_id: str
    option_id: str
    # The segments the answer rests on, one citation per segment (a table's
    # header row and a data row are two citations).
    citations: list[Citation] = Field(default_factory=list)
    # Verbatim intent text, when the answer rests on the request itself.
    excerpt: str = ""
    note: str = ""


class AdjudicationResult(BaseModel):
    schema_version: str = "3.0"
    answers: list[AdjudicationAnswer] = Field(default_factory=list)


class ProbeVerdict(BaseModel):
    requirement_id: str
    # found: the pack's segments state it (the claims are in `claims`);
    # not_stated: they don't; ambiguous: they allow several candidates.
    status: Literal["found", "not_stated", "ambiguous"]
    segments_reviewed: list[str] = Field(default_factory=list)
    # found: the ids of the claims (in `claims`, or already extracted) that
    # relate the requirement's entity to what was found.
    claim_ids: list[str] = Field(default_factory=list)
    # ambiguous (or found): the eids of the candidate entities.
    candidate_eids: list[str] = Field(default_factory=list)
    note: str = ""


class ProbeResult(BaseModel):
    """A Gap Probe is targeted re-extraction: the same evidence-claim contract
    as Extraction (source-semantic claims citing segments; no relationship
    keys, hints or option ids), plus a verdict per requirement."""

    schema_version: str = "4.0"
    claims: EvidenceGraph = Field(default_factory=EvidenceGraph)
    verdicts: list[ProbeVerdict] = Field(default_factory=list)


ObjectionKind = Literal[
    "missed_evidence",
    "evidence_misread",
    "wrong_mapping",
    "missed_mapping",
    "wrong_indirect_reason",
    "wrong_merge",
    "conflict_mishandled",
    "wrong_identity",
    "wrong_adjudication",
    "scope_error",
    "unsupported_change",
    "frame_error",
    "intent_ambiguous",
]


class Objection(BaseModel):
    objection_id: str
    # decision: a ledger decision id; segment: a source id (missed evidence);
    # intent: the request itself; action: a ChangeSet action id.
    target_kind: Literal["decision", "segment", "intent", "action"]
    target_id: str
    kind: ObjectionKind
    severity: Literal["info", "minor", "material"] = "info"
    message: str
    # wrong_mapping / wrong_identity / wrong_adjudication / ...: one of the
    # options listed on the target decision.
    option_id: Optional[str] = None
    # missed_evidence: the claims the earlier steps missed.
    evidence: EvidenceGraph = Field(default_factory=EvidenceGraph)
    # frame_error: the amendment, every addition quoting the intent.
    frame_amendment: Optional[FrameAmendment] = None
    # intent_ambiguous: at least two readings that would change the result.
    readings: list[str] = Field(default_factory=list)
    excerpt: Optional[str] = None


class VerificationResult(BaseModel):
    schema_version: str = "3.0"
    verdict: Literal["approved", "approved_with_findings", "correction_required"]
    objections: list[Objection] = Field(default_factory=list)
    summary: str = ""
