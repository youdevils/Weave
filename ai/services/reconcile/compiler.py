"""
The compiler (C9): accepted claims -> a pure ChangeSet v3 + its ChangeTrace.

Structural only. It turns what the analysis selected into mutations:

    selected entity, identity new          -> create_object (+ planned values)
    selected entity, identity reactivate   -> set_active(true) (+ update_object)
    selected entity, existing, new values  -> update_object
    selected mapped assertion              -> create_relationship (or nothing,
                                              if it already exists; set_active
                                              if it exists retired)
    confirmed removal claim                -> set_active(false)

It never emits a mutation that is not traced to claim decisions (I2) and
never compiles blocked or blocked-dependent items (only `needed` ones). Each
action carries the verbatim provenance of the evidence it rests on, so the
ChangeSet is self-contained; the evidence/decision ids live only in the
ChangeTrace, never in the ChangeSet (I3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from model.services.proposal.evidence import MAX_EVIDENCE_PER_CHANGE

from ai.services.artifacts import Provenance
from ai.services.change_set import ChangeSet
from ai.services.reconcile.analysis import Analysis
from ai.services.semantic.index import SemanticModelIndex

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class TraceEntry:
    subject: str
    evidence_ids: list = field(default_factory=list)
    decision_ids: list = field(default_factory=list)


@dataclass
class ChangeTrace:
    entries: dict = field(default_factory=dict)  # action_id -> TraceEntry
    # Subjects compiled into actions, and selected items needing no change.
    already_consistent: list = field(default_factory=list)

    def payload(self) -> dict:
        return {
            action_id: {"subject": e.subject, "evidence_ids": e.evidence_ids, "decision_ids": e.decision_ids}
            for action_id, e in self.entries.items()
        }


def _provenance(items) -> list[dict]:
    seen, result = set(), []
    for item in items:
        marker = (item.source_id, item.excerpt)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(Provenance(
            source_id=item.source_id, excerpt=item.excerpt, segment_id=getattr(item, "segment_id", None),
            locator=item.locator or getattr(item, "segment_id", None),
        ).model_dump())
    return result[:MAX_EVIDENCE_PER_CHANGE]


def _timestamp(value) -> str | None:
    text = (value or "").strip()
    if not _DATE.match(text):
        return None
    return text if "T" in text else f"{text[:10]}T00:00:00Z"


class _Compiler:

    def __init__(self, analysis: Analysis, index: SemanticModelIndex):
        self.analysis = analysis
        self.index = index
        self.actions: list[dict] = []
        self.trace = ChangeTrace()
        self.refs: dict[str, dict] = {}

    def emit(self, action: dict, *, subject, evidence_ids, decision_ids):
        action_id = f"a{len(self.actions) + 1}"
        action["action_id"] = action_id
        self.actions.append(action)
        self.trace.entries[action_id] = TraceEntry(subject, list(dict.fromkeys(evidence_ids)), list(dict.fromkeys(d for d in decision_ids if d)))
        return action_id

    def corroborate(self, action_id, aid, assertion, mapping) -> None:
        """A further claim stating an already-compiled relationship: its
        evidence and decisions join that action's trace and provenance."""

        if action_id is None:
            self.trace.already_consistent.append(aid)
            return
        action = next(a for a in self.actions if a["action_id"] == action_id)
        seen = {(p["source_id"], p["excerpt"]) for p in action.get("provenance", [])}
        action["provenance"] = [*action.get("provenance", []),
                                *(p for p in _provenance(assertion.provenance) if (p["source_id"], p["excerpt"]) not in seen)][:MAX_EVIDENCE_PER_CHANGE]
        entry = self.trace.entries[action_id]
        entry.evidence_ids = list(dict.fromkeys([*entry.evidence_ids, aid]))
        entry.decision_ids = list(dict.fromkeys([*entry.decision_ids, mapping.decision_id, f"esc:{aid}"]))

    def values_for(self, owner, *, modes):
        return [v for v in self.analysis.values if v.owner == owner and v.mode in modes]

    def attribute_payload(self, values) -> list[dict]:
        payload = []
        for value in values:
            item = {"key": value.attribute_key}
            if isinstance(value.value, bool):
                item["boolean_value"] = value.value
            elif isinstance(value.value, (int, float)):
                item["number_value"] = value.value
            else:
                item["string_value"] = str(value.value)
            payload.append(item)
        return payload

    def fact_provenance(self, values):
        return [p for v in values for p in self.analysis.graph.fact(v.fid).provenance]

    def run(self) -> tuple[ChangeSet, ChangeTrace]:
        analysis, index = self.analysis, self.index
        scope = analysis.scope
        order = {cid: position for position, cid in enumerate(analysis.clusters.clusters)}
        objects = sorted(scope.needed, key=lambda c: order.get(c, 0))

        for cid in objects:
            cluster = analysis.clusters.clusters[cid]
            identity = analysis.identities[cid]
            type_item = index.object_types[analysis.types[cid].type_id]
            base_decisions = [analysis.types[cid].decision_id, identity.decision_id, scope.decisions.get(cid)]
            if identity.outcome == "new":
                token = f"e_{cid}"
                values = self.values_for(cid, modes=("set",))
                self.refs[cid] = {"kind": "new", "token": token}
                self.emit(
                    {
                        "kind": "create_object", "token": token, "type": {"kind": "existing", "key": type_item.key},
                        "name": cluster.name, "attributes": self.attribute_payload(values),
                        "provenance": _provenance([*cluster.provenance, *self.fact_provenance(values)]),
                        "rationale": f"The evidence names '{cluster.name}' as a {type_item.name}.",
                    },
                    subject=cid, evidence_ids=[*cluster.member_eids, *(v.fid for v in values)],
                    decision_ids=[*base_decisions, *(v.decision_id for v in values)],
                )
                continue

            obj = index.objects[identity.object_id]
            self.refs[cid] = {"kind": "existing", "type_key": type_item.key, "key": obj.key}
            if identity.outcome == "reactivate":
                self.emit(
                    {
                        "kind": "set_active", "active": True,
                        "target": {"entity": "object", "object": self.refs[cid]},
                        "provenance": _provenance(cluster.provenance),
                        "rationale": f"The evidence describes '{cluster.name}' as current; it is retired in the model.",
                    },
                    subject=cid, evidence_ids=cluster.member_eids, decision_ids=base_decisions,
                )
            values = self.values_for(cid, modes=("update", "set"))
            if values:
                self.emit(
                    {
                        "kind": "update_object", "target": self.refs[cid], "attributes": self.attribute_payload(values),
                        "provenance": _provenance(self.fact_provenance(values)),
                        "rationale": f"The evidence gives new values for '{cluster.name}'.",
                    },
                    subject=cid, evidence_ids=[*cluster.member_eids, *(v.fid for v in values)],
                    decision_ids=[*base_decisions, *(v.decision_id for v in values)],
                )
            elif identity.outcome == "existing":
                self.trace.already_consistent.append(cid)

        for cid in sorted(scope.anchor_clusters - scope.needed):
            identity = analysis.identities[cid]
            obj = index.objects[identity.object_id]
            self.refs[cid] = {"kind": "existing", "type_key": index.object_types[obj.type_id].key, "key": obj.key}

        assertions = sorted(scope.selected_assertions, key=lambda aid: [a.aid for a in analysis.graph.assertions].index(aid))
        # Several claims stating the same relationship (same type, ends and
        # validity) corroborate ONE relationship: one action, citing them all.
        stated: dict[tuple, str | None] = {}
        for aid in assertions:
            mapping = analysis.assertions[aid]
            assertion = analysis.graph.assertion(aid)
            subject_cid, object_cid = mapping.canonical_subject, mapping.canonical_object
            same = (mapping.relationship_type_id, subject_cid, object_cid, assertion.qualifiers.valid_from, assertion.qualifiers.valid_to)
            if same in stated:
                self.corroborate(stated[same], aid, assertion, mapping)
                continue
            for cid in (subject_cid, object_cid):
                identity = analysis.identities.get(cid)
                if cid not in self.refs and identity is not None and identity.outcome == "existing":
                    obj = index.objects[identity.object_id]
                    self.refs[cid] = {"kind": "existing", "type_key": index.object_types[obj.type_id].key, "key": obj.key}
            if subject_cid not in self.refs or object_cid not in self.refs:
                continue
            relationship_type = index.relationship_types[mapping.relationship_type_id]
            decisions = [mapping.decision_id, f"esc:{aid}", analysis.identities[subject_cid].decision_id, analysis.identities[object_cid].decision_id]
            subject_ref, object_ref = self.refs[subject_cid], self.refs[object_cid]
            if subject_ref["kind"] == "existing" and object_ref["kind"] == "existing":
                existing = index.relationships_matching(
                    relationship_type.id, analysis.identities[subject_cid].object_id, analysis.identities[object_cid].object_id
                )
                if any(r.is_active for r in existing):
                    self.trace.already_consistent.append(aid)
                    stated[same] = None
                    continue
                if existing:
                    stated[same] = self.emit(
                        {
                            "kind": "set_active", "active": True,
                            "target": {"entity": "relationship", "relationship": {
                                "relationship_type_key": relationship_type.key, "subject": subject_ref, "object": object_ref}},
                            "provenance": _provenance(assertion.provenance),
                            "rationale": f"The evidence states this {relationship_type.name} relationship is current.",
                        },
                        subject=aid, evidence_ids=[aid], decision_ids=decisions,
                    )
                    continue
            values = self.values_for(aid, modes=("set",))
            action = {
                "kind": "create_relationship", "relationship_type": {"kind": "existing", "key": relationship_type.key},
                "subject": subject_ref, "object": object_ref, "attributes": self.attribute_payload(values),
                "provenance": _provenance([*assertion.provenance, *self.fact_provenance(values)]),
                "rationale": f"The evidence says '{analysis.cluster_name(mapping.subject_cid)}' {assertion.predicate} '{analysis.cluster_name(mapping.object_cid)}'.",
            }
            valid_from, valid_to = _timestamp(assertion.qualifiers.valid_from), _timestamp(assertion.qualifiers.valid_to)
            if valid_from:
                action["valid_from"] = valid_from
            if valid_to:
                action["valid_to"] = valid_to
            stated[same] = self.emit(action, subject=aid, evidence_ids=[aid, *(v.fid for v in values)], decision_ids=[*decisions, *(v.decision_id for v in values)])

        for removal in analysis.removals:
            if not removal.confirmed:
                continue
            if removal.kind == "object":
                cluster = analysis.clusters.clusters[removal.subject]
                obj = index.objects[removal.target_id]
                target = {"entity": "object", "object": {"kind": "existing", "type_key": index.object_types[obj.type_id].key, "key": obj.key}}
                provenance, evidence_ids = cluster.provenance, cluster.member_eids
                decisions = [analysis.identities[removal.subject].decision_id]
            else:
                mapping = analysis.assertions[removal.subject]
                relationship = index.relationships[removal.target_id]
                subject, obj = index.objects[relationship.subject_id], index.objects[relationship.object_id]
                target = {"entity": "relationship", "relationship": {
                    "relationship_type_key": index.relationship_types[relationship.type_id].key,
                    "subject": {"kind": "existing", "type_key": index.object_types[subject.type_id].key, "key": subject.key},
                    "object": {"kind": "existing", "type_key": index.object_types[obj.type_id].key, "key": obj.key},
                }}
                provenance, evidence_ids = analysis.graph.assertion(removal.subject).provenance, [removal.subject]
                decisions = [mapping.decision_id]
            self.emit(
                {"kind": "set_active", "active": False, "target": target, "provenance": _provenance(provenance),
                 "rationale": "The evidence explicitly states this has ended or been removed."},
                subject=removal.subject, evidence_ids=evidence_ids,
                decision_ids=[*decisions, f"adj:{removal.question_key}"],
            )

        summary = self.summary()
        return ChangeSet.model_validate({"summary": summary, "actions": self.actions}), self.trace

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for action in self.actions:
            counts[action["kind"]] = counts.get(action["kind"], 0) + 1
        if not counts:
            return "No model changes are needed."
        labels = {
            "create_object": "new entities", "update_object": "updated entities", "create_relationship": "new relationships",
            "set_active": "lifecycle changes",
        }
        return "Proposed: " + ", ".join(f"{n} {labels.get(kind, kind)}" for kind, n in counts.items()) + "."


def compile_change_set(analysis: Analysis, *, index: SemanticModelIndex) -> tuple[ChangeSet, ChangeTrace]:
    return _Compiler(analysis, index).run()
