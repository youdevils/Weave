"""
Typed Adjudication questions and the pinned answers that resolve them.

Wherever Reconcile needs a judgement OnyxJar cannot make (I2) -- which of
several types/relationship types/attributes a claim means, whether a
predicate is a converse, whether two mentions are one entity, whether
differing values contradict, which value is current -- the deterministic
pipeline records the decision as `ambiguous` and emits a Question whose
options OnyxJar generated. An answer (from Adjudication, a Gap Probe remap or
a Verification objection) becomes a Pin: a claim, keyed by the question, that
every later recomputation honours. Every question also offers "undecidable",
so ambiguity is preserved rather than forced (I4).

A question the Adjudication budget never reached is NOT pinned: it stays
open (its decision stays `ambiguous`, so nothing resting on it compiles) and
is reported as unadjudicated; a later round may still answer it. The only
non-claim pin is `rejected_answer` -- an answer that failed validation twice,
never re-asked -- and it is invisible to the deterministic layers
(`claim_pins`), so it can never displace a hint or lexical basis.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

NONE = "none"
UNDECIDABLE = "undecidable"
NEW = "new"


class QuestionOption(BaseModel):
    option_id: str
    label: str
    detail: str = ""


class Question(BaseModel):
    question_id: str  # == the pin key, "<kind>:<subject>"
    kind: str
    subject_ids: list[str] = Field(default_factory=list)
    prompt: str
    options: list[QuestionOption] = Field(default_factory=list)
    excerpts: list[str] = Field(default_factory=list)

    def option_ids(self) -> set[str]:
        return {o.option_id for o in self.options}


@dataclass(frozen=True)
class Pin:
    option_id: str
    basis: str  # adjudicated | probe | verifier | rejected_answer
    # rejected_answer: why the (twice-invalid) answer was refused.
    reason: str = ""
    excerpt: str = ""
    note: str = ""


def key(kind, *subject) -> str:
    return ":".join([kind, *map(str, subject)])


def pin_decision_id(question_key) -> str:
    return f"adj:{question_key}"


# OnyxJar defaults, never claims: they make nothing compilable and never take
# part in mapping, identity or scope.
NON_CLAIM_BASES = frozenset({"budget", "rejected_answer"})


def is_claim(pin) -> bool:
    return pin is not None and pin.basis not in NON_CLAIM_BASES


def claim_pins(pins) -> dict:
    """The pins the deterministic pipeline honours: claimed answers only."""

    return {key: pin for key, pin in pins.items() if is_claim(pin)}


def pin_inputs(question_key, pins) -> list[str]:
    """The claim decision a pinned answer contributes as an input -- none for
    a non-claim default, which never makes anything compilable."""

    return [pin_decision_id(question_key)] if is_claim(pins.get(question_key)) else []


def standard_options(options, *, allow_none=True) -> list[QuestionOption]:
    result = list(options)
    if allow_none:
        result.append(QuestionOption(option_id=NONE, label="None of these"))
    result.append(QuestionOption(option_id=UNDECIDABLE, label="Cannot be decided from the evidence"))
    return result


# Question kinds in the order they must be settled: an entity's type decides
# which relationship/attribute options exist at all, so type-level questions
# are asked in a round of their own when present.
PHASE_1 = ("target_type", "coreference", "entity_type")
PHASE_2 = ("assertion_mapping", "indirect_classification", "identity", "fact_attribute", "conflict_classification",
           "value_selection", "value_change", "removal_confirmation", "current_satisfier")
