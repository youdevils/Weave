"""
Claim grounding, layer 2 (L2): does the evidence a claim cites even mention
what the claim is about? Deterministic and ontology-free (I1-safe) -- it
compares names, aliases and values with cited text, never catalogue types.

    L1 literal     every excerpt occurs in its cited source/segment
                   (ai.services.provenance)
    L2 anchoring   this module:
                     entity     its evidence mentions its name or an alias
                     fact       its evidence contains its value
                     assertion  one cited unit mentions both endpoints
                                ("anchored"); or, for `support: structural`,
                                the endpoints are mentioned in cited units
                                that are structurally related -- a heading
                                (or table) and something under it, or the
                                user's intent naming one endpoint alongside
                                the other's kind while a source names that
                                other endpoint ("structural")
    L3 adequacy    whether the cited text really supports the meaning --
                   not decidable by code; Verification reviews it, with the
                   L2 outcomes (and every `structural` claim) in the ledger.

A cited "unit" is the cited segment's text when the provenance names a
segment (ai.services.provenance.resolve_segments fills it in when the excerpt
occurs in exactly one segment), the excerpt itself otherwise, and the
excerpt for the intent. Structural context (headings, headers) is never
itself a claim: it only satisfies L2 when a claim explicitly cites it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.services.evidence_bundle import INTENT_SOURCE_ID, EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph, item_id
from ai.services.feedback import AIIssue, issue
from ai.services.sources import mentions, value_occurs

ANCHORED, STRUCTURAL, UNANCHORED = "anchored", "structural", "unanchored"


@dataclass(frozen=True)
class Unit:
    key: str
    text: str
    source_id: str
    segment_id: str | None
    ancestor_ids: tuple = ()


def units(provenance, bundle: EvidenceBundle) -> list[Unit]:
    found = []
    for item in provenance:
        segment = bundle.segment(item.segment_id) if getattr(item, "segment_id", None) else None
        if item.source_id == INTENT_SOURCE_ID:
            found.append(Unit(f"intent:{item.excerpt}", item.excerpt, INTENT_SOURCE_ID, None))
        elif segment is not None and segment.source_id == item.source_id:
            found.append(Unit(segment.segment_id, segment.text, segment.source_id, segment.segment_id, tuple(segment.ancestor_ids)))
        else:
            found.append(Unit(f"{item.source_id}:{item.excerpt}", item.excerpt, item.source_id, None))
    return found


def _names(entity) -> list[str]:
    return [entity.name, *entity.aliases]


def _related(a: Unit, b: Unit) -> bool:
    if a.source_id != b.source_id or a.source_id == INTENT_SOURCE_ID:
        return False
    return (a.segment_id is not None and a.segment_id in b.ancestor_ids) or (b.segment_id is not None and b.segment_id in a.ancestor_ids)


def ground_entity(entity, bundle: EvidenceBundle) -> str:
    return ANCHORED if any(mentions(u.text, _names(entity)) for u in units(entity.provenance, bundle)) else UNANCHORED


def ground_fact(fact, bundle: EvidenceBundle) -> str:
    return ANCHORED if any(value_occurs(fact.value, u.text) for u in units(fact.provenance, bundle)) else UNANCHORED


def ground_assertion(assertion, *, subject, obj, bundle: EvidenceBundle) -> str:
    if subject is None or obj is None:
        return UNANCHORED
    cited = units(assertion.provenance, bundle)
    s_names, o_names = _names(subject), _names(obj)
    if any(mentions(u.text, s_names) and mentions(u.text, o_names) for u in cited):
        return ANCHORED
    if getattr(assertion, "support", "explicit") != "structural":
        return UNANCHORED
    s_units = [u for u in cited if mentions(u.text, s_names)]
    o_units = [u for u in cited if mentions(u.text, o_names)]
    if any(_related(a, b) for a in s_units for b in o_units):
        return STRUCTURAL
    # The user's intent naming one endpoint alongside the other's kind
    # ("add the stages ... to the 2027 Championship"), with a source naming
    # that other endpoint.
    intent_units = [u for u in cited if u.source_id == INTENT_SOURCE_ID]
    source_units = [u for u in cited if u.source_id != INTENT_SOURCE_ID]
    for named, kinded in ((subject, obj), (obj, subject)):
        if any(mentions(u.text, _names(named)) and mentions(u.text, [kinded.type_label]) for u in intent_units) and any(
            mentions(u.text, _names(kinded)) for u in source_units
        ):
            return STRUCTURAL
    return UNANCHORED


def ground_graph(graph: EvidenceGraph, *, bundle: EvidenceBundle, known: EvidenceGraph | None = None) -> dict[str, str]:
    """item id -> anchored | structural | unanchored. `known` supplies the
    entities that assertions in `graph` may refer to but don't define."""

    entities = {e.eid: e for e in (known.entities if known else [])}
    entities.update({e.eid: e for e in graph.entities})
    outcomes = {}
    for entity in graph.entities:
        outcomes[entity.eid] = ground_entity(entity, bundle)
    for fact in graph.facts:
        outcomes[fact.fid] = ground_fact(fact, bundle)
    for assertion in graph.assertions:
        outcomes[assertion.aid] = ground_assertion(
            assertion, subject=entities.get(assertion.subject_eid), obj=entities.get(assertion.object_eid), bundle=bundle
        )
    return outcomes


_MESSAGES = {
    "entity": "its cited evidence does not mention '{name}' (or an alias).",
    "fact": "its cited evidence does not contain the value '{value}'.",
    "assertion": (
        "its cited evidence does not mention both '{subject}' and '{object}'. Cite the segment that states the relationship; "
        "if its meaning comes from layout (a heading and an item under it), set support='structural' and cite both."
    ),
}


def grounding_issues(graph: EvidenceGraph, *, bundle: EvidenceBundle, known: EvidenceGraph | None = None) -> list[AIIssue]:
    outcomes = ground_graph(graph, bundle=bundle, known=known)
    entities = {e.eid: e for e in [*(known.entities if known else []), *graph.entities]}
    issues = []
    for item in graph.items():
        identifier = item_id(item)
        if outcomes.get(identifier) != UNANCHORED:
            continue
        if hasattr(item, "eid"):
            message = _MESSAGES["entity"].format(name=item.name)
        elif hasattr(item, "fid"):
            message = _MESSAGES["fact"].format(value=item.value)
        else:
            subject, obj = entities.get(item.subject_eid), entities.get(item.object_eid)
            message = _MESSAGES["assertion"].format(subject=subject.name if subject else item.subject_eid, object=obj.name if obj else item.object_eid)
        issues.append(issue("unanchored_claim", f"'{identifier}': {message}", item_id=identifier))
    return issues
