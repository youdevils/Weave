"""
Ontology mapping (C2/C3): OnyxJar computes structural options and accepts
explicit claims. It never chooses a meaning.

For each entity cluster, assertion and fact, OnyxJar computes what the
catalogue *could* represent it as -- candidate ObjectTypes, every
(RelationshipType, orientation) legal for the endpoints' types, every
compatible attribute -- and then accepts a mapping only on an explicit basis:

    lexical      the claim's own label/predicate equals exactly one catalogue
                 name/key after deterministic normalisation
    hint         the extractor's hint (and, for relationships, its stated
                 orientation) is one of the legal options
                 (lexical acceptance of a relationship also requires the
                 predicate's words to appear in the assertion's own cited
                 evidence -- a predicate the source never uses is a hint at
                 most, never a lexical match)
    adjudicated  an Adjudication answer (or Gap Probe remap / Verification
                 objection) pinned one of the options
    reading      a Reading-derived claim (ai.services.reconcile.readings): its
                 Reading slot already selected the catalogue identity, so it
                 is taken as decided -- never re-interpreted lexically, by
                 hint or by a question; only its legality is checked

Anything else with options is `ambiguous` (a question); with none, it is
`indirect` (a rule path exists through another type) or `unmapped`. OnyxJar
never reorients a predicate: a hint legal only in the converse orientation
without an explicit `converse` claim stays ambiguous. A rule whose subject
and object types are the same can't be oriented by types at all, so its
acceptance is flagged `orientation_unverifiable` for Verification.

`indirect` keeps three layers in its ledger decision -- what the source says,
how it maps (the path), and why it isn't directly compilable:

    intermediate_unidentified  the source refers to the intermediate only
                               non-specifically (a `generic` entity, or an
                               adjudicated "refers to intermediate")
    no_direct_representation   the source states a direct relationship the
                               ontology can only express through a path the
                               source never asserts (adjudicated)
    indirect_unclassified      no claim distinguishes the two. Never asked:
                               no answer changes scope, viability or what
                               compiles (an indirect mapping fills no
                               requirement either way); a reviewer's
                               `indirect_classification` answer is honoured
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.conf import settings

from ai.services.evidence_graph import EvidenceGraph
from ai.services.reconcile import questions as q
from ai.services.reconcile.ledger import MAPPING, Ledger
from ai.services.reconcile.normalise import (
    ClusterResult,
    ObservationSet,
    classify,
    observation,
    record_observation_set,
    singular,
)
from ai.services.semantic.index import SemanticModelIndex, normalize_name
from ai.services.sources import mentions, tokens
from model.services.keys import slugify_key

AS_STATED, CONVERSE = "as_stated", "converse"


@dataclass
class TypeMapping:
    cluster_id: str
    outcome: str  # mapped | ambiguous | unmapped | unresolved_ambiguity
    type_id: str | None = None
    basis: str = ""
    options: list = field(default_factory=list)  # ObjectType keys
    reason: str | None = None
    decision_id: str = ""


@dataclass
class AssertionMapping:
    aid: str
    subject_cid: str
    object_cid: str
    outcome: str  # mapped | ambiguous | indirect | unmapped | pending | unresolved_ambiguity
    relationship_type_id: str | None = None
    orientation: str = AS_STATED
    basis: str = ""
    options: list = field(default_factory=list)  # "rel_key:orientation"
    paths: list = field(default_factory=list)
    reason: str | None = None
    flags: list = field(default_factory=list)
    decision_id: str = ""
    pattern_key: str | None = None

    @property
    def canonical_subject(self) -> str:
        return self.subject_cid if self.orientation == AS_STATED else self.object_cid

    @property
    def canonical_object(self) -> str:
        return self.object_cid if self.orientation == AS_STATED else self.subject_cid


@dataclass
class FactMapping:
    fid: str
    owner: str  # cluster id or aid
    owner_kind: str  # object | relationship
    outcome: str  # mapped | ambiguous | unmapped | pending | unresolved_ambiguity
    attribute_key: str | None = None
    basis: str = ""
    options: list = field(default_factory=list)
    reason: str | None = None
    decision_id: str = ""


@dataclass
class MappingResult:
    types: dict[str, TypeMapping]
    assertions: dict[str, AssertionMapping]
    facts: dict[str, FactMapping]
    attribute_sets: dict[tuple, ObservationSet]  # (owner, attribute key) -> set


def option_id(index: SemanticModelIndex, relationship_type_id, orientation) -> str:
    return f"{index.relationship_types[relationship_type_id].key}:{orientation}"


def parse_option(index: SemanticModelIndex, value):
    """'played_at:converse' -> (relationship_type_id, orientation) or None."""

    key, _, orientation = str(value or "").partition(":")
    item = index.relationship_type_by_key(key)
    if item is None or orientation not in (AS_STATED, CONVERSE):
        return None
    return item.id, orientation


# -- entity types -------------------------------------------------------------


def _label_matches(index: SemanticModelIndex, label) -> list:
    wanted = singular(label)
    slug = slugify_key(label)
    return [
        t for t in index.object_types.values()
        if wanted and (singular(t.name) == wanted or singular(t.key.replace("_", " ")) == wanted or t.key == slug)
    ]


def _similar_types(index: SemanticModelIndex, labels) -> list:
    words = {w for label in labels for w in singular(label).split()}
    found = []
    for item in index.object_types.values():
        type_words = set(singular(item.name).split()) | set(singular(item.key.replace("_", " ")).split())
        if words & type_words:
            found.append(item)
    return found


def map_entity_types(clusters: ClusterResult, *, index: SemanticModelIndex, pins: dict, ledger: Ledger, reading_types=None) -> dict[str, TypeMapping]:
    """`reading_types` (eid -> (type id, [read: decisions])): the catalogue
    types Reading slots selected for Reading-derived entities."""

    result = {}
    limit = settings.AI_MAPPING_MAX_OPTIONS
    reading_types = reading_types or {}
    for cid, cluster in clusters.clusters.items():
        pin_key = q.key("entity_type", cid)
        inputs = [*cluster.member_eids, *q.pin_inputs(pin_key, pins)]
        mapping = TypeMapping(cluster_id=cid, outcome="unmapped")
        pin = pins.get(pin_key)
        valid_hints = sorted({h for h in cluster.type_hints if index.object_type_by_key(h)})
        lexical = {t.key for label in cluster.type_labels for t in _label_matches(index, label)}
        read = [reading_types[e] for e in cluster.member_eids if e in reading_types]
        read_types = sorted({type_id for type_id, _ in read})
        inputs += [d for _, decisions in read for d in decisions if d not in inputs]

        if pin is None and len(read_types) == 1:
            mapping = TypeMapping(cid, "mapped", read_types[0], "reading")
        elif pin is None and len(read_types) > 1:
            mapping = TypeMapping(cid, "ambiguous", options=sorted(index.object_types[t].key for t in read_types)[:limit])
        elif pin is not None:
            item = index.object_type_by_key(pin.option_id)
            if item is not None:
                mapping = TypeMapping(cid, "mapped", item.id, "adjudicated")
            elif pin.option_id == q.NONE:
                mapping = TypeMapping(cid, "unmapped", basis="adjudicated", reason="no_semantic_match")
            else:
                options = valid_hints or sorted(lexical) or [t.key for t in _similar_types(index, cluster.type_labels)][:limit]
                mapping = TypeMapping(cid, "unresolved_ambiguity", basis=pin.basis, options=options)
        elif len(valid_hints) == 1 and len(cluster.type_hints) == 1:
            mapping = TypeMapping(cid, "mapped", index.object_type_by_key(valid_hints[0]).id, "hint")
        elif len(valid_hints) > 1:
            mapping = TypeMapping(cid, "ambiguous", options=valid_hints[:limit])
        elif len(lexical) == 1:
            mapping = TypeMapping(cid, "mapped", index.object_type_by_key(next(iter(lexical))).id, "lexical")
        else:
            options = sorted(lexical) or [t.key for t in _similar_types(index, [*cluster.type_labels, *cluster.type_hints])]
            if not options and len(index.object_types) <= limit:
                options = sorted(t.key for t in index.object_types.values() if t.is_active)
            if options:
                mapping = TypeMapping(cid, "ambiguous", options=options[:limit])
            else:
                mapping = TypeMapping(cid, "unmapped", reason="no_structure")

        if mapping.outcome == "mapped" and not index.object_types[mapping.type_id].is_active:
            mapping = TypeMapping(cid, "unmapped", basis=mapping.basis, reason="inactive_type", options=[index.object_types[mapping.type_id].key])

        mapping.decision_id = f"type:{cid}"
        ledger.structural(
            mapping.decision_id, step=MAPPING, basis=mapping.basis or "deterministic", subject_ids=[cid], inputs=inputs,
            outcome=mapping.outcome, reason=mapping.reason,
            options=[{"option_id": o} for o in mapping.options],
            source={"name": cluster.name, "type_labels": cluster.type_labels, "type_hints": cluster.type_hints},
            mapping={"type_key": index.object_types[mapping.type_id].key} if mapping.type_id else None,
            flags=["unresolved_ambiguity"] if mapping.outcome == "unresolved_ambiguity" else [],
            question_key=pin_key,
        )
        result[cid] = mapping
    return result


# -- assertions -------------------------------------------------------------------


def direct_options(index: SemanticModelIndex, subject_type, object_type) -> list[tuple[str, str]]:
    """Every (RelationshipType, orientation) a rule allows between these
    endpoint types. Same-type rules yield both orientations: types alone
    can't tell them apart."""

    options = []
    for relationship_type in index.relationship_types.values():
        if not relationship_type.is_active:
            continue
        if index.rule(relationship_type.id, subject_type, object_type) is not None:
            options.append((relationship_type.id, AS_STATED))
        if index.rule(relationship_type.id, object_type, subject_type) is not None:
            options.append((relationship_type.id, CONVERSE))
    return list(dict.fromkeys(options))


