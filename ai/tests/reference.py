"""
Reference specs: what a correct Reconcile result for a canonical regression
document must contain, must keep blocked (and in which negative state), and
must never contain -- checked by one evaluator for scripted, replayed and
live runs alike (.Documentation/reconcile-architecture-plan.md, Phase 0 and
the Phase 5 gate).

A spec (ai/tests/fixtures/references/<doc>.json):

    {
      "document": "...", "description": "...",
      "required_objects":       [{"id": "...", "type": "match", "names": ["New Zealand v Fiji"]}],
      "required_relationships": [{"id": "...", "type": "played_at", "subject": [...names], "object": [...names]}],
      "required_blocked":       [{"id": "...", "names": ["McLean Park"], "states": ["not_stated"]}],
      "forbidden_objects":      [{"id": "...", "type": "team" | null, "names": [...], "name_contains": [...]}],
      "forbidden_relationships":[{"id": "...", "type": "played_at", "subject": [...] | null, "object": [...] | null}]
    }

Names compare case-, accent- and whitespace-insensitively; every list of
names is a set of acceptable alternatives. A spec never names ids, keys or
segment ids, so it outlives any representation change.

Negative states (plan, section 3.4) are derived from a blocked target's own
unmet requirements: `undecidable` when one rests on an open decision or an
unresolved ambiguity; `not_stated` when none of them has any evidenced
counterpart; otherwise `insufficient_evidence` (evidence exists but does not
meet the rule). Until Phase 4 adds `Requirement.state`, this derivation is
the definition the specs are checked against.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

REFERENCES = Path(__file__).parent / "fixtures" / "references"

UNDECIDABLE, INSUFFICIENT, NOT_STATED = "undecidable", "insufficient_evidence", "not_stated"


def norm(name) -> str:
    value = unicodedata.normalize("NFKD", str(name or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    return re.sub(r"\s+", " ", value).strip()


def load_spec(name: str) -> dict:
    return json.loads((REFERENCES / f"{name}.json").read_text(encoding="utf-8"))


@dataclass
class Outcome:
    """A Reconcile result reduced to what a spec can talk about."""

    objects: set = field(default_factory=set)  # (type_key, normalised name)
    relationships: set = field(default_factory=set)  # (type_key, subject name, object name), names normalised
    blocked: dict = field(default_factory=dict)  # normalised target name -> negative state
    # Every blocked entry as reported (several items may share a name).
    blocked_entries: list = field(default_factory=list)

    def names_of(self, type_key=None) -> set:
        return {n for t, n in self.objects if type_key is None or t == type_key}


def blocked_state(entry: dict) -> str:
    """The negative state of one `Analysis.blocked_targets` entry: the state
    the analysis reports for it (ai.services.reconcile.triage), or -- for an
    entry recorded before states were reported -- derived from its own unmet
    requirements."""

    if entry.get("state"):
        return entry["state"]
    own = [m for m in entry.get("missing_requirements", []) if not m.get("entity") or m.get("entity") == entry.get("target")]
    if not own:
        own = entry.get("missing_requirements", [])
    if any(m.get("pending_decision") or m.get("unresolved_ambiguity") for m in own):
        return UNDECIDABLE
    if all(not m.get("evidenced") for m in own):
        return NOT_STATED
    return INSUFFICIENT


def outcome_from_change_set(change_set, blocked_targets, index=None) -> Outcome:
    """From a compiled ChangeSet v3 plus `blocked_targets`. Existing objects
    referenced by key are named through `index` when given."""

    outcome = Outcome()
    tokens = {}
    for action in change_set.actions:
        data = action.model_dump(mode="json")
        if data.get("kind") == "create_object":
            name = norm(data.get("name"))
            tokens[data.get("token")] = name
            outcome.objects.add(((data.get("type") or {}).get("key"), name))

    def name_of(ref):
        ref = ref or {}
        if ref.get("kind") == "new":
            return tokens.get(ref.get("token"), "")
        if index is not None and ref.get("type_key") and ref.get("key"):
            type_item = index.object_type_by_key(ref["type_key"])
            obj = index.object_by_key(type_item.id, ref["key"]) if type_item is not None else None
            if obj is not None:
                return norm(obj.name)
        return norm(ref.get("key"))

    for action in change_set.actions:
        data = action.model_dump(mode="json")
        if data.get("kind") == "create_relationship":
            outcome.relationships.add(((data.get("relationship_type") or {}).get("key"), name_of(data.get("subject")), name_of(data.get("object"))))
    for entry in blocked_targets or []:
        outcome.blocked[norm(entry.get("target"))] = blocked_state(entry)
        outcome.blocked_entries.append(entry)
    return outcome


def outcome_from_proposal(proposal_id, blocked_targets) -> Outcome:
    """From a committed Proposal (any run: scripted, replayed or live) plus
    the run's `blocked_targets`."""

    from model.models.object import Object
    from model.models.object_type import ObjectType
    from model.models.proposal import ProposalChange
    from model.models.relationship_type import RelationshipType

    outcome = Outcome()
    changes = list(ProposalChange.objects.filter(proposal_id=proposal_id)) if proposal_id else []
    names = {}
    for change in changes:
        if change.target_type == "Object" and change.operation == "create":
            names[str(change.target_id)] = norm(change.after.get("name"))
            object_type = ObjectType.objects.filter(id=change.parent_id).first()
            outcome.objects.add((object_type.key if object_type else None, names[str(change.target_id)]))

    def name_of(object_id):
        if str(object_id) in names:
            return names[str(object_id)]
        existing = Object.objects.filter(id=object_id).first()
        return norm(existing.name) if existing else ""

    for change in changes:
        if change.target_type == "Relationship" and change.operation == "create":
            relationship_type = RelationshipType.objects.filter(id=change.parent_id).first()
            outcome.relationships.add((relationship_type.key if relationship_type else None,
                                       name_of(change.after.get("subject_id")), name_of(change.after.get("object_id"))))
    for entry in blocked_targets or []:
        outcome.blocked[norm(entry.get("target"))] = blocked_state(entry)
        outcome.blocked_entries.append(entry)
    return outcome


