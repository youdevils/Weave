"""
Evidence ingress: the single path by which any AI response's claims enter the
EvidenceGraph -- Extraction batches, their corrections, Gap Probe rounds and
corrections, and Verification `missed_evidence` patches. Deterministic,
literal, logged; it never creates or changes a semantic claim.

Provenance. The AI cites *where* it quotes from (`segment_id`); the logical
source is derived from the SourceIndex, never trusted:

    source_id = S1          the logical source (or "intent")
    segment_id = S1#t4.r1   the addressable location within it

A `source_id` that names a segment is moved to `segment_id` (repaired); a
segment that belongs to a different source than the one named is rejected
(`source_segment_mismatch`); a missing segment is filled where the excerpt
occurs in exactly one segment (ai.services.provenance.resolve_segments).

Identity. Ids in a response are *local* to it; OnyxJar owns the global
namespace:

    - a definition whose id is a correction's replacement keeps that id;
    - a definition repeating a known claim (same id, same content) is a
      reference to it, not a new claim (collapsed);
    - otherwise it gets its local id if globally unused, else a fresh flat id
      (`e17`, `a42`, `f9`) -- never a nested prefix;
    - references inside the response follow its own definitions first (a
      definition shadows a known id of the same name), then known ids;
    - identical duplicate definitions in one response collapse into one (their
      provenance merged); conflicting ones are all rejected, precisely.

Every outcome is appended to `ReconcileState.ingress_log` and ledgered by the
analysis as an `ingest:` coverage decision.
"""

from __future__ import annotations

import re

from ai.services.evidence_bundle import INTENT_SOURCE_ID, EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph, item_id
from ai.services.feedback import AIIssue, issue
from ai.services.provenance import resolve_segments
from ai.services.reconcile.normalise import normalize_value, singular
from ai.services.semantic.index import normalize_name

_SAFE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def log(rs, identifier, *, origin, outcome, reason="", local=None) -> None:
    rs.ingress_log.append({"id": identifier, "local": local or identifier, "origin": origin, "outcome": outcome, "reason": reason})


# -- provenance ------------------------------------------------------------------


def normalise_provenance(item, bundle: EvidenceBundle) -> tuple[list[str], list[AIIssue]]:
    """-> (repairs made, issues). Mutates `item.provenance`."""

    repairs, issues = [], []
    identifier = item_id(item)
    for p in item.provenance:
        if p.source_id == INTENT_SOURCE_ID:
            continue
        named_segment = bundle.segment(p.source_id)
        if named_segment is not None:
            if p.segment_id and p.segment_id != named_segment.segment_id:
                issues.append(issue("source_segment_mismatch", f"Cite source_id '{named_segment.source_id}' with segment_id '{p.segment_id}'; "
                                    f"'{p.source_id}' is a segment, not a source.", item_id=identifier))
                continue
            p.segment_id = named_segment.segment_id
            p.source_id = named_segment.source_id
            repairs.append("source_id_was_a_segment")
            continue
        if p.segment_id:
            segment = bundle.segment(p.segment_id)
            if segment is None:
                continue  # validation reports unknown_segment
            if p.source_id != segment.source_id:
                if bundle.source(p.source_id) is None:
                    p.source_id = segment.source_id
                    repairs.append("source_id_derived_from_segment")
                else:
                    issues.append(issue("source_segment_mismatch", f"Segment '{p.segment_id}' belongs to source '{segment.source_id}', "
                                        f"not '{p.source_id}'.", item_id=identifier))
    resolve_segments(item.provenance, bundle=bundle)
    return repairs, issues


# -- identity --------------------------------------------------------------------


def _signature(item, refs) -> tuple:
    """Content identity of a definition (after reference mapping)."""

    if hasattr(item, "eid"):
        return ("e", normalize_name(item.name), singular(item.type_label), item.specificity)
    if hasattr(item, "aid"):
        return ("a", refs(item.subject_eid), refs(item.object_eid), normalize_name(item.predicate), item.polarity)
    return ("f", refs(item.subject_id), singular(item.label), normalize_value(item.value))


def _merge_provenance(target, other) -> None:
    seen = {(p.source_id, p.segment_id, p.excerpt) for p in target.provenance}
    for p in other.provenance:
        if (p.source_id, p.segment_id, p.excerpt) not in seen:
            target.provenance.append(p)
            seen.add((p.source_id, p.segment_id, p.excerpt))


