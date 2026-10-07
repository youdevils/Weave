"""
Coverage: which target-relevant evidence was actually examined (C2 coverage
gate). Deterministic; a coverage decision is never a claim about the domain.

A segment is *target-relevant* when it mentions, by name (word-boundary,
plural-insensitive), an extracted entity of a target type or an anchor the
intent names ("named target"), or -- for structured segments only (table
rows, list items), where a type word usually denotes an item -- a target
type's label, in its own text or (for a table row) in its table's header
row: a row of a "Venue | ..." table is about venues even when nothing has
been extracted from it yet. Headings and table header segments are context,
never required coverage. Each entry records the target types it is relevant
to, so an uncovered segment becomes that target's evidence gap.

Each relevant segment ends in exactly one of three distinct states:

    claimed    cited by a validated claim. A table row with two or more
               cells is relational, so it is claimed only by an assertion or
               a fact -- an entity that merely cites the row doesn't account
               for what the row says.
    dismissed  the AI said it is not relevant (a coverage decision with its
               reason). A dismissal of a segment that names a target is
               *flagged*: re-asked once, then kept but listed for
               Verification and in the run's findings.
    uncovered  neither -- re-asked once, then recorded (partial coverage).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph, cited_segments
from ai.services.intent_frame import IntentFrame
from ai.services.reconcile.mapping import _label_matches
from ai.services.semantic.index import SemanticModelIndex
from ai.services.sources import mentions

CLAIMED, DISMISSED, UNCOVERED = "claimed", "dismissed", "uncovered"
_REQUIRED_KINDS = ("text_block", "list_item", "table_row")


@dataclass
class SegmentCoverage:
    segment_id: str
    status: str
    named: list = field(default_factory=list)  # target/anchor names it mentions
    labelled: bool = False  # relevant only through a target type label
    cited_by: list = field(default_factory=list)
    reason: str = ""
    # Target ObjectType ids this segment is relevant to.
    type_ids: list = field(default_factory=list)

    @property
    def named_target(self) -> bool:
        return bool(self.named)

    @property
    def flagged(self) -> bool:
        return self.status == DISMISSED and self.named_target


def target_types(frame: IntentFrame, index: SemanticModelIndex) -> dict[str, list[str]]:
    """Target ObjectType id -> the intent's labels for it."""

    found: dict[str, list[str]] = {}
    for target in frame.targets:
        if target.verb == "retire":
            continue
        hinted = index.object_type_by_key(target.type_hint) if target.type_hint else None
        for type_id in ({hinted.id} if hinted is not None else {t.id for t in _label_matches(index, target.type_label)}):
            found.setdefault(type_id, []).append(target.type_label)
    return found


def target_type_ids(frame: IntentFrame, index: SemanticModelIndex) -> set[str]:
    return set(target_types(frame, index))


def _entity_type_ids(entity, index) -> set[str]:
    hinted = index.object_type_by_key(entity.type_hint) if entity.type_hint else None
    if hinted is not None:
        return {hinted.id}
    return {t.id for t in _label_matches(index, entity.type_label)}


def _unique(values) -> list[str]:
    return [v for v in dict.fromkeys(values) if (v or "").strip()]


def relevance_by_type(frame: IntentFrame, graph: EvidenceGraph, index: SemanticModelIndex) -> dict:
    """Target type id -> (names of its extracted entities, its labels)."""

    result = {}
    for type_id, labels in target_types(frame, index).items():
        names = []
        for entity in graph.entities:
            if entity.specificity == "specific" and type_id in _entity_type_ids(entity, index):
                names += [entity.name, *entity.aliases]
        own = [*labels, index.object_types[type_id].name if type_id in index.object_types else ""]
        result[type_id] = (_unique(names), _unique(own))
    return result


def relevance(frame: IntentFrame, graph: EvidenceGraph, index: SemanticModelIndex) -> tuple[list[str], list[str]]:
    """-> (target/anchor names, target type labels)."""

    by_type = relevance_by_type(frame, graph, index)
    names = [a.name for a in frame.anchors] + [n for names, _ in by_type.values() for n in names]
    labels = [t.type_label for t in frame.targets] + [l for _, labels in by_type.values() for l in labels]
    return _unique(names), _unique(labels)


def labelled_by(segment, labels) -> bool:
    """A structured segment that names a kind: in its own text, or -- a table
    row -- in its table's header row."""

    if segment.kind not in ("table_row", "list_item"):
        return False
    return mentions(segment.text, labels) or (segment.kind == "table_row" and mentions(" | ".join(segment.header or []), labels))


def _relational(segment) -> bool:
    return segment.kind == "table_row" and sum(1 for c in segment.cells if c.strip()) >= 2


def compute_coverage(bundle: EvidenceBundle, graph: EvidenceGraph, frame: IntentFrame, index: SemanticModelIndex, dismissals: dict) -> dict[str, SegmentCoverage]:
    names, labels = relevance(frame, graph, index)
    by_type = relevance_by_type(frame, graph, index)
    citations: dict[str, list] = {}
    for item in graph.items():
        for segment_id in cited_segments(item):
            citations.setdefault(segment_id, []).append(item)

    result = {}
    for segment in bundle.segments():
        if segment.kind not in _REQUIRED_KINDS:
            continue
        named = [n for n in names if mentions(segment.text, [n])]
        labelled = not named and labelled_by(segment, labels)
        if not (named or labelled):
            continue
        type_ids = [
            type_id for type_id, (type_names, type_labels) in by_type.items()
            if any(mentions(segment.text, [n]) for n in type_names) or labelled_by(segment, type_labels)
        ]
        cited = citations.get(segment.segment_id, [])
        if _relational(segment):
            cited = [i for i in cited if not hasattr(i, "eid")]
        cited_ids = [getattr(i, "eid", None) or getattr(i, "aid", None) or getattr(i, "fid", None) for i in cited]
        dismissal = dismissals.get(segment.segment_id)
        if cited_ids:
            status, reason = CLAIMED, ""
        elif dismissal:
            status, reason = DISMISSED, dismissal.get("reason", "")
        else:
            status, reason = UNCOVERED, ""
        result[segment.segment_id] = SegmentCoverage(segment.segment_id, status, named, labelled, cited_ids, reason, type_ids)
    return result