def one_hop_paths(index: SemanticModelIndex, subject_type, object_type) -> list[dict]:
    """Paths subject -r1- middle -r2- object (either orientation per hop)."""

    def touching(type_a, type_b):
        found = []
        for rule in index.rules.values():
            if (rule.subject_type_id, rule.object_type_id) in ((type_a, type_b), (type_b, type_a)):
                found.append(rule)
        return found

    paths = []
    for middle in index.object_types:
        if middle in (subject_type, object_type):
            continue
        for first in touching(subject_type, middle):
            for second in touching(middle, object_type):
                paths.append(
                    {
                        "via_type": index.object_types[middle].key,
                        "via_type_id": middle,
                        "hops": [
                            {"relationship_type_key": index.relationship_types[first.relationship_type_id].key,
                             "subject_type_key": index.object_types[first.subject_type_id].key,
                             "object_type_key": index.object_types[first.object_type_id].key},
                            {"relationship_type_key": index.relationship_types[second.relationship_type_id].key,
                             "subject_type_key": index.object_types[second.subject_type_id].key,
                             "object_type_key": index.object_types[second.object_type_id].key},
                        ],
                    }
                )
    return paths[: settings.AI_MAPPING_MAX_OPTIONS]


def _lexical_relationship(index, predicate, options, evidence_texts=None) -> list:
    wanted, slug = singular(predicate), slugify_key(predicate)
    if evidence_texts is not None and not any(mentions(text, [predicate]) for text in evidence_texts):
        return []
    return [
        (rt, orientation) for rt, orientation in options
        if orientation == AS_STATED
        and (singular(index.relationship_types[rt].name) == wanted or index.relationship_types[rt].key == slug
             or singular(index.relationship_types[rt].key.replace("_", " ")) == wanted)
    ]


