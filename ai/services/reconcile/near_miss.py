"""
Gap Probe retrieval (C6, revised): OnyxJar decides *which evidence* a probe
reads; the probe only says what that evidence states.

For each unsatisfied requirement OnyxJar builds its own evidence list:

    - every segment that mentions the entity by name/alias (word-boundary,
      plural-insensitive);
    - when a *heading* names the entity (a document titled with it), the
      segments under that heading -- those in a section whose heading names
      the counterpart's kind first (the "Teams" grid under a tournament's
      title), then the rest -- because what a section lists under its title
      is evidence about it;
    - for text blocks and list items, the adjacent block on each side;
    - and, always, the heading and table segments these sit under, as real
      citable segments (ai.services.sources.with_ancestors);
    - plus the claims already extracted from those segments (so the probe
      extends them instead of re-declaring them).

Packs are deduplicated across requirements and bounded by
AI_GAP_PROBE_PACK_MAX_CHARS (mention segments first, context after). A
requirement's coverage is `complete` only when every segment mentioning its
entity is in the pack -- that, not the probe's say-so, is what a later
`not_stated` verdict's coverage records.

Each requirement is posed as an evidence *question* about its entity ("what
do these segments say about X? OnyxJar is looking for any <kind> related to
it"), in catalogue names and descriptions, never relationship keys and never
as a rule to be satisfied: the probe returns source-semantic claims, and
OnyxJar maps them like any other (I2; ai/README.md).

A *target gap* (an intent target the evidence has not yet yielded items
for) is posed at the level of the requested kind ("what do these segments
say about venues?") over its own segments: those labelled by the kind (in
their text, their table's header, or a heading above them), or the
target-relevant segments nothing has accounted for yet. Its `found` must
name claims OnyxJar maps to that kind (re-checked by the analysis).
"""

from __future__ import annotations

from django.conf import settings

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import cited_segments
from ai.services.reconcile.analysis import Analysis, TargetGap
from ai.services.semantic.index import SemanticModelIndex
from ai.services.sources import mentions, with_ancestors

_SEARCHED = ("text_block", "list_item", "table_row")


def question(requirement, analysis: Analysis, index: SemanticModelIndex) -> str:
    counterpart = index.object_types[requirement.counterpart_type_id].name
    relationship = index.relationship_types[requirement.relationship_type_id].name
    name = analysis.cluster_name(requirement.cluster_id)
    return (
        f"What do this requirement's segments say about '{name}'? OnyxJar is looking for any {counterpart} related to it "
        f"('{relationship}'). Report only what the segments state; if they don't identify one, that is not_stated."
    )


def target_question(gap: TargetGap, index: SemanticModelIndex) -> str:
    item = index.type_by_id(gap.type_id)
    kind = item.name if item else gap.type_label
    if gap.kind == "relationship_type":
        looking = f"any '{kind}' relationship between the things they name"
    else:
        looking = f"any {kind} they name, and what they say about each"
    lead = (
        "These segments mention what the request is about, but nothing has been extracted from them yet. What do they say?"
        if gap.reason == "uncovered" else
        f"The request asks to {gap.verb} '{gap.type_label}', and nothing of that kind has been extracted yet. What do these segments say?"
    )
    return f"{lead} OnyxJar is looking for {looking}. Report only what the segments state; if they name none, that is not_stated."


def _target_requirement(gap: TargetGap, own, index: SemanticModelIndex, bundle: EvidenceBundle) -> dict:
    item = index.type_by_id(gap.type_id)
    looking_for = {"kind": item.name if item else gap.type_label, "kind_description": item.description if item else ""}
    if gap.kind == "relationship_type":
        looking_for = {"relationship": looking_for["kind"], "relationship_description": looking_for["kind_description"]}
    return {
        "requirement_id": gap.requirement_id,
        "requested": {"type_label": gap.type_label, "verb": gap.verb},
        "question": target_question(gap, index),
        "looking_for": looking_for,
        "segment_ids": [s.segment_id for s in with_ancestors(bundle, own)],
        # OnyxJar-side, never sent: a target-level "found" is checked by kind.
        "_target": gap.target_id,
    }


def _section_members(bundle: EvidenceBundle, names, counterpart_labels) -> list:
    """Segments under a heading that names the entity; those in a section
    whose own heading names the counterpart's kind first."""

    anchors = {s.segment_id for s in bundle.segments() if s.kind == "heading" and mentions(s.text, names)}
    if not anchors:
        return []
    members = [s for s in bundle.segments() if s.kind in _SEARCHED and anchors & set(s.ancestor_ids)]
    return sorted(members, key=lambda s: (not mentions(" ".join(s.heading_path), counterpart_labels), s.source_id, s.position))