def _selected_entry(outcome, names, select):
    """The blocked entry a spec item is about. Without `select`, the first
    name that is blocked. With `select` ({"relationship_type_key": k,
    "evidenced_at_least": n}), the item identified by its evidence: among the
    blocked entries with one of the names, the one whose own unmet `k`
    requirement has at least n evidenced counterparts (e.g. the fixture
    table's quarter-final stage, which has its matches -- not a prose
    mention of the same name that has none)."""

    candidates = [e for e in outcome.blocked_entries if norm(e.get("target")) in names]
    if not select:
        state = next((outcome.blocked[n] for n in names if n in outcome.blocked), None)
        return state, ""
    for entry in candidates:
        for missing in entry.get("missing_requirements", []):
            if (not missing.get("entity") or missing.get("entity") == entry.get("target")) \
                    and missing.get("relationship_type_key") == select["relationship_type_key"] \
                    and (missing.get("evidenced") or 0) >= select.get("evidenced_at_least", 1):
                return blocked_state(entry), ""
    return None, f"no blocked {sorted(names)} with {select['relationship_type_key']} evidenced >= {select.get('evidenced_at_least', 1)}"


@dataclass
class Check:
    id: str
    passed: bool
    detail: str = ""


def _names(values) -> set:
    return {norm(v) for v in (values or [])}