def _generic_intermediates(graph, clusters, types, assertion, via_type_ids) -> list[str]:
    """Generic entities of a path's intermediate type that the source links to
    either endpoint, or that share the assertion's own excerpt -- the source
    itself referring to the intermediate non-specifically."""

    endpoints = {clusters.by_eid.get(assertion.subject_eid), clusters.by_eid.get(assertion.object_eid)}
    excerpts = {normalize_name(p.excerpt) for p in assertion.provenance}
    found = []
    for cid, cluster in clusters.clusters.items():
        if cluster.specificity != "generic" or types[cid].type_id not in via_type_ids:
            continue
        linked = any(
            {clusters.by_eid.get(other.subject_eid), clusters.by_eid.get(other.object_eid)} >= {cid} and
            ({clusters.by_eid.get(other.subject_eid), clusters.by_eid.get(other.object_eid)} & endpoints)
            for other in graph.assertions
        )
        shared = any(
            normalize_name(p.excerpt) in excerpt or excerpt in normalize_name(p.excerpt)
            for p in cluster.provenance for excerpt in excerpts if excerpt
        )
        if linked or shared:
            found.extend(cluster.member_eids)
    return found


def predicate_pattern_key(assertion, subject_type_key, object_type_key) -> str:
    """One Adjudication answer about what a predicate *means* between two kinds
    ("played at" between match and venue) applies to every assertion with the
    same wording and kinds -- typical of table rows."""

    return q.key("predicate_mapping", "_".join(tokens(assertion.predicate)) or "-", subject_type_key, object_type_key)