def probe_payload(requests, analysis: Analysis, *, index: SemanticModelIndex, bundle: EvidenceBundle) -> tuple[list[dict], list[dict], dict]:
    """-> (requirements, pack segments, {requirement id: "complete" | "partial"})."""

    mention_sets, context_sets = {}, {}
    for requirement in requests:
        if isinstance(requirement, TargetGap):
            mention_sets[requirement.requirement_id] = [sid for sid in requirement.segment_ids if bundle.segment(sid) is not None]
            context_sets[requirement.requirement_id] = []
            continue
        cluster = analysis.clusters.clusters[requirement.cluster_id]
        names = [cluster.name, *cluster.aliases]
        counterpart = index.object_types[requirement.counterpart_type_id]
        hits = [s for s in bundle.segments() if s.kind in _SEARCHED and mentions(s.text, names)]
        hit_ids = {s.segment_id for s in hits}
        hits += [s for s in _section_members(bundle, names, [counterpart.name, counterpart.key.replace("_", " ")]) if s.segment_id not in hit_ids]
        context = []
        for segment in hits:
            if segment.kind in ("text_block", "list_item"):
                context += [n for n in bundle.neighbours(segment) if n.kind in _SEARCHED]
        mention_sets[requirement.requirement_id] = [s.segment_id for s in hits]
        context_sets[requirement.requirement_id] = [s.segment_id for s in context]

    budget = settings.AI_GAP_PROBE_PACK_MAX_CHARS
    chosen: list[str] = []

    def take(segment_id):
        nonlocal budget
        if segment_id in chosen:
            return True
        segment = bundle.segment(segment_id)
        if segment is None or len(segment.text) > budget:
            return False
        chosen.append(segment_id)
        budget -= len(segment.text)
        return True

    # Mentions first, round-robin across requirements, then context.
    for pool in (mention_sets, context_sets):
        queues = {k: list(v) for k, v in pool.items()}
        while any(queues.values()):
            for key in list(queues):
                if queues[key]:
                    take(queues[key].pop(0))

    order = {s.segment_id: (s.source_id, s.position) for s in bundle.segments()}
    chosen.sort(key=lambda sid: order.get(sid, ("", 0)))
    coverage = {
        rid: "complete" if set(ids) <= set(chosen) and not any(s.truncated for s in bundle.sources) else "partial"
        for rid, ids in mention_sets.items()
    }

    in_pack = set(chosen)
    requirements = []
    for requirement in requests:
        own = [s for s in mention_sets[requirement.requirement_id] + context_sets[requirement.requirement_id] if s in in_pack]
        if isinstance(requirement, TargetGap):
            requirements.append(_target_requirement(requirement, own, index, bundle))
            continue
        cluster = analysis.clusters.clusters[requirement.cluster_id]
        requirements.append({
            "requirement_id": requirement.requirement_id,
            "entity": {"eid": cluster.member_eids[0], "name": cluster.name, "aliases": cluster.aliases,
                       "kind": index.object_types[analysis.types[requirement.cluster_id].type_id].name},
            "question": question(requirement, analysis, index),
            "looking_for": {
                "kind": index.object_types[requirement.counterpart_type_id].name,
                "kind_description": index.object_types[requirement.counterpart_type_id].description,
                "relationship": index.relationship_types[requirement.relationship_type_id].name,
                "relationship_description": index.relationship_types[requirement.relationship_type_id].description,
            },
            # This requirement's own evidence (with the headings/tables they sit under).
            "segment_ids": [s.segment_id for s in with_ancestors(bundle, own)],
            # OnyxJar-side, never sent: what a "found" verdict must involve.
            "_entity_ids": list(cluster.member_eids),
        })

    segments = [s.context() for s in with_ancestors(bundle, chosen)]
    return requirements, segments, coverage


def pack_claims(analysis: Analysis, segment_ids) -> dict:
    """Claims already extracted from the pack's segments -- compact."""

    wanted = set(segment_ids)
    graph = analysis.graph
    return {
        "entities": [
            {"eid": e.eid, "name": e.name, "type_label": e.type_label, "specificity": e.specificity}
            for e in graph.entities if cited_segments(e) & wanted
        ],
        "assertions": [
            {"aid": a.aid, "subject_eid": a.subject_eid, "predicate": a.predicate, "object_eid": a.object_eid}
            for a in graph.assertions if cited_segments(a) & wanted
        ],
    }
