"""
The IntentFrame: the user's intent as explicit, excerpted claims -- which
kinds of thing they want added/updated/retired/linked (targets), which
existing entities they name (anchors), and whether related relationships are
wanted. Every element quotes the intent text it rests on, so a framing (or a
Verification `frame_error` amendment) can never assert an intent the user
did not express.

The intent is the authority for what was asked, and framing claims are
grounded in it the way evidence claims are grounded in sources:

    L1  the excerpt is a verbatim span of the intent. Several elements may
        quote the same span ("add the venues and stages" frames two
        targets). An excerpt elided with "..." whose fragments all occur in
        the intent, in order, within one sentence, is literally repaired to
        the covering span (`repair_elisions`; recorded, never semantic).
    L2  the span mentions what the element is about: a target's own type
        label, an anchor's name.

An element that still fails after its one re-ask is never deleted: it is
kept as *unframed* requested work (ai.services.reconcile.state), reported,
and recoverable by a Verification `frame_error` amendment.

Like the EvidenceGraph, it is not ontology-checked here: mapping a target's
type label onto the catalogue happens in ai.services.reconcile.scope.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from ai.services.evidence_bundle import excerpt_occurs
from ai.services.feedback import AIIssue, issue
from ai.services.sources import mentions

_ELISION = re.compile(r"\s*(?:\[\s*\.\.\.\s*\]|\.\.\.|\u2026)\s*")
_MAX_ELIDED_GAP = 120


class FrameTarget(BaseModel):
    target_id: str
    # The intent's own word for the kind of thing ("venues", "stages").
    type_label: str
    # Optional catalogue ObjectType/RelationshipType key -- a hint.
    type_hint: Optional[str] = None
    verb: Literal["add", "update", "retire", "link"] = "add"
    excerpt: str


class FrameAnchor(BaseModel):
    anchor_id: str
    # An existing entity the intent names ("the 2027 Championship").
    name: str
    type_hint: Optional[str] = None
    excerpt: str


class IntentFrame(BaseModel):
    restated_intent: str = ""
    targets: list[FrameTarget] = Field(default_factory=list)
    anchors: list[FrameAnchor] = Field(default_factory=list)
    # "...and create any relationships that should be associated": optional
    # (min 0) relationships between in-scope entities are wanted too.
    include_related: bool = False
    include_related_excerpt: Optional[str] = None


class FrameAmendment(BaseModel):
    """A Verification `frame_error` correction -- every addition quotes the intent."""

    add_targets: list[FrameTarget] = Field(default_factory=list)
    remove_target_ids: list[str] = Field(default_factory=list)
    add_anchors: list[FrameAnchor] = Field(default_factory=list)
    include_related: Optional[bool] = None
    include_related_excerpt: Optional[str] = None


def covering_span(excerpt, intent_text) -> str | None:
    """The intent span an elided excerpt ("add the venues ... listed")
    stands for: every fragment verbatim, in order, within one sentence, with
    bounded gaps. None when the excerpt is not an elision of the intent."""

    fragments = [f.strip(" ,;:") for f in _ELISION.split(excerpt or "")]
    fragments = [f for f in fragments if f]
    if len(fragments) < 2 or not _ELISION.search(excerpt or ""):
        return None
    pieces = [r"\s+".join(re.escape(word) for word in fragment.split()) for fragment in fragments]
    pattern = f"[^.!?]{{0,{_MAX_ELIDED_GAP}}}?".join(pieces)
    found = re.search(pattern, intent_text or "", flags=re.IGNORECASE)
    return found.group(0) if found else None


def repair_elisions(frame: IntentFrame, intent_text: str) -> tuple[IntentFrame, dict]:
    """Literal repair of elided excerpts to their covering intent span.
    -> (repaired copy, {element id: original excerpt})."""

    copy, repaired = frame.model_copy(deep=True), {}
    for element, identifier in [*((t, t.target_id) for t in copy.targets), *((a, a.anchor_id) for a in copy.anchors)]:
        if excerpt_occurs(element.excerpt, intent_text):
            continue
        span = covering_span(element.excerpt, intent_text)
        if span is not None:
            repaired[identifier] = element.excerpt
            element.excerpt = span
    if copy.include_related and copy.include_related_excerpt and not excerpt_occurs(copy.include_related_excerpt, intent_text):
        span = covering_span(copy.include_related_excerpt, intent_text)
        if span is not None:
            repaired["include_related"] = copy.include_related_excerpt
            copy.include_related_excerpt = span
    return copy, repaired


def validate_intent_frame(frame: IntentFrame, intent_text: str) -> list[AIIssue]:
    issues: list[AIIssue] = []
    seen = set()
    for element, identifier in [*((t, t.target_id) for t in frame.targets), *((a, a.anchor_id) for a in frame.anchors)]:
        if not identifier.strip() or identifier in seen:
            issues.append(issue("duplicate_id", f"Intent frame id '{identifier}' must be non-empty and unique.", item_id=identifier))
        seen.add(identifier)
        if not excerpt_occurs(element.excerpt, intent_text):
            issues.append(issue(
                "excerpt_not_found",
                f"Intent frame element '{identifier}': excerpt must be a verbatim span of the intent, never elided with '...'. "
                "Several targets may quote the same span (e.g. both 'venues' and 'stages' may quote \"add the venues and stages\").",
                item_id=identifier,
            ))
            continue
        about = element.type_label if isinstance(element, FrameTarget) else element.name
        if about.strip() and not mentions(element.excerpt, [about]):
            issues.append(issue(
                "unanchored_claim",
                f"Intent frame element '{identifier}': its excerpt does not mention '{about}'. Quote the words of the intent that name it.",
                item_id=identifier,
            ))
    for target in frame.targets:
        if not target.type_label.strip():
            issues.append(issue("malformed_item", f"Target '{target.target_id}' needs a type_label.", item_id=target.target_id))
    if frame.include_related and not (frame.include_related_excerpt and excerpt_occurs(frame.include_related_excerpt, intent_text)):
        issues.append(issue("excerpt_not_found", "include_related=true must quote the intent words that ask for it.", item_id="include_related"))
    return issues


def amend(frame: IntentFrame, amendment: FrameAmendment) -> IntentFrame:
    copy = frame.model_copy(deep=True)
    copy.targets = [t for t in copy.targets if t.target_id not in set(amendment.remove_target_ids)]
    copy.targets.extend(t.model_copy(deep=True) for t in amendment.add_targets)
    copy.anchors.extend(a.model_copy(deep=True) for a in amendment.add_anchors)
    if amendment.include_related is not None:
        copy.include_related = amendment.include_related
        copy.include_related_excerpt = amendment.include_related_excerpt
    return copy
