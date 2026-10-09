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

    claimed    cited by a validated claim, and every target entity it names
               is accounted for: an endpoint of an assertion (or the
               subject of a fact) that cites it. A claim citing the row
               about something else doesn't account for the target entity
               it names (a fixture row "Pool A | New Zealand v Fiji | Eden
               Park" claimed only as "Pool A ... New Zealand" says nothing
               about Eden Park). A table row with two or more cells is
               relational, so only an assertion or a fact accounts for
               anything in it -- an entity that merely cites the row doesn't
               account for what the row says; elsewhere an entity citing the
               segment accounts for itself.
    dismissed  the AI said it is not relevant (a coverage decision with its
               reason). A dismissal of a segment that names a target is
               *flagged*: re-asked once, then kept but listed for
               Verification and in the run's findings.
    uncovered  neither -- re-asked once, then recorded (partial coverage).

A segment that is cited, but names a target entity no citing claim accounts
for, is not claimed: it is dismissed (when the AI dismissed it) or uncovered,
and `unaccounted` lists those entities' names; its `type_ids` are then theirs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.document import queries
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph, cited_segments
from ai.services.intent_frame import IntentFrame
from ai.services.reconcile.mapping import _label_matches
from ai.services.semantic.index import SemanticModelIndex, normalize_name
from ai.services.sources import contains_tokens, mentions, tokens

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
    # Names of target entities it names that no claim citing it accounts for.
    unaccounted: list = field(default_factory=list)

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


# Layout predicates live in the DEM's structural queries (ai.services.document).
labelled_by = queries.labelled_by
header_labelled = queries.header_labelled
_relational = queries.relational


def _names(entity) -> set[str]:
    return {normalize_name(n) for n in (entity.name, *entity.aliases) if (n or "").strip()}


def _target_entities(frame: IntentFrame, graph: EvidenceGraph, index: SemanticModelIndex) -> list:
    """-> [(entity, its target type ids)] for every specific entity of a target type."""

    types = target_type_ids(frame, index)
    found = []
    for entity in graph.entities:
        own = _entity_type_ids(entity, index) & types
        if entity.specificity == "specific" and own:
            found.append((entity, own))
    return found


def _masked(hay: list[str], sequences) -> list[str]:
    """`hay` with every occurrence of `sequences` blanked (longest first)."""

    hay = list(hay)
    for sequence in sorted(sequences, key=len, reverse=True):
        start = 0
        while start + len(sequence) <= len(hay):
            if hay[start:start + len(sequence)] == sequence:
                hay[start:start + len(sequence)] = [""] * len(sequence)
                start += len(sequence)
            else:
                start += 1
    return hay


def _named_as(hay: list[str], entity, name_tokens) -> str | None:
    """The name (or alias) by which a segment's tokens name `entity`, other
    than inside the longer name of another extracted entity ('Final' within
    'Quarter-finals', 'Pool A' within the match 'Pool A winner v Pool B
    runner-up'); None when it doesn't."""

    for name in (entity.name, *entity.aliases):
        own = tokens(name)
        if not own:
            continue
        longer = [t for t in name_tokens if len(t) > len(own) and contains_tokens(t, own)]
        if contains_tokens(_masked(hay, longer), own):
            return name
    return None


def _accounted_names(graph: EvidenceGraph, cited, *, relational: bool) -> set[str]:
    """Normalised names of the entities the claims citing a segment are about."""

    names: set[str] = set()

    def endpoint(identifier):
        entity = graph.entity(identifier)
        if entity is not None:
            names.update(_names(entity))
            return
        assertion = graph.assertion(identifier)
        if assertion is not None:
            endpoint(assertion.subject_eid)
            endpoint(assertion.object_eid)

    for item in cited:
        if hasattr(item, "aid"):
            endpoint(item.subject_eid)
            endpoint(item.object_eid)
        elif hasattr(item, "fid"):
            endpoint(item.subject_id)
        elif not relational:
            names.update(_names(item))
    return names


def compute_coverage(bundle: EvidenceBundle, graph: EvidenceGraph, frame: IntentFrame, index: SemanticModelIndex, dismissals: dict,
                     scope=None) -> dict[str, SegmentCoverage]:
    """`scope` (readings mode): the prose-eligible segments -- structured
    content is accounted for by its Reading, never by per-segment claims."""

    names, labels = relevance(frame, graph, index)
    by_type = relevance_by_type(frame, graph, index)
    entities = _target_entities(frame, graph, index)
    name_tokens = [t for e in graph.entities for t in (tokens(n) for n in (e.name, *e.aliases)) if t]
    citations: dict[str, list] = {}
    for item in graph.items():
        for segment_id in cited_segments(item):
            citations.setdefault(segment_id, []).append(item)

    result = {}
    for segment in bundle.segments():
        if segment.kind not in _REQUIRED_KINDS or (scope is not None and segment.segment_id not in scope):
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
        relational = _relational(segment)
        if relational:
            cited = [i for i in cited if not hasattr(i, "eid")]
        cited_ids = [getattr(i, "eid", None) or getattr(i, "aid", None) or getattr(i, "fid", None) for i in cited]
        unaccounted, unaccounted_types = [], []
        if cited_ids:
            accounted = _accounted_names(graph, cited, relational=relational)
            hay, reported = tokens(segment.text), set()
            for entity, own in entities:
                if _names(entity) & accounted:
                    continue
                # Reported as the source names it, once (an alias shared by two
                # extracted entities is one mention).
                named_as = _named_as(hay, entity, name_tokens)
                if named_as is not None and normalize_name(named_as) not in reported:
                    reported.add(normalize_name(named_as))
                    unaccounted.append(named_as)
                if named_as is not None:
                    unaccounted_types += [t for t in own if t not in unaccounted_types]
        dismissal = dismissals.get(segment.segment_id)
        if unaccounted:
            type_ids = unaccounted_types
        if cited_ids and not unaccounted:
            status, reason = CLAIMED, ""
        elif dismissal:
            status, reason = DISMISSED, dismissal.get("reason", "")
        else:
            status, reason = UNCOVERED, ""
        result[segment.segment_id] = SegmentCoverage(segment.segment_id, status, named, labelled, cited_ids, reason, type_ids, unaccounted)
    return result