def _reading_mapping(assertion, subject_cid, object_cid, subject_type, object_type, read, *, clusters, index, ledger) -> AssertionMapping:
    """A Reading-derived assertion: its Reading slot already chose the
    relationship and orientation. Only legality is OnyxJar's to check."""

    relationship_type_id, orientation, decisions = read
    inputs = [assertion.aid, subject_type.decision_id, object_type.decision_id, *decisions]
    mapping = AssertionMapping(assertion.aid, subject_cid, object_cid, "unmapped")
    layer = None
    generic = "generic" in (clusters.clusters[subject_cid].specificity, clusters.clusters[object_cid].specificity)
    if subject_type.outcome != "mapped" or object_type.outcome != "mapped":
        mapping.outcome = "pending" if {subject_type.outcome, object_type.outcome} & {"ambiguous"} else "unmapped"
        mapping.reason = None if mapping.outcome == "pending" else "endpoint_unmapped"
    elif (relationship_type_id, orientation) not in direct_options(index, subject_type.type_id, object_type.type_id):
        mapping.reason, mapping.basis = "reading_illegal", "reading"
    else:
        mapping.relationship_type_id, mapping.orientation, mapping.basis = relationship_type_id, orientation, "reading"
        layer = {"option": option_id(index, relationship_type_id, orientation)}
        if generic:
            mapping.outcome, mapping.reason = "indirect", "intermediate_unidentified"
            layer["note"] = "an endpoint is referred to only non-specifically"
        else:
            mapping.outcome = "mapped"
            if subject_type.type_id == object_type.type_id:
                mapping.flags.append("orientation_unverifiable")
    mapping.decision_id = f"map:{assertion.aid}"
    ledger.structural(
        mapping.decision_id, step=MAPPING, basis=mapping.basis or "deterministic", subject_ids=[assertion.aid], inputs=inputs,
        outcome=mapping.outcome, reason=mapping.reason,
        source={"aid": assertion.aid, "predicate": assertion.predicate, "subject": clusters.clusters[subject_cid].name,
                "object": clusters.clusters[object_cid].name, "excerpts": [p.excerpt for p in assertion.provenance]},
        mapping=layer, flags=list(mapping.flags),
    )
    return mapping


