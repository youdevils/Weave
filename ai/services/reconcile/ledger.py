"""
The Decision Ledger: every interpretation Reconcile makes, as an auditable
decision with stable id, the step that produced it, what it rests on, and
its outcome. It replaces the old CandidateSet dispositions, is what
Verification reviews (and objects to, by decision id), and is the backbone
of the Semantic Claim Invariant:

    I2. OnyxJar may derive structural consequences from explicit evidence
        claims and known ontology rules, but must never create a semantic
        claim that was not explicitly extracted from evidence or explicitly
        asserted through an AI step.

Every decision is a `claim` (made by an AI step -- Extraction, Gap Probe,
Adjudication, Verification, Framing -- always with an excerpt), `structural`
(computed by OnyxJar), or `coverage` (a workflow decision about which
evidence was examined -- a dismissed or uncovered segment, a probe verdict).
A structural decision must rest, transitively through `inputs`, on at least
one claim: `i2_violations()` reports any that don't. A coverage decision is
never a claim: it says nothing about the domain and never makes anything
"rest on a claim". Evidence items themselves are registered as claim
decisions under their own ids.

Decision ids are stable across recomputation ("map:A3", "ident:C1", ...),
so a Verification objection that names one still means the same thing after
the pipeline re-runs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Kind = Literal["claim", "structural", "coverage"]

# Steps -> where a Verification objection on a decision of that step re-enters.
EXTRACTION, FRAMING, NORMALISE, MAPPING, IDENTITY, SCOPE, ADJUDICATION, PROBE, VERIFIER, COMPILE, GROUNDING, COVERAGE = (
    "extraction", "framing", "normalise", "mapping", "identity", "scope", "adjudication", "probe", "verifier", "compile",
    "grounding", "coverage",
)


@dataclass
class Decision:
    decision_id: str
    step: str
    kind: Kind
    # lexical | hint | extraction | adjudicated | probe | verifier | framing | deterministic
    basis: str
    subject_ids: tuple = ()
    inputs: tuple = ()
    outcome: str = ""
    options: list = field(default_factory=list)
    # The three layers a non-compiled mapping records (C3): what the source
    # says, how it maps to the ontology, and why it is not directly compilable.
    source: dict | None = None
    mapping: dict | None = None
    reason: str | None = None
    excerpts: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    # The Adjudication question key whose pinned answer would override this
    # decision (how objections and probe remaps are routed back in).
    question_key: str | None = None

    def payload(self) -> dict:
        data = {k: v for k, v in asdict(self).items() if v not in (None, [], {}, (), "")}
        data["subject_ids"] = list(self.subject_ids)
        data["inputs"] = list(self.inputs)
        return data


class Ledger:

    def __init__(self):
        self.decisions: dict[str, Decision] = {}

    def add(self, decision: Decision) -> Decision:
        self.decisions[decision.decision_id] = decision
        return decision

    def get(self, decision_id) -> Decision | None:
        return self.decisions.get(decision_id)

    def claim(self, decision_id, *, step, basis, subject_ids=(), inputs=(), outcome="asserted", excerpts=(), **kwargs) -> Decision:
        return self.add(
            Decision(
                decision_id=decision_id, step=step, kind="claim", basis=basis, subject_ids=tuple(subject_ids),
                inputs=tuple(inputs), outcome=outcome, excerpts=list(excerpts), **kwargs,
            )
        )

    def coverage(self, decision_id, *, step, basis, subject_ids=(), inputs=(), outcome="", **kwargs) -> Decision:
        return self.add(
            Decision(
                decision_id=decision_id, step=step, kind="coverage", basis=basis, subject_ids=tuple(subject_ids),
                inputs=tuple(inputs), outcome=outcome, **kwargs,
            )
        )

    def structural(self, decision_id, *, step, basis="deterministic", subject_ids=(), inputs=(), outcome="", **kwargs) -> Decision:
        return self.add(
            Decision(
                decision_id=decision_id, step=step, kind="structural", basis=basis, subject_ids=tuple(subject_ids),
                inputs=tuple(inputs), outcome=outcome, **kwargs,
            )
        )

    def rests_on_claim(self, decision_id, _seen=None) -> bool:
        seen = _seen if _seen is not None else set()
        if decision_id in seen:
            return False
        seen.add(decision_id)
        decision = self.decisions.get(decision_id)
        if decision is None:
            return False
        if decision.kind == "claim":
            return True
        if decision.kind == "coverage":
            return False
        return any(self.rests_on_claim(i, seen) for i in decision.inputs)

    def i2_violations(self) -> list[str]:
        return [d.decision_id for d in self.decisions.values() if d.kind == "structural" and not self.rests_on_claim(d.decision_id)]

    def dependants(self, decision_id) -> set[str]:
        """Every decision that (transitively) rests on `decision_id`."""

        result, frontier = set(), {decision_id}
        while frontier:
            frontier = {d.decision_id for d in self.decisions.values() if set(d.inputs) & frontier} - result
            result |= frontier
        return result

    def payload(self, *, steps=None) -> list[dict]:
        return [d.payload() for d in self.decisions.values() if steps is None or d.step in steps]