def evaluate(outcome: Outcome, spec: dict) -> list[Check]:
    """Every spec assertion, passed or not -- the unit live comparisons count."""

    checks = []
    for item in spec.get("required_objects", []):
        names = _names(item["names"])
        present = bool(names & outcome.names_of(item.get("type")))
        checks.append(Check(item["id"], present, "" if present else f"missing {item.get('type')} {sorted(names)}"))
    for item in spec.get("required_relationships", []):
        subjects, objects = _names(item["subject"]), _names(item["object"])
        present = any(t == item["type"] and s in subjects and o in objects for t, s, o in outcome.relationships)
        checks.append(Check(item["id"], present, "" if present else f"missing {item['type']} {sorted(subjects)} -> {sorted(objects)}"))
    for item in spec.get("required_blocked", []):
        names = _names(item["names"])
        compiled = names & outcome.names_of()
        state, why = _selected_entry(outcome, names, item.get("select"))
        passed = not compiled and state in item["states"]
        detail = "" if passed else (f"compiled: {sorted(compiled)}" if compiled else why or f"state {state!r}, expected one of {item['states']}")
        checks.append(Check(item["id"], passed, detail))
    for item in spec.get("forbidden_objects", []):
        names, fragments = _names(item.get("names")), _names(item.get("name_contains"))
        found = sorted(n for t, n in outcome.objects if (item.get("type") in (None, t))
                       and (n in names or any(f in n for f in fragments)))
        checks.append(Check(item["id"], not found, f"forbidden objects present: {found}" if found else ""))
    for item in spec.get("forbidden_relationships", []):
        subjects, objects = _names(item.get("subject")), _names(item.get("object"))
        found = sorted(r for r in outcome.relationships if r[0] == item["type"]
                       and (not subjects or r[1] in subjects) and (not objects or r[2] in objects))
        checks.append(Check(item["id"], not found, f"forbidden relationships present: {found}" if found else ""))
    return checks


@dataclass
class CoreRun:
    analysis: object
    state: object
    index: object
    change_set: object
    blocked: list
    outcome: Outcome


def run_core(testcase, *, model, frame, items, assets, intent, probe_rounds=4) -> CoreRun:
    """The deterministic governance core on IDEAL semantic input, end to end:
    analysis (iterated until every evidence gap has been probed and answered
    not_stated over complete coverage -- the core's own end state, with no AI
    left to ask) -> compile -> TracePolicy -> resolution -> speculative
    staging. Asserts the core's own guarantees (traced, resolvable, valid)."""

    from ai.services.evidence_bundle import EvidenceBundle
    from ai.services.operation_definitions import RECONCILE, RECONCILE_POLICY
    from ai.services.reconcile.analysis import run_analysis
    from ai.services.reconcile.compiler import compile_change_set
    from ai.services.reconcile.state import ReconcileState
    from ai.services.reconcile.trace_policy import check_trace
    from ai.services.resolution import resolve_change_set
    from ai.services.semantic.index import SemanticModelIndex
    from ai.services.staging import stage_and_validate
    from ai.tests.support import graph

    bundle = EvidenceBundle.from_assets(list(assets))
    index = SemanticModelIndex.load(model)
    rs = ReconcileState(frame=frame, graph=graph(*items))
    analysis = run_analysis(rs, index=index, bundle=bundle)
    for _ in range(probe_rounds):
        open_gaps = [r.requirement_id for r in analysis.probe_requests if r.requirement_id not in rs.probed]
        if not open_gaps:
            break
        rs.probed |= set(open_gaps)
        rs.probe_outcomes.update({r: "not_stated" for r in open_gaps})
        rs.missing_evidence.update({r: "complete" for r in open_gaps})
        analysis = run_analysis(rs, index=index, bundle=bundle)

    change_set, trace = compile_change_set(analysis, index=index)
    testcase.assertEqual(check_trace(change_set, trace, analysis), [], "every compiled action must trace to grounded claims")
    blocked = analysis.blocked_targets(index, rs.missing_evidence)
    if change_set.actions:
        resolution = resolve_change_set(change_set, model=model, index=index, policy=RECONCILE_POLICY, bundle=bundle, intent_text=intent)
        testcase.assertEqual(resolution.issues, [])
        staged = stage_and_validate(model=model, user=testcase.user, operation=RECONCILE, resolution=resolution, index=index)
        testcase.assertEqual(staged.issues, [], "the compiled result must be valid against the model")
    return CoreRun(analysis, rs, index, change_set, blocked, outcome_from_change_set(change_set, blocked, index))


def failures(outcome: Outcome, spec: dict) -> list[Check]:
    return [c for c in evaluate(outcome, spec) if not c.passed]


def assert_reference(testcase, outcome: Outcome, spec: dict) -> None:
    failed = failures(outcome, spec)
    testcase.assertEqual(failed, [], "Reference spec '%s' failed:\n%s" % (
        spec.get("document"), "\n".join(f"  {c.id}: {c.detail}" for c in failed)))
