"""
Scope (C5, D): which evidenced items a Reconcile run should compile.

Intent targets and anchors come from the IntentFrame (claims). A target's
type label maps to the catalogue like any other claim (lexical / hint /
adjudicated); an anchor binds to an existing Object only lexically (several
matches are a clarification). A target labelled with the catalogue's own
term for relationships in general ("relationships") names no kind: it is the
same claim as `include_related` and is folded into it (`general_relationships`,
lexical), never made into some relationship type. Every target is requested
work with a reported status (ai.services.reconcile.analysis): an unmapped
target is reported as a block -- it never widens scope, never empties it for
the other targets, and is never fabricated into a type. Only when the user
named no kind of thing at all (no targets, none unframed) is every compilable
evidenced item a target.

Evidence-Selective Closure (ESC) then works over what the evidence already
claims -- it SELECTS, it never adds (I2). For every new or reactivated
entity in scope it derives, from the ontology, the rules with a minimum at
its end; a requirement is satisfied only by `mapped` assertions between
compilable (specific, identified) entities with the right type and
orientation, whose counterparts are themselves satisfiable. An unsatisfied
requirement is a structural fact; recovering it needs a new claim (Gap
Probe), never OnyxJar construction. Evidence that would satisfy it but whose
mapping is still undecided (`ambiguous` / `unresolved_ambiguity`, with an
option for the rule's relationship in the right orientation) is
`pending_decision`: it counts as evidenced (the evidence states something)
but never as viable, and such a requirement is a decision gap -- answered by
Adjudication, never re-probed.

Outcomes per entity cluster:

    selected           in scope and compilable
    blocked            an intent target whose requirement can't be satisfied
                       (after probing) -- not compiled; a material finding
    blocked_dependent  selected only to support a blocked target
    omitted            a supporting item that is not satisfiable/needed
    clarification      an intent target whose requirement is ambiguous
                       (the Gap Probe found several possible satisfiers)

More evidenced satisfiers than a rule's maximum allows is never resolved by
picking one: when time qualifiers separate them, the single current one is
kept (or an Adjudication "which is current" question is asked); when they
are simultaneous facts, it is a `constraint_conflict` -- none of them is
compiled, the requirement is never probed (the evidence exists), and it is a
material finding suggesting a model change. Cardinality counts distinct
counterparts, never statements: two claims stating the same relationship
("Eden Park hosts the match" / "the match is played at Eden Park")
corroborate one relationship -- they neither exceed a maximum nor satisfy a
minimum twice.

Optional (min 0) relationships are only included between in-scope entities,
and only when the IntentFrame asks (`include_related`) or one end is an
anchor the intent names.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.evidence_graph import EvidenceGraph
from ai.services.intent_frame import IntentFrame
from ai.services.reconcile import questions as q
from ai.services.reconcile.ledger import SCOPE, Ledger
from ai.services.reconcile.mapping import _label_matches, _similar_types
from ai.services.reconcile.normalise import ClusterResult, singular
from ai.services.semantic.index import SemanticModelIndex

TARGET_VERBS = ("add", "update", "link")
# The catalogue's own words for "relationships in general" (not a kind).
GENERAL_RELATIONSHIP_LABELS = ("relationship", "relation", "relationship type")
GENERAL_RELATIONSHIPS = "general_relationships"


@dataclass
class TargetType:
    target_id: str
    verb: str
    outcome: str  # mapped | ambiguous | unmapped | unresolved_ambiguity
    kind: str | None = None  # object_type | relationship_type
    type_id: str | None = None
    options: list = field(default_factory=list)  # "object_type:venue" | "relationship_type:played_at"
    decision_id: str = ""


@dataclass
class Anchor:
    anchor_id: str
    name: str
    outcome: str  # resolved | ambiguous | unresolved
    object_id: str | None = None
    options: list = field(default_factory=list)
    decision_id: str = ""


@dataclass
class Requirement:
    requirement_id: str
    cluster_id: str
    rule_id: str
    side: str  # subject | object: which end of the rule the cluster is
    relationship_type_id: str
    counterpart_type_id: str
    minimum: int
    maximum: int | None
    satisfiers: list = field(default_factory=list)  # aids usable now
    candidates: list = field(default_factory=list)  # aids that would satisfy if their counterpart were viable
    # aids that would be candidates but for an unresolved ambiguity (the
    # counterpart's identity/type): evidence exists, so this is never probed.
    ambiguous: list = field(default_factory=list)
    # aids excluded as a constraint_conflict: evidence exists, never probed.
    conflicted: list = field(default_factory=list)
    # aids that would be candidates but for an undecided mapping (one of their
    # options is this rule's relationship): a decision gap, never probed.
    pending_decision: list = field(default_factory=list)
    canonical: int = 0
    # aid -> the counterpart cluster it relates this one to.
    counterparts: dict = field(default_factory=dict)

    def distinct(self, aids) -> int:
        """How many distinct counterparts these assertions name."""

        return len({self.counterparts.get(aid, aid) for aid in aids})

    @property
    def evidenced(self) -> int:
        """Counterparts the evidence states for this requirement, whatever the
        fate of the claims stating them."""

        return self.distinct([*self.candidates, *self.ambiguous, *self.conflicted, *self.pending_decision]) + self.canonical

    @property
    def viable_count(self) -> int:
        return self.distinct(self.satisfiers) + self.canonical


@dataclass
class ScopeResult:
    targets: dict = field(default_factory=dict)  # target_id -> TargetType
    anchors: dict = field(default_factory=dict)  # anchor_id -> Anchor
    target_clusters: set = field(default_factory=set)
    anchor_clusters: set = field(default_factory=set)
    tentative: set = field(default_factory=set)
    viable: set = field(default_factory=set)
    needed: set = field(default_factory=set)
    outcomes: dict = field(default_factory=dict)  # cid -> outcome
    selected_assertions: set = field(default_factory=set)
    excluded_assertions: dict = field(default_factory=dict)  # aid -> reason
    requirements: dict = field(default_factory=dict)  # cid -> [Requirement]
    unsatisfied: list = field(default_factory=list)  # [Requirement] -- own, not dependency-only
    over_asserted: list = field(default_factory=list)  # [(cid, Requirement, [aids])] -- time-separated, asked
    constraint_conflicts: list = field(default_factory=list)  # [(cid, Requirement, [aids], allowed)] -- simultaneous
    edges: dict = field(default_factory=dict)  # cid -> {counterpart cids it depends on}
    blocked_roots: dict = field(default_factory=dict)  # blocked target cid -> [dependant cids]
    clarifications: list = field(default_factory=list)  # user-facing questions
    decisions: dict = field(default_factory=dict)  # cid -> decision id


# -- targets / anchors ------------------------------------------------------------


def _type_option(kind, key) -> str:
    return f"{kind}:{key}"


def resolve_targets(frame: IntentFrame, *, index: SemanticModelIndex, pins: dict, ledger: Ledger) -> dict[str, TargetType]:
    result = {}
    for target in frame.targets:
        pin_key = q.key("target_type", target.target_id)
        inputs = [f"frame:{target.target_id}", *q.pin_inputs(pin_key, pins)]
        resolved = TargetType(target.target_id, target.verb, "unmapped")
        pin = pins.get(pin_key)
        object_matches = _label_matches(index, target.type_label)
        relationship_matches = [
            t for t in index.relationship_types.values()
            if singular(t.name) == singular(target.type_label) or t.key == target.type_label
        ]
        options = [*(_type_option("object_type", t.key) for t in object_matches),
                   *(_type_option("relationship_type", t.key) for t in relationship_matches)]
        if not target.type_hint and singular(target.type_label) in GENERAL_RELATIONSHIP_LABELS and pin is None:
            resolved, basis = TargetType(target.target_id, target.verb, GENERAL_RELATIONSHIPS), "lexical"
        elif pin is not None:
            kind, _, type_key = pin.option_id.partition(":")
            item = index.type_by_key(kind, type_key) if kind in ("object_type", "relationship_type") else None
            if item is not None:
                resolved, basis = TargetType(target.target_id, target.verb, "mapped", kind, item.id), "adjudicated"
            elif pin.option_id == q.NONE:
                resolved, basis = TargetType(target.target_id, target.verb, "unmapped"), "adjudicated"
            else:
                resolved, basis = TargetType(target.target_id, target.verb, "unresolved_ambiguity", options=options), pin.basis
        elif target.type_hint and index.object_type_by_key(target.type_hint):
            resolved, basis = TargetType(target.target_id, target.verb, "mapped", "object_type", index.object_type_by_key(target.type_hint).id), "hint"
        elif target.type_hint and index.relationship_type_by_key(target.type_hint):
            resolved, basis = TargetType(target.target_id, target.verb, "mapped", "relationship_type", index.relationship_type_by_key(target.type_hint).id), "hint"
        elif len(options) == 1:
            kind, _, type_key = options[0].partition(":")
            resolved, basis = TargetType(target.target_id, target.verb, "mapped", kind, index.type_by_key(kind, type_key).id), "lexical"
        else:
            similar = options or [_type_option("object_type", t.key) for t in _similar_types(index, [target.type_label])]
            resolved = TargetType(target.target_id, target.verb, "ambiguous" if similar else "unmapped", options=similar)
            basis = "deterministic"
        resolved.decision_id = f"target:{target.target_id}"
        item = index.type_by_id(resolved.type_id) if resolved.type_id else None
        ledger.structural(
            resolved.decision_id, step=SCOPE, basis=basis, subject_ids=[target.target_id], inputs=inputs,
            outcome=resolved.outcome, options=[{"option_id": o} for o in resolved.options],
            source={"type_label": target.type_label, "verb": target.verb, "excerpt": target.excerpt},
            mapping={"type_key": item.key, "kind": resolved.kind} if item else None, question_key=pin_key,
        )
        result[target.target_id] = resolved
    return result


def resolve_anchors(frame: IntentFrame, *, index: SemanticModelIndex, ledger: Ledger) -> dict[str, Anchor]:
    result = {}
    for anchor in frame.anchors:
        object_type = index.object_type_by_key(anchor.type_hint) if anchor.type_hint else None
        type_ids = [object_type.id] if object_type else list(index.object_types)
        matches = [m.object for type_id in type_ids for m in index.match_objects(type_id, anchor.name)]
        if len(matches) == 1:
            resolved = Anchor(anchor.anchor_id, anchor.name, "resolved", matches[0].id)
        elif matches:
            resolved = Anchor(anchor.anchor_id, anchor.name, "ambiguous", options=[f"{index.object_types[m.type_id].key}:{m.key}" for m in matches])
        else:
            resolved = Anchor(anchor.anchor_id, anchor.name, "unresolved")
        resolved.decision_id = f"anchor:{anchor.anchor_id}"
        ledger.structural(
            resolved.decision_id, step=SCOPE, basis="lexical" if resolved.outcome == "resolved" else "deterministic",
            subject_ids=[anchor.anchor_id], inputs=[f"frame:{anchor.anchor_id}"], outcome=resolved.outcome,
            options=[{"option_id": o} for o in resolved.options], source={"name": anchor.name, "excerpt": anchor.excerpt},
        )
        result[anchor.anchor_id] = resolved
    return result


# -- ESC -------------------------------------------------------------------------


def _time_separated(assertion) -> bool:
    qualifiers = assertion.qualifiers
    return bool(qualifiers.as_of or qualifiers.valid_from or qualifiers.valid_to) or assertion.modality != "stated"


class _Closure:

    def __init__(self, graph, clusters, types, identities, assertions, *, index, frame, targets, anchors, pins, ledger, excluded, probe_outcomes,
                 unframed=()):
        self.unframed = set(unframed)
        self.include_related = frame.include_related or any(t.outcome == GENERAL_RELATIONSHIPS for t in targets.values())
        self.graph = graph
        self.clusters = clusters
        self.types = types
        self.identities = identities
        self.assertions = assertions
        self.index = index
        self.frame = frame
        self.pins = pins
        self.ledger = ledger
        self.excluded = set(excluded)
        self.probe_outcomes = probe_outcomes  # requirement_id -> "ambiguous" | ...
        self.result = ScopeResult(targets=targets, anchors=anchors)
        self.slot_exclusions: dict[str, str] = {}

    # -- predicates --------------------------------------------------------

    def compilable(self, cid) -> bool:
        cluster = self.clusters.clusters.get(cid)
        return (
            cluster is not None and cluster.specificity == "specific" and cluster.polarity == "present"
            and self.types[cid].outcome == "mapped" and self.identities[cid].resolved and cid not in self.excluded
            and not (set(cluster.member_eids) & self.excluded)
        )

    def usable(self, aid) -> bool:
        mapping = self.assertions.get(aid)
        assertion = self.graph.assertion(aid)
        return (
            mapping is not None and mapping.outcome == "mapped" and assertion is not None and assertion.polarity != "removed"
            and aid not in self.excluded and aid not in self.slot_exclusions
            and self.compilable(mapping.subject_cid) and self.compilable(mapping.object_cid)
        )

    def needs_closure(self, cid) -> bool:
        return self.identities[cid].outcome in ("new", "reactivate")

    def existing(self, cid) -> bool:
        return self.identities[cid].outcome == "existing"

    # -- requirements --------------------------------------------------------

    def requirements_of(self, cid) -> list[Requirement]:
        type_id = self.types[cid].type_id
        found = []
        for rule in self.index.rules_touching(type_id):
            if not self.index.relationship_types[rule.relationship_type_id].is_active:
                continue
            for side, minimum, maximum, counterpart in (
                ("subject", rule.object_minimum, rule.object_maximum, rule.object_type_id),
                ("object", rule.subject_minimum, rule.subject_maximum, rule.subject_type_id),
            ):
                own = rule.subject_type_id if side == "subject" else rule.object_type_id
                if own != type_id:
                    continue
                requirement = Requirement(
                    requirement_id=f"req:{cid}:{rule.id}:{side}", cluster_id=cid, rule_id=rule.id, side=side,
                    relationship_type_id=rule.relationship_type_id, counterpart_type_id=counterpart,
                    minimum=minimum or 0, maximum=maximum,
                )
                for aid, mapping in self.assertions.items():
                    if mapping.outcome in ("ambiguous", "unresolved_ambiguity"):
                        other = self._would_fill(mapping, rule.relationship_type_id, side, cid, counterpart)
                        if other is not None:
                            requirement.pending_decision.append(aid)
                            requirement.counterparts[aid] = other
                        continue
                    if mapping.outcome != "mapped" or mapping.relationship_type_id != rule.relationship_type_id:
                        continue
                    end, other = (mapping.canonical_subject, mapping.canonical_object) if side == "subject" else (mapping.canonical_object, mapping.canonical_subject)
                    if end != cid or self.types[other].type_id != counterpart:
                        continue
                    requirement.counterparts[aid] = other
                    if self.usable(aid):
                        requirement.candidates.append(aid)
                    elif self.slot_exclusions.get(aid) == "constraint_conflict":
                        requirement.conflicted.append(aid)
                    elif self._blocked_by_ambiguity(aid, other):
                        requirement.ambiguous.append(aid)
                if self.identities[cid].outcome == "reactivate":
                    obj_id = self.identities[cid].object_id
                    requirement.canonical = sum(
                        1 for r in self.index.relationships_of(obj_id)
                        if r.is_active and r.type_id == rule.relationship_type_id
                        and (r.subject_id if side == "subject" else r.object_id) == obj_id
                    )
                found.append(requirement)
        return found

    def _would_fill(self, mapping, relationship_type_id, side, cid, counterpart_type_id):
        """The counterpart an undecided assertion would relate this cluster to
        if one of its options were chosen (OnyxJar's options, never a
        choice), or None."""

        for option in mapping.options:
            key, _, orientation = str(option).partition(":")
            relationship_type = self.index.relationship_type_by_key(key)
            if relationship_type is None or relationship_type.id != relationship_type_id:
                continue
            subject, obj = (mapping.subject_cid, mapping.object_cid) if orientation == "as_stated" else (mapping.object_cid, mapping.subject_cid)
            end, other = (subject, obj) if side == "subject" else (obj, subject)
            if end == cid and other in self.types and self.types[other].type_id == counterpart_type_id:
                return other
        return None

    def _blocked_by_ambiguity(self, aid, other) -> bool:
        cluster = self.clusters.clusters.get(other)
        assertion = self.graph.assertion(aid)
        return (
            cluster is not None and cluster.specificity == "specific" and assertion is not None and assertion.polarity != "removed"
            and self.identities[other].outcome in ("ambiguous", "unresolved_ambiguity")
        )

    def counterpart(self, aid, cid) -> str:
        mapping = self.assertions[aid]
        return mapping.object_cid if mapping.subject_cid == cid else mapping.subject_cid

    # -- the closure --------------------------------------------------------------

    def run(self) -> ScopeResult:
        result = self.result
        target_object_types = {t.type_id for t in result.targets.values() if t.outcome == "mapped" and t.kind == "object_type" and t.verb in TARGET_VERBS}
        target_relationship_types = {t.type_id for t in result.targets.values() if t.outcome == "mapped" and t.kind == "relationship_type" and t.verb in TARGET_VERBS}
        anchor_objects = {a.object_id for a in result.anchors.values() if a.outcome == "resolved"}

        cids = list(self.clusters.clusters)
        named_kinds = [t for t in result.targets.values() if t.outcome != GENERAL_RELATIONSHIPS]
        if not named_kinds and not self.unframed:
            result.target_clusters = {c for c in cids if self.compilable(c)}
        else:
            result.target_clusters = {c for c in cids if self.compilable(c) and self.types[c].type_id in target_object_types}
        result.anchor_clusters = {c for c in cids if self.compilable(c) and self.identities[c].object_id in anchor_objects and self.existing(c)}

        seeds = set(result.target_clusters) | result.anchor_clusters
        target_assertions = {
            aid for aid, m in self.assertions.items() if m.outcome == "mapped" and m.relationship_type_id in target_relationship_types and self.usable(aid)
        }
        for aid in target_assertions:
            seeds |= {self.assertions[aid].subject_cid, self.assertions[aid].object_cid}

        for _ in range(4):  # over-assertion exclusions can change viability; bounded re-runs
            self._close(seeds)
            if not self._over_assertion():
                break

        self._outcomes(target_assertions)
        return result

    def _close(self, seeds):
        result = self.result
        result.requirements, result.edges = {}, {}
        tentative, queue = set(), list(seeds)
        while queue:
            cid = queue.pop()
            if cid in tentative:
                continue
            tentative.add(cid)
            if not self.needs_closure(cid):
                continue
            requirements = [r for r in self.requirements_of(cid) if r.minimum > 0]
            result.requirements[cid] = requirements
            for requirement in requirements:
                for aid in requirement.candidates:
                    other = self.counterpart(aid, cid)
                    result.edges.setdefault(cid, set()).add(other)
                    queue.append(other)
        result.tentative = tentative

        viable = set(tentative)
        changed = True
        while changed:
            changed = False
            for cid in sorted(viable):
                if not self.needs_closure(cid):
                    continue
                for requirement in result.requirements.get(cid, []):
                    requirement.satisfiers = [aid for aid in requirement.candidates if self.counterpart(aid, cid) in viable]
                    probe = self.probe_outcomes.get(requirement.requirement_id)
                    if probe == "ambiguous" or requirement.viable_count < requirement.minimum:
                        viable.discard(cid)
                        changed = True
                        break
        result.viable = viable
        # The fixpoint stops at a cluster's first unmet requirement, so the
        # satisfiers of its later requirements (and of anything discarded
        # earlier) can be stale: settle every requirement against the final
        # viable set, so blocked items report exactly which requirements
        # they miss -- not one that is met (a blocked stage's tournament).
        for cid in tentative:
            for requirement in result.requirements.get(cid, []):
                requirement.satisfiers = [aid for aid in requirement.candidates if self.counterpart(aid, cid) in viable]

        anchors = result.anchor_clusters
        needed, queue = set(), [c for c in (result.target_clusters | anchors) if c in viable]
        while queue:
            cid = queue.pop()
            if cid in needed:
                continue
            needed.add(cid)
            for requirement in result.requirements.get(cid, []):
                for aid in requirement.satisfiers:
                    queue.append(self.counterpart(aid, cid))
        result.needed = needed

    def _over_assertion(self) -> bool:
        """Selected satisfiers beyond a rule's maximum (see module docstring).
        Returns True if exclusions changed."""

        changed = False
        result = self.result
        for cid in sorted(result.needed):
            if not self.compilable(cid):
                continue
            for requirement in self.requirements_of(cid):
                if requirement.maximum is None:
                    continue
                existing = 0
                if self.existing(cid):
                    obj_id = self.identities[cid].object_id
                    existing = sum(
                        1 for r in self.index.relationships_of(obj_id)
                        if r.is_active and r.type_id == requirement.relationship_type_id
                        and (r.subject_id if requirement.side == "subject" else r.object_id) == obj_id
                    )
                in_scope = [aid for aid in requirement.candidates if self.counterpart(aid, cid) in result.needed or self.existing(self.counterpart(aid, cid))]
                # A statement already excluded by a conflict on its OTHER end
                # still states a counterpart on this end: leaving it out
                # would let one conflict hide another (a third team on a
                # two-team match, excluded only because that team is also in
                # another match), so the result would depend on which
                # cluster happened to be checked first.
                in_scope += [aid for aid in requirement.conflicted if aid not in in_scope and self.compilable(self.counterpart(aid, cid))]
                allowed = requirement.maximum - existing - requirement.canonical
                if requirement.distinct(in_scope) <= allowed:
                    continue
                temporal = any(_time_separated(self.graph.assertion(aid)) for aid in in_scope)
                if not temporal:
                    # Simultaneous facts: never pick one to satisfy the rule.
                    if not any(c == cid and r.rule_id == requirement.rule_id for c, r, _, _ in result.constraint_conflicts):
                        result.constraint_conflicts.append((cid, requirement, list(in_scope), max(allowed, 0)))
                    for aid in in_scope:
                        if self.slot_exclusions.get(aid) != "constraint_conflict":
                            self.slot_exclusions[aid] = "constraint_conflict"
                            changed = True
                    continue
                slot_key = q.key("current_satisfier", cid, requirement.rule_id, requirement.side)
                pin = self.pins.get(slot_key)
                if pin is not None and pin.option_id in in_scope:
                    keep = {pin.option_id}
                else:
                    current = [
                        aid for aid in in_scope
                        if not self.graph.assertion(aid).qualifiers.valid_to and self.graph.assertion(aid).modality == "stated"
                    ]
                    keep = set(current) if current and len(current) <= allowed and len(current) < len(in_scope) else set()
                    if not keep:
                        result.over_asserted.append((cid, requirement, in_scope))
                for aid in in_scope:
                    if aid not in keep and aid not in self.slot_exclusions:
                        self.slot_exclusions[aid] = "over_asserted" if not keep else "historical"
                        changed = True
        return changed

    def _outcomes(self, target_assertions):
        result = self.result
        blocked = {c for c in result.target_clusters if c not in result.viable}
        reach_from_viable = set(result.needed)

        def reach(start):
            # Only through non-viable clusters: a viable one (a tournament
            # that is added anyway) does not carry one item's block on to
            # an unrelated item behind it.
            seen, queue = set(), [start]
            while queue:
                cid = queue.pop()
                if cid in seen:
                    continue
                seen.add(cid)
                if cid == start or cid not in result.viable:
                    queue.extend(result.edges.get(cid, ()))
            return seen

        for cid in result.tentative:
            if cid in result.needed:
                outcome = "selected"
            elif cid in blocked:
                ambiguous = any(self.probe_outcomes.get(r.requirement_id) == "ambiguous" for r in result.requirements.get(cid, []))
                outcome = "clarification" if ambiguous else "blocked"
            elif any(cid in reach(b) for b in blocked) and cid not in reach_from_viable:
                outcome = "blocked_dependent"
            else:
                outcome = "omitted"
            result.outcomes[cid] = outcome

        for root in blocked:
            dependants = sorted(c for c in reach(root) - {root} if result.outcomes.get(c) == "blocked_dependent")
            result.blocked_roots[root] = dependants

        # Own unsatisfied requirements (not merely a non-viable counterpart)
        # with no evidence at all, decided or not: what a Gap Probe could
        # recover. Undecided evidence is a decision gap, never an evidence gap.
        for cid in sorted(result.tentative - result.viable):
            for requirement in result.requirements.get(cid, []):
                if requirement.evidenced < requirement.minimum and not requirement.pending_decision:
                    result.unsatisfied.append(requirement)

        anchors = result.anchor_clusters
        in_scope = result.needed | anchors
        for aid, mapping in self.assertions.items():
            if not self.usable(aid):
                if aid in self.slot_exclusions:
                    result.excluded_assertions[aid] = self.slot_exclusions[aid]
                continue
            ends = {mapping.subject_cid, mapping.object_cid}
            if not ends <= (in_scope | {c for c in ends if self.existing(c)}):
                continue
            satisfies = any(
                aid in requirement.satisfiers
                for cid in ends & result.needed
                for requirement in result.requirements.get(cid, [])
            )
            anchor_link = bool(ends & anchors) and bool(ends & result.needed)
            related = self.include_related and ends <= in_scope
            if satisfies or anchor_link or related or aid in target_assertions:
                result.selected_assertions.add(aid)

        for cid, outcome in result.outcomes.items():
            requirements = result.requirements.get(cid, [])
            inputs = [self.types[cid].decision_id, self.identities[cid].decision_id, *self.clusters.clusters[cid].member_eids]
            inputs += [self.assertions[a].decision_id for r in requirements for a in r.candidates]
            if cid in result.target_clusters:
                inputs += [t.decision_id for t in result.targets.values() if t.type_id == self.types[cid].type_id]
            decision_id = f"esc:{cid}"
            result.decisions[cid] = decision_id
            self.ledger.structural(
                decision_id, step=SCOPE, subject_ids=[cid], inputs=inputs, outcome=outcome,
                detail={
                    "name": self.clusters.clusters[cid].name,
                    "target": cid in result.target_clusters,
                    "anchor": cid in anchors,
                    "requirements": [
                        {
                            "requirement_id": r.requirement_id,
                            "relationship_type_key": self.index.relationship_types[r.relationship_type_id].key,
                            "counterpart_type_key": self.index.object_types[r.counterpart_type_id].key,
                            "minimum": r.minimum, "satisfied_by": r.satisfiers, "candidates": r.candidates,
                        }
                        for r in requirements
                    ],
                },
            )
        for aid in result.selected_assertions:
            self.ledger.structural(
                f"esc:{aid}", step=SCOPE, subject_ids=[aid], inputs=[self.assertions[aid].decision_id], outcome="selected",
            )
        for aid, reason in result.excluded_assertions.items():
            self.ledger.structural(
                f"esc:{aid}", step=SCOPE, subject_ids=[aid], inputs=[self.assertions[aid].decision_id], outcome=reason,
                question_key=next((q.key("current_satisfier", c, r.rule_id, r.side) for c, r, aids in result.over_asserted if aid in aids), None),
            )


def evidence_selective_closure(graph: EvidenceGraph, clusters: ClusterResult, types, identities, assertions, *, index, frame, targets, anchors, pins, ledger, excluded=(), probe_outcomes=None,
                               unframed=()) -> ScopeResult:
    return _Closure(
        graph, clusters, types, identities, assertions, index=index, frame=frame, targets=targets, anchors=anchors,
        pins=pins, ledger=ledger, excluded=excluded, probe_outcomes=probe_outcomes or {}, unframed=unframed,
    ).run()


# -- removals --------------------------------------------------------------------


@dataclass
class Removal:
    subject: str  # cluster id or aid
    kind: str  # object | relationship
    target_id: str  # canonical id to retire
    question_key: str
    confirmed: bool


def removals(graph: EvidenceGraph, clusters: ClusterResult, types, identities, assertions, scope: ScopeResult, *, index: SemanticModelIndex, pins: dict) -> list[Removal]:
    """Explicit removal claims (polarity=removed) about existing canonical
    entities that are material to the intent. Never inferred from absence;
    each needs a confirmed `removal_confirmation` answer before it compiles."""

    retire_types = {t.type_id for t in scope.targets.values() if t.outcome == "mapped" and t.verb == "retire"}
    found = []
    for cid, cluster in clusters.clusters.items():
        identity = identities[cid]
        if cluster.polarity != "removed" or identity.outcome != "existing":
            continue
        if scope.targets and types[cid].type_id not in retire_types and types[cid].type_id not in {t.type_id for t in scope.targets.values()}:
            continue
        pin_key = q.key("removal_confirmation", cid)
        pin = pins.get(pin_key)
        found.append(Removal(cid, "object", identity.object_id, pin_key, bool(pin and pin.option_id == "confirm")))
    for aid, mapping in assertions.items():
        assertion = graph.assertion(aid)
        if assertion is None or assertion.polarity != "removed" or mapping.outcome != "mapped":
            continue
        subject, obj = identities[mapping.canonical_subject], identities[mapping.canonical_object]
        if subject.outcome != "existing" or obj.outcome != "existing":
            continue
        existing = [r for r in index.relationships_matching(mapping.relationship_type_id, subject.object_id, obj.object_id) if r.is_active]
        if len(existing) != 1:
            continue
        pin_key = q.key("removal_confirmation", aid)
        pin = pins.get(pin_key)
        found.append(Removal(aid, "relationship", existing[0].id, pin_key, bool(pin and pin.option_id == "confirm")))
    return found