def ingest(patch: EvidenceGraph, *, rs, bundle: EvidenceBundle, origin: str, replace_ids=frozenset()) -> tuple[EvidenceGraph, dict, list[AIIssue]]:
    """-> (the patch with global ids and normalised provenance, local->global
    id map, ingress issues keyed by global id)."""

    patch = patch.model_copy(deep=True)
    known = {item_id(i): i for i in rs.graph.items()}
    known.update({k: v[0] for k, v in rs.pending_items.items()})
    replace_ids = set(replace_ids)

    # 1. Provenance.
    issues: list[AIIssue] = []
    repairs: dict[str, list[str]] = {}
    for item in patch.items():
        made, found = normalise_provenance(item, bundle)
        repairs[item_id(item)] = made
        issues += found

    # 2. Group definitions by local id.
    groups: dict[str, list] = {}
    for item in patch.items():
        groups.setdefault(item_id(item), []).append(item)

    # Entities first (assertion/fact signatures depend on entity mapping).
    mapping: dict[str, str] = {}
    used = set(known) | replace_ids

    def resolve_ref(local):
        return mapping.get(local, local)

    def allocate(local, kind):
        if local in replace_ids:
            return local
        if local and _SAFE.match(local) and local not in used:
            used.add(local)
            return local
        while True:
            rs.id_counter += 1
            candidate = f"{kind}{rs.id_counter}"
            if candidate not in used:
                used.add(candidate)
                return candidate

    kept, rejected = [], []
    for local, items in list(groups.items()):
        if len({_signature(i, lambda x: x)[0] for i in items}) > 1:
            del groups[local]
            mapping[local] = f"{local}#rejected"
            issues.append(issue("conflicting_duplicate_id", f"Id '{local}' is given to claims of different kinds; give each claim its own id.", item_id=local))
            log(rs, local, origin=origin, outcome="rejected", reason="one id used for different kinds of claim")
    for kind_order in ("e", "a", "f"):
        for local, items in groups.items():
            items_of_kind = [i for i in items if _signature(i, resolve_ref)[0] == kind_order]
            if not items_of_kind:
                continue
            signatures = {_signature(i, resolve_ref) for i in items_of_kind}
            if len(signatures) > 1:
                rejected.append(local)
                issues.append(issue("conflicting_duplicate_id", f"Id '{local}' is given to {len(items_of_kind)} different claims in one "
                                    "response; give each claim its own id.", item_id=local))
                mapping[local] = f"{local}#rejected"
                for _ in items_of_kind:
                    log(rs, local, origin=origin, outcome="rejected", reason="conflicting definitions share one id")
                continue
            primary = items_of_kind[0]
            for duplicate in items_of_kind[1:]:
                _merge_provenance(primary, duplicate)
                log(rs, local, origin=origin, outcome="collapsed", reason="identical duplicate definition in one response")
            if local in known and local not in replace_ids and _signature(known[local], lambda x: x) == _signature(primary, resolve_ref):
                mapping[local] = local
                log(rs, local, origin=origin, outcome="collapsed", reason="repeats an already accepted claim (treated as a reference)")
                continue
            global_id = allocate(local, kind_order)
            mapping[local] = global_id
            kept.append((local, global_id, primary))

    # 3. Rewrite ids and references.
    def ref(value):
        return mapping.get(value, value)

    entities, assertions, facts = [], [], []
    for local, global_id, item in kept:
        if hasattr(item, "eid"):
            item.eid = global_id
            entities.append(item)
        elif hasattr(item, "aid"):
            item.aid = global_id
            item.subject_eid, item.object_eid = ref(item.subject_eid), ref(item.object_eid)
            assertions.append(item)
        else:
            item.fid = global_id
            item.subject_id = ref(item.subject_id)
            if item.supersedes is not None and item.supersedes.target_fid:
                item.supersedes.target_fid = ref(item.supersedes.target_fid)
            facts.append(item)
        made = repairs.get(local, [])
        if made:
            log(rs, global_id, local=local, origin=origin, outcome="repaired", reason=", ".join(sorted(set(made))))
    for found in issues:
        if found.item_id in mapping:
            found.item_id = mapping[found.item_id]
    return EvidenceGraph(entities=entities, assertions=assertions, facts=facts), mapping, issues
