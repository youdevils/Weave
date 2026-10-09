"""
Intent links (readings mode): what the REQUEST says about how its targets
relate to an existing entity it names -- "add the venues and stages to the
2027 Championship" -- when no evidence claim states it.

The flyer never says Pool Stage belongs to the 2027 Championship; the request
does. Nothing in the evidence relates them, and the model's rules may not
require the link, so no requirement and no lead ever surface it: it was
silently dropped in both modes (live gate 2026-10-09, rugby flyer, 0/5).

OnyxJar does not decide that link. It asks ONE typed question per (target,
anchor) -- only when the target has evidenced items, none of them is related
to the anchor, and some catalogue rule allows a relationship between the two
types -- offering exactly those legal relationships (plus none /
undecidable). The answer must quote the request. A claimed answer is an AI
semantic claim (`adj:intent_link:<target>:<anchor>`); its expansion -- the
anchor as an intent-origin entity, and one structural assertion from it to
each evidenced item of the target -- is its structural consequence (I2),
ledgered over that claim. Identity then resolves the anchor to the existing
Object: nothing is created for it.
"""

from __future__ import annotations

from ai.services.artifacts import Provenance
from ai.services.evidence_bundle import INTENT_SOURCE_ID
from ai.services.evidence_graph import EvidenceAssertion, EvidenceEntity, EvidenceGraph
from ai.services.reconcile import questions as q
from ai.services.reconcile.mapping import AS_STATED, _label_matches, direct_options
from ai.services.semantic.index import normalize_name

KIND = "intent_link"


def key(target_id, anchor_id) -> str:
    return q.key(KIND, target_id, anchor_id)


def _type_of(index, hint, label):
    item = index.object_type_by_key(hint) if hint else None
    if item is None:
        matches = _label_matches(index, label)
        item = matches[0] if len(matches) == 1 else None
    return item if item is not None and item.is_active else None


def _pairs(frame, index):
    for anchor in frame.anchors:
        anchor_type = _type_of(index, anchor.type_hint, "")
        if anchor_type is None:
            continue
        for target in frame.targets:
            if target.verb != "add":
                continue
            target_type = _type_of(index, target.type_hint, target.type_label)
            if target_type is None:
                continue
            legal = direct_options(index, anchor_type.id, target_type.id)
            if legal:
                yield anchor, anchor_type, target, target_type, legal


def _items(graph, target_type, kind_of):
    return [e for e in graph.entities if e.specificity == "specific" and kind_of(e) == target_type.id]


def _related(graph, items, anchor) -> bool:
    anchor_ids = {e.eid for e in graph.entities if normalize_name(anchor.name) in {normalize_name(n) for n in (e.name, *e.aliases)}}
    item_ids = {e.eid for e in items}
    return any({a.subject_eid, a.object_eid} & anchor_ids and {a.subject_eid, a.object_eid} & item_ids for a in graph.assertions)


def questions(frame, graph, index, kind_of, *, pins, asked) -> list:
    found = []
    for anchor, anchor_type, target, target_type, legal in _pairs(frame, index):
        question_id = key(target.target_id, anchor.anchor_id)
        if question_id in pins or question_id in asked:
            continue
        items = _items(graph, target_type, kind_of)
        if not items or _related(graph, items, anchor):
            continue
        options = []
        for relationship_type_id, orientation in legal:
            relationship = index.relationship_types[relationship_type_id]
            first, second = (anchor_type, target_type) if orientation == AS_STATED else (target_type, anchor_type)
            options.append(q.QuestionOption(option_id=f"{relationship.key}:{orientation}",
                                            label=f"{first.name} -{relationship.name}-> {second.name} ({relationship.key})",
                                            detail=relationship.description or ""))
        found.append(q.Question(
            question_id=question_id, kind=KIND, subject_ids=[target.target_id, anchor.anchor_id],
            prompt=(f"The request asks to {target.verb} '{target.type_label}' and names the existing {anchor_type.name} "
                    f"'{anchor.name}'. Does the request itself say how the {target.type_label} it asks for relate to "
                    f"'{anchor.name}'? ({len(items)} evidenced: {', '.join(e.name for e in items[:5])}.) Quote the request."),
            options=q.standard_options(options),
            excerpts=[target.excerpt, anchor.excerpt],
        ))
    return found


def claims(frame, graph, index, kind_of, *, pins, intent_text) -> tuple[EvidenceGraph, dict]:
    """The structural consequences of every claimed intent-link answer.
    -> (graph patch with origin='intent', {item id: [adj: decision]})."""

    patch, inputs = EvidenceGraph(), {}
    for anchor, anchor_type, target, target_type, legal in _pairs(frame, index):
        question_id = key(target.target_id, anchor.anchor_id)
        pin = pins.get(question_id)
        if pin is None or not q.is_claim(pin):
            continue
        relationship_key, _, orientation = pin.option_id.partition(":")
        relationship = index.relationship_type_by_key(relationship_key)
        if relationship is None or (relationship.id, orientation) not in legal:
            continue
        decision = q.pin_decision_id(question_id)
        anchor_eid = f"i/{anchor.anchor_id}"
        if patch.entity(anchor_eid) is None:
            patch.entities.append(EvidenceEntity(
                eid=anchor_eid, name=anchor.name, type_label=anchor_type.name, type_hint=anchor_type.key, origin="intent",
                provenance=[Provenance(source_id=INTENT_SOURCE_ID, excerpt=anchor.excerpt)],
            ))
            inputs[anchor_eid] = [decision]
        for item in _items(graph, target_type, kind_of):
            aid = f"i/{anchor.anchor_id}/{item.eid}"
            item_citation = next((p for p in item.provenance if p.source_id != INTENT_SOURCE_ID), None)
            if item_citation is None:
                continue
            patch.assertions.append(EvidenceAssertion(
                aid=aid, subject_eid=anchor_eid, predicate=relationship.name, object_eid=item.eid,
                relationship_type_hint=relationship.key, hint_orientation=orientation, support="structural", origin="intent",
                provenance=[Provenance(source_id=INTENT_SOURCE_ID, excerpt=intent_text), item_citation.model_copy()],
            ))
            inputs.setdefault(aid, []).append(decision)
    return patch, inputs