def map_assertions(graph: EvidenceGraph, clusters: ClusterResult, types: dict, *, index: SemanticModelIndex, pins: dict, ledger: Ledger, evidence_texts=None,
                   reading_relations=None) -> dict[str, AssertionMapping]:
    """`evidence_texts(assertion)` -> the texts its provenance cites (for the
    lexical-evidence check); None skips that check. `reading_relations`
    (aid -> (relationship type id, orientation, [read: decisions])): what
    Reading slots selected for Reading-derived assertions -- they bypass the
    pin / hint / lexical / question path entirely."""

    result = {}
    reading_relations = reading_relations or {}
    for assertion in graph.assertions:
        subject_cid = clusters.by_eid.get(assertion.subject_eid)
        object_cid = clusters.by_eid.get(assertion.object_eid)
        if subject_cid is None or object_cid is None:
            continue
        subject_type, object_type = types[subject_cid], types[object_cid]
        if assertion.aid in reading_relations:
            result[assertion.aid] = _reading_mapping(assertion, subject_cid, object_cid, subject_type, object_type,
                                                     reading_relations[assertion.aid], clusters=clusters, index=index, ledger=ledger)
            continue
        pin_key = q.key("assertion_mapping", assertion.aid)
        indirect_key = q.key("indirect_classification", assertion.aid)
        pattern_key = None
        if subject_type.outcome == "mapped" and object_type.outcome == "mapped":
            pattern_key = predicate_pattern_key(
                assertion, index.object_types[subject_type.type_id].key, index.object_types[object_type.type_id].key
            )
            if pin_key not in pins and pattern_key in pins:
                pin_key = pattern_key
        inputs = [assertion.aid, subject_type.decision_id, object_type.decision_id, *q.pin_inputs(pin_key, pins), *q.pin_inputs(indirect_key, pins)]
        mapping = AssertionMapping(assertion.aid, subject_cid, object_cid, "unmapped")
        generic = "generic" in (clusters.clusters[subject_cid].specificity, clusters.clusters[object_cid].specificity)
        source = {
            "aid": assertion.aid, "predicate": assertion.predicate,
            "subject": clusters.clusters[subject_cid].name, "object": clusters.clusters[object_cid].name,
            "excerpts": [p.excerpt for p in assertion.provenance],
        }
        layer = None

        if subject_type.outcome != "mapped" or object_type.outcome != "mapped":
            unresolved = {subject_type.outcome, object_type.outcome} & {"ambiguous"}
            mapping.outcome = "pending" if unresolved else "unmapped"
            mapping.reason = None if unresolved else "endpoint_unmapped"
        else:
            options = direct_options(index, subject_type.type_id, object_type.type_id)
            mapping.options = [option_id(index, rt, o) for rt, o in options]
            accepted, basis = None, ""
            pin = pins.get(pin_key)
            if pin is not None:
                parsed = parse_option(index, pin.option_id)
                if parsed in options:
                    accepted, basis = parsed, "adjudicated"
                elif pin.option_id == q.NONE:
                    mapping.outcome, mapping.reason, mapping.basis = "unmapped", "no_semantic_match", "adjudicated"
                else:
                    mapping.outcome, mapping.basis = "unresolved_ambiguity", pin.basis
                    mapping.flags.append("unresolved_ambiguity")
            if accepted is None and pin is None and assertion.relationship_type_hint:
                hinted = index.relationship_type_by_key(assertion.relationship_type_hint)
                if hinted is not None and (hinted.id, assertion.hint_orientation) in options:
                    accepted, basis = (hinted.id, assertion.hint_orientation), "hint"
            if accepted is None and pin is None:
                lexical = _lexical_relationship(
                    index, assertion.predicate, options, evidence_texts(assertion) if evidence_texts else None
                )
                if len(lexical) == 1:
                    accepted, basis = lexical[0], "lexical"

            if mapping.outcome in ("unmapped", "unresolved_ambiguity") and mapping.basis:
                pass  # settled by the pin above
            elif generic and (options or accepted):
                mapping.outcome, mapping.reason = "indirect", "intermediate_unidentified"
                if accepted:
                    mapping.relationship_type_id, mapping.orientation, mapping.basis = accepted[0], accepted[1], basis
                layer = {"option": option_id(index, *accepted)} if accepted else {"options": mapping.options}
                layer["note"] = "an endpoint is referred to only non-specifically"
            elif accepted is not None:
                mapping.outcome, mapping.basis = "mapped", basis
                mapping.relationship_type_id, mapping.orientation = accepted
                if subject_type.type_id == object_type.type_id:
                    mapping.flags.append("orientation_unverifiable")
                layer = {"option": option_id(index, *accepted)}
            elif options:
                mapping.outcome = "ambiguous"
            else:
                paths = one_hop_paths(index, subject_type.type_id, object_type.type_id)
                if paths:
                    mapping.outcome, mapping.paths = "indirect", paths
                    layer = {"paths": [{k: v for k, v in p.items() if k != "via_type_id"} for p in paths]}
                    indirect_pin = pins.get(indirect_key)
                    generics = _generic_intermediates(graph, clusters, types, assertion, {p["via_type_id"] for p in paths})
                    if indirect_pin is not None:
                        mapping.basis = "adjudicated"
                        mapping.reason = {
                            "refers_to_intermediate": "intermediate_unidentified",
                            "direct_statement": "no_direct_representation",
                        }.get(indirect_pin.option_id, "indirect_unclassified")
                        if mapping.reason == "indirect_unclassified":
                            mapping.flags.append("unresolved_ambiguity")
                    elif generics:
                        mapping.basis, mapping.reason = "extraction", "intermediate_unidentified"
                        inputs.extend(generics)
                    else:
                        mapping.reason = "indirect_unclassified"
                else:
                    mapping.reason = "no_structure"

        mapping.decision_id = f"map:{assertion.aid}"
        mapping.pattern_key = pattern_key
        ledger.structural(
            mapping.decision_id, step=MAPPING, basis=mapping.basis or "deterministic", subject_ids=[assertion.aid],
            inputs=inputs, outcome=mapping.outcome, reason=mapping.reason,
            options=[{"option_id": o} for o in mapping.options], source=source, mapping=layer,
            flags=list(mapping.flags),
            question_key=indirect_key if mapping.outcome == "indirect" else q.key("assertion_mapping", assertion.aid),
        )
        result[assertion.aid] = mapping
    return result


