"""
Normalisation: overlays on the EvidenceGraph that preserve information
instead of collapsing it (C7).

EntityClusters -- mentions of what may be one entity. Two entities merge
only when a normalised name/alias is identical (a lexical transformation of
their own claims), they share specificity, their type labels are compatible,
and no distinguishing fact disagrees. The same label claimed for things whose
kinds map to *different* catalogue types (the stage "Final" and the final
match) is a homonym: recorded, never merged, never asked about. Anything
else less certain becomes a `possible_same_as` pair for a coreference
question -- OnyxJar never merges non-identical mentions on its own (I2).
Members keep their own provenance.

ObservationSets -- observations of one property of one subject (by
normalised label here; re-run per mapped attribute in mapping.py). Two
differing values are only a conflict when nothing separates them:

    corroborated        values equal (after deterministic normalisation)
    superseded          an observation explicitly corrects another
    distinct            differing values separated by qualifiers (time
                        window, context/condition, unit, modality)
    candidate_conflict  differing values, nothing separating them -- an
                        Adjudication question that may only answer
                        contradictory / distinct, never pick a winner
    conflict            adjudicated contradictory: never used for mutation
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from itertools import combinations

from ai.services.evidence_bundle import normalize_for_matching
from ai.services.evidence_graph import EvidenceGraph
from ai.services.reconcile import questions as q
from ai.services.reconcile.ledger import NORMALISE, Ledger
from ai.services.semantic.index import normalize_name


def singular(label) -> str:
    """Deterministic label normalisation: case/punctuation-insensitive and
    plural-insensitive ("Venues" == "venue", "matches" == "match")."""

    words = normalize_name(label).split()
    if not words:
        return ""
    last = words[-1]
    if len(last) > 4 and last.endswith("ies"):
        last = last[:-3] + "y"
    elif len(last) > 4 and last.endswith(("ches", "shes", "sses", "xes", "zes")):
        last = last[:-2]
    elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    return " ".join([*words[:-1], last])


_NUMBER = re.compile(r"^[+-]?(\d[\d,_\s]*)(\.\d+)?$")


def normalize_value(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    compact = text.replace(" ", " ")
    if _NUMBER.match(compact):
        try:
            number = float(re.sub(r"[,_\s]", "", compact))
            return f"n:{number:g}"
        except ValueError:
            pass
    lowered = text.casefold()
    if lowered in ("true", "yes"):
        return "b:true"
    if lowered in ("false", "no"):
        return "b:false"
    return "t:" + normalize_for_matching(text)


# -- clusters ----------------------------------------------------------------


@dataclass
class Cluster:
    cluster_id: str
    member_eids: list[str]
    name: str
    aliases: list[str]
    type_labels: list[str]
    type_hints: list[str]
    specificity: str
    polarity: str  # present | removed | mixed
    provenance: list = field(default_factory=list)

    def names(self) -> set[str]:
        return {n for n in (normalize_name(v) for v in (self.name, *self.aliases)) if n}


@dataclass
class ClusterResult:
    clusters: dict[str, Cluster]
    by_eid: dict[str, str]
    # (eid_a, eid_b) mention pairs that may be one entity and need a coreference answer.
    possible_same_as: list[tuple[str, str]]

    def cluster_of(self, eid) -> Cluster | None:
        cid = self.by_eid.get(eid)
        return self.clusters.get(cid) if cid else None


def _type_compatible(a, b) -> bool:
    if a.type_hint and b.type_hint:
        return a.type_hint == b.type_hint
    labels_a = {singular(a.type_label), *( [singular(a.type_hint)] if a.type_hint else [])}
    labels_b = {singular(b.type_label), *( [singular(b.type_hint)] if b.type_hint else [])}
    return bool(labels_a & labels_b)


def _names(entity) -> set[str]:
    return {n for n in (normalize_name(v) for v in (entity.name, *entity.aliases)) if n}


def _unqualified_facts(graph, eid) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    for fact in graph.facts:
        if fact.subject_id != eid:
            continue
        qualifiers = fact.qualifiers
        if any((qualifiers.as_of, qualifiers.valid_from, qualifiers.valid_to, qualifiers.context)):
            continue
        facts.setdefault(singular(fact.label), set()).add(normalize_value(fact.value))
    return facts


def _facts_disagree(a, b) -> bool:
    return any(len(values | b[label]) > 1 for label, values in a.items() if label in b)


def build_clusters(graph: EvidenceGraph, *, pins: dict, ledger: Ledger, kind_of=None) -> ClusterResult:
    """`kind_of(entity)` -> the catalogue type id the entity's own hint/label
    lexically names, or None (used only to recognise homonyms)."""

    entities = list(graph.entities)
    parent = {e.eid: e.eid for e in entities}

    def find(eid):
        while parent[eid] != eid:
            parent[eid] = parent[parent[eid]]
            eid = parent[eid]
        return eid

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            # The earlier mention's id names the cluster (stable ids).
            first, second = sorted((root_a, root_b), key=lambda e: order[e])
            parent[second] = first

    order = {e.eid: position for position, e in enumerate(entities)}
    facts = {e.eid: _unqualified_facts(graph, e.eid) for e in entities}
    merges: dict[tuple, str] = {}
    possible = []
    for a, b in combinations(entities, 2):
        if not (_names(a) & _names(b)):
            continue
        pair_key = q.key("coreference", a.eid, b.eid)
        lexical = a.specificity == b.specificity and _type_compatible(a, b) and not _facts_disagree(facts[a.eid], facts[b.eid])
        pin = pins.get(pair_key)
        if pin is not None:
            if pin.option_id == "same":
                union(a.eid, b.eid)
                merges[(a.eid, b.eid)] = "adjudicated"
            continue
        kind_a, kind_b = (kind_of(a), kind_of(b)) if kind_of else (None, None)
        if kind_a and kind_b and kind_a != kind_b:
            ledger.structural(
                f"homonym:{a.eid}:{b.eid}", step=NORMALISE, basis="lexical", subject_ids=[a.eid, b.eid], inputs=[a.eid, b.eid],
                outcome="distinct_kinds", detail={"name": a.name, "type_labels": [a.type_label, b.type_label]},
            )
        elif lexical:
            union(a.eid, b.eid)
            merges[(a.eid, b.eid)] = "lexical"
        else:
            possible.append((a.eid, b.eid))

    grouped: dict[str, list] = {}
    for entity in entities:
        grouped.setdefault(find(entity.eid), []).append(entity)

    clusters, by_eid = {}, {}
    for cid, members in grouped.items():
        polarities = {m.polarity for m in members}
        aliases = []
        for member in members:
            for value in (member.name, *member.aliases):
                if value not in aliases and value != members[0].name:
                    aliases.append(value)
        cluster = Cluster(
            cluster_id=cid,
            member_eids=[m.eid for m in members],
            name=members[0].name,
            aliases=aliases,
            type_labels=sorted({m.type_label for m in members}),
            type_hints=sorted({m.type_hint for m in members if m.type_hint}),
            specificity=members[0].specificity,
            polarity=polarities.pop() if len(polarities) == 1 else "mixed",
            provenance=[p for m in members for p in m.provenance],
        )
        clusters[cid] = cluster
        for member in members:
            by_eid[member.eid] = cid
        if len(members) > 1:
            bases = {basis for (x, y), basis in merges.items() if find(x) == cid}
            inputs = [m.eid for m in members]
            for (x, y), basis in merges.items():
                if basis == "adjudicated" and find(x) == cid:
                    inputs += q.pin_inputs(q.key("coreference", x, y), pins)
            ledger.structural(
                f"cluster:{cid}", step=NORMALISE, basis="adjudicated" if "adjudicated" in bases else "lexical",
                subject_ids=[m.eid for m in members], inputs=inputs, outcome="merged",
                detail={"names": [m.name for m in members]},
            )

    # A pair already merged transitively needs no question.
    possible = [(a, b) for a, b in possible if find(a) != find(b)]
    return ClusterResult(clusters=clusters, by_eid=by_eid, possible_same_as=possible)


# -- observation sets -----------------------------------------------------------


@dataclass
class Observation:
    fid: str
    subject: str  # cluster id or aid
    label: str
    value: str
    norm_value: str
    qualifier_key: tuple
    modality: str
    valid_to: str | None
    supersedes_target: str | None
    supersedes: bool
    provenance: list


@dataclass
class ObservationSet:
    set_key: str  # "<subject>:<property>"
    subject: str
    prop: str
    level: str  # label | attribute
    observations: list[Observation]
    classification: str = "corroborated"
    superseded: set = field(default_factory=set)
    flags: list = field(default_factory=list)

    @property
    def fids(self) -> list[str]:
        return [o.fid for o in self.observations]

    def remaining(self) -> list[Observation]:
        return [o for o in self.observations if o.fid not in self.superseded]


def observation(fact, subject) -> Observation:
    qualifiers = fact.qualifiers
    return Observation(
        fid=fact.fid,
        subject=subject,
        label=fact.label,
        value=fact.value,
        norm_value=normalize_value(fact.value),
        qualifier_key=(
            (qualifiers.as_of or "").strip(), (qualifiers.valid_from or "").strip(), (qualifiers.valid_to or "").strip(),
            normalize_for_matching(qualifiers.context or ""), normalize_for_matching(fact.unit or ""), fact.modality,
        ),
        modality=fact.modality,
        valid_to=qualifiers.valid_to,
        supersedes_target=fact.supersedes.target_fid if fact.supersedes else None,
        supersedes=fact.supersedes is not None,
        provenance=list(fact.provenance),
    )


def classify(obs_set: ObservationSet, *, pins: dict) -> ObservationSet:
    fids = set(obs_set.fids)
    superseded = set()
    for item in obs_set.observations:
        if not item.supersedes:
            continue
        if item.supersedes_target and item.supersedes_target in fids:
            superseded.add(item.supersedes_target)
        elif not item.supersedes_target:
            superseded |= {o.fid for o in obs_set.observations if o is not item and o.norm_value != item.norm_value}
    obs_set.superseded = superseded
    remaining = obs_set.remaining()

    if len({o.norm_value for o in remaining}) <= 1:
        obs_set.classification = "superseded" if superseded else "corroborated"
        return obs_set

    differing = [(a, b) for a, b in combinations(remaining, 2) if a.norm_value != b.norm_value]
    if all(a.qualifier_key != b.qualifier_key for a, b in differing):
        obs_set.classification = "distinct"
        return obs_set

    pin = pins.get(q.key("conflict_classification", obs_set.set_key))
    if pin is None:
        obs_set.classification = "candidate_conflict"
    elif pin.option_id == "contradictory":
        obs_set.classification = "conflict"
    elif pin.option_id == "distinct":
        obs_set.classification = "distinct"
    else:
        obs_set.classification = "candidate_conflict"
        obs_set.flags.append("unresolved_ambiguity")
    return obs_set


def current_observation(obs_set: ObservationSet, *, pins: dict):
    """
    -> ("set", Observation) | ("not_set", None) | ("conflict", None) |
       ("question", kind). Deterministic only when exactly one observation is
    current: everything agrees, one explicitly supersedes the rest, or exactly
    one `stated` observation has no end. Otherwise it is a question.
    """

    remaining = obs_set.remaining()
    if obs_set.classification in ("corroborated", "superseded"):
        return ("set", remaining[0]) if remaining else ("not_set", None)
    if obs_set.classification == "conflict":
        return "conflict", None
    if obs_set.classification == "candidate_conflict":
        if "unresolved_ambiguity" in obs_set.flags:
            return "not_set", None
        return "question", "conflict_classification"
    current = [o for o in remaining if o.modality == "stated" and not o.valid_to]
    if current and len({o.norm_value for o in current}) == 1:
        return "set", current[0]
    pin = pins.get(q.key("value_selection", obs_set.set_key))
    if pin is None:
        return "question", "value_selection"
    chosen = next((o for o in remaining if o.fid == pin.option_id), None)
    return ("set", chosen) if chosen else ("not_set", None)


def label_observation_sets(graph: EvidenceGraph, clusters: ClusterResult, *, pins: dict, ledger: Ledger) -> list[ObservationSet]:
    """Evidence-label level sets (C7 level 1) -- recorded in the ledger for
    findings and Verification; mutation uses the attribute level (mapping.py)."""

    grouped: dict[tuple, list[Observation]] = {}
    for fact in graph.facts:
        subject = clusters.by_eid.get(fact.subject_id, fact.subject_id)
        grouped.setdefault((subject, singular(fact.label)), []).append(observation(fact, subject))
    sets = []
    for (subject, prop), observations in grouped.items():
        obs_set = classify(ObservationSet(set_key=f"{subject}:{prop}", subject=subject, prop=prop, level="label", observations=observations), pins=pins)
        sets.append(obs_set)
        if len(observations) > 1:
            record_observation_set(ledger, obs_set, pins=pins)
    return sets


def record_observation_set(ledger: Ledger, obs_set: ObservationSet, *, pins: dict) -> None:
    inputs = list(obs_set.fids)
    for kind in ("conflict_classification", "value_selection"):
        inputs.extend(q.pin_inputs(q.key(kind, obs_set.set_key), pins))
    ledger.structural(
        f"obs:{obs_set.level}:{obs_set.set_key}", step=NORMALISE, basis="deterministic",
        subject_ids=obs_set.fids, inputs=inputs, outcome=obs_set.classification,
        detail={"property": obs_set.prop, "values": [o.value for o in obs_set.observations], "superseded": sorted(obs_set.superseded)},
        flags=list(obs_set.flags),
        question_key=q.key("conflict_classification", obs_set.set_key),
    )