# -- facts ----------------------------------------------------------------------

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def value_compatible(value, attribute) -> bool:
    text = str(value or "").strip()
    data_type = attribute.data_type
    if data_type == "number":
        return typed_value(text, attribute) is not None
    if data_type == "boolean":
        return text.casefold() in ("true", "false", "yes", "no")
    if data_type in ("date", "datetime"):
        return bool(_DATE.match(text))
    if data_type == "url":
        return text.startswith(("http://", "https://"))
    if data_type == "choice":
        return any(normalize_name(choice) == normalize_name(text) for choice in attribute.choices)
    return bool(text)


def typed_value(value, attribute):
    """The stored value for `attribute` -- a deterministic transformation of the
    extracted value, or None when it isn't representable."""

    text = str(value or "").strip()
    if attribute.data_type == "number":
        compact = re.sub(r"[,_\s ]", "", text)
        try:
            number = float(compact)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    if attribute.data_type == "boolean":
        lowered = text.casefold()
        return True if lowered in ("true", "yes") else False if lowered in ("false", "no") else None
    if attribute.data_type == "choice":
        return next((choice for choice in attribute.choices if normalize_name(choice) == normalize_name(text)), None)
    return text if value_compatible(text, attribute) else None


def map_facts(graph: EvidenceGraph, clusters: ClusterResult, types: dict, assertions: dict, *, index: SemanticModelIndex, pins: dict, ledger: Ledger) -> tuple[dict, dict]:
    result = {}
    limit = settings.AI_MAPPING_MAX_OPTIONS
    for fact in graph.facts:
        if fact.subject_id in clusters.by_eid:
            owner = clusters.by_eid[fact.subject_id]
            owner_kind = "object"
            owner_mapping = types[owner]
            owner_type_id = owner_mapping.type_id if owner_mapping.outcome == "mapped" else None
            owner_pending = owner_mapping.outcome == "ambiguous"
        elif fact.subject_id in assertions:
            owner = fact.subject_id
            owner_kind = "relationship"
            owner_mapping = assertions[owner]
            owner_type_id = owner_mapping.relationship_type_id if owner_mapping.outcome == "mapped" else None
            owner_pending = owner_mapping.outcome in ("ambiguous", "pending")
        else:
            continue

        pin_key = q.key("fact_attribute", fact.fid)
        inputs = [fact.fid, owner_mapping.decision_id, *q.pin_inputs(pin_key, pins)]
        mapping = FactMapping(fact.fid, owner, owner_kind, "unmapped")
        if owner_type_id is None:
            mapping.outcome = "pending" if owner_pending else "unmapped"
            mapping.reason = None if owner_pending else "owner_unmapped"
        else:
            attributes = [a for a in index.attributes_of(owner_type_id) if a.is_active]
            compatible = [a for a in attributes if value_compatible(fact.value, a)]
            mapping.options = [a.key for a in compatible][:limit]
            pin = pins.get(pin_key)
            lexical = [
                a for a in compatible
                if singular(a.name) == singular(fact.label) or a.key == slugify_key(fact.label)
            ]
            if pin is not None:
                chosen = next((a for a in compatible if a.key == pin.option_id), None)
                if chosen is not None:
                    mapping.outcome, mapping.attribute_key, mapping.basis = "mapped", chosen.key, "adjudicated"
                elif pin.option_id == q.NONE:
                    mapping.outcome, mapping.reason, mapping.basis = "unmapped", "no_semantic_match", "adjudicated"
                else:
                    mapping.outcome, mapping.basis = "unresolved_ambiguity", pin.basis
            elif len(lexical) == 1:
                mapping.outcome, mapping.attribute_key, mapping.basis = "mapped", lexical[0].key, "lexical"
            elif compatible:
                mapping.outcome = "ambiguous"
            else:
                same_name = any(singular(a.name) == singular(fact.label) for a in attributes)
                mapping.reason = "value_incompatible" if same_name else "no_compatible_attribute"

        mapping.decision_id = f"fact:{fact.fid}"
        ledger.structural(
            mapping.decision_id, step=MAPPING, basis=mapping.basis or "deterministic", subject_ids=[fact.fid],
            inputs=inputs, outcome=mapping.outcome, reason=mapping.reason,
            options=[{"option_id": o} for o in mapping.options],
            source={"label": fact.label, "value": fact.value, "excerpts": [p.excerpt for p in fact.provenance]},
            mapping={"attribute_key": mapping.attribute_key} if mapping.attribute_key else None,
            flags=["unresolved_ambiguity"] if mapping.outcome == "unresolved_ambiguity" else [],
            question_key=pin_key,
        )
        result[fact.fid] = mapping

    # Attribute-level observation sets (C7 level 2): differently labelled
    # facts that mapped onto the same attribute are compared too.
    grouped: dict[tuple, list] = {}
    for fact in graph.facts:
        mapping = result.get(fact.fid)
        if mapping is not None and mapping.outcome == "mapped":
            grouped.setdefault((mapping.owner, mapping.attribute_key), []).append(observation(fact, mapping.owner))
    sets = {}
    for (owner, attribute_key), observations in grouped.items():
        obs_set = classify(
            ObservationSet(set_key=f"{owner}:{attribute_key}", subject=owner, prop=attribute_key, level="attribute", observations=observations),
            pins=pins,
        )
        sets[(owner, attribute_key)] = obs_set
        record_observation_set(ledger, obs_set, pins=pins)
    return result, sets
