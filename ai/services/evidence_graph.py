"""
The EvidenceGraph: what the supplied sources assert, as explicit, excerpted
claims -- Extraction's output, appended to later by Gap Probes and by
Verification.

INVARIANT (ai/README.md, I1): the EvidenceGraph records extracted evidence. It
is never required to be ontology-valid, and no ontology-derived check may
reject it. An entity may be untyped or carry a non-catalogue `type_label`; an
assertion's `predicate` stays the source's own wording and its
`relationship_type_hint` is a hint, never a constraint. How (and whether) any
of it maps onto the catalogue is a separate overlay
(ai.services.reconcile.mapping) keyed by these ids -- the graph itself is
never rewritten. That is enforced structurally: `validate_evidence_graph`
takes no SemanticModelIndex or catalogue, and this module may not import
ai.services.semantic (ai.tests.test_evidence_graph).

Items carry `origin` (extraction | probe | verifier | reading), which OnyxJar
sets -- never trusted from a provider response. `reading` items are not
extracted by an AI at all: they are the deterministic expansion of a Reading
(an AI's schema-level interpretation of a table or section) over the rows it
conforms to (ai.services.reconcile.readings). Each carries `basis_refs`: EVERY
Reading ("<reading id>@<revision>") needed to reproduce it, so a change to any
of them invalidates it. AI-origin items never carry basis_refs.
"""

from __future__ import annotations

from typing import Literal, Optional

from django.conf import settings
from pydantic import BaseModel, Field

from ai.services.artifacts import Provenance
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.feedback import AIIssue, issue
from ai.services.provenance import check_provenance, excerpt_in_any_source, resolve_segments

Origin = Literal["extraction", "probe", "verifier", "reading", "intent"]


class Qualifiers(BaseModel):
    """What separates two legitimately different observations of the same
    property: when it held, and under what context/condition."""

    as_of: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    context: Optional[str] = None


class EvidenceEntity(BaseModel):
    eid: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    # The source's own word for what kind of thing this is ("venue", "stadium").
    type_label: str
    # Optional catalogue ObjectType key the extractor believes fits -- a hint.
    type_hint: Optional[str] = None
    # generic: the source refers to unidentified instance(s) of a kind
    # ("pool matches") -- evidence, but never compiled into an Object.
    specificity: Literal["specific", "generic"] = "specific"
    polarity: Literal["present", "removed"] = "present"
    provenance: list[Provenance] = Field(default_factory=list)
    origin: Origin = "extraction"
    basis_refs: list[str] = Field(default_factory=list)


class EvidenceAssertion(BaseModel):
    aid: str
    subject_eid: str
    # The source's own wording (or a short paraphrase) of the relationship.
    predicate: str
    object_eid: str
    relationship_type_hint: Optional[str] = None
    # converse: the predicate means the converse of the hinted RelationshipType
    # ("hosts" vs played_at) -- an explicit semantic claim, never inferred.
    hint_orientation: Literal["as_stated", "converse"] = "as_stated"
    # explicit: one cited passage states it. structural: its meaning is
    # conveyed by layout (an item under a heading, a row under a table's
    # caption) -- it must then cite each of those segments. This only changes
    # which citation shapes satisfy grounding (ai.services.grounding); it never
    # changes how the claim maps onto the ontology.
    support: Literal["explicit", "structural"] = "explicit"
    polarity: Literal["present", "removed", "changed"] = "present"
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)
    modality: Literal["stated", "reported", "estimated", "planned"] = "stated"
    provenance: list[Provenance] = Field(default_factory=list)
    origin: Origin = "extraction"
    basis_refs: list[str] = Field(default_factory=list)


class Supersedes(BaseModel):
    # The fid this observation corrects, when it is in the graph.
    target_fid: Optional[str] = None
    # The source wording that says so ("revised", "corrected to").
    excerpt: str


class EvidenceFact(BaseModel):
    fid: str
    # The eid (or aid) the fact is about.
    subject_id: str
    label: str
    value: str
    unit: Optional[str] = None
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)
    modality: Literal["stated", "reported", "estimated", "planned"] = "stated"
    supersedes: Optional[Supersedes] = None
    provenance: list[Provenance] = Field(default_factory=list)
    origin: Origin = "extraction"
    basis_refs: list[str] = Field(default_factory=list)


class EvidenceGraph(BaseModel):
    entities: list[EvidenceEntity] = Field(default_factory=list)
    assertions: list[EvidenceAssertion] = Field(default_factory=list)
    facts: list[EvidenceFact] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.entities or self.assertions or self.facts)

    def items(self) -> list:
        return [*self.entities, *self.assertions, *self.facts]

    def ids(self) -> set[str]:
        return {item_id(item) for item in self.items()}

    def entity(self, eid) -> EvidenceEntity | None:
        return next((e for e in self.entities if e.eid == eid), None)

    def assertion(self, aid) -> EvidenceAssertion | None:
        return next((a for a in self.assertions if a.aid == aid), None)

    def fact(self, fid) -> EvidenceFact | None:
        return next((f for f in self.facts if f.fid == fid), None)

    def item(self, identifier):
        return next((i for i in self.items() if item_id(i) == identifier), None)

    def with_origin(self, origin: str) -> "EvidenceGraph":
        """`origin` is OnyxJar-owned: whatever a provider put there is overwritten."""

        copy = self.model_copy(deep=True)
        for item in copy.items():
            item.origin = origin
            if origin not in ("reading", "intent"):
                item.basis_refs = []
        return copy

    def appended(self, other: "EvidenceGraph") -> "EvidenceGraph":
        """Append-only growth: a new graph with `other`'s items after this one's."""

        copy = self.model_copy(deep=True)
        copy.entities.extend(e.model_copy(deep=True) for e in other.entities)
        copy.assertions.extend(a.model_copy(deep=True) for a in other.assertions)
        copy.facts.extend(f.model_copy(deep=True) for f in other.facts)
        return copy

    def without(self, identifiers) -> "EvidenceGraph":
        identifiers = set(identifiers)
        return EvidenceGraph(
            entities=[e for e in self.entities if e.eid not in identifiers],
            assertions=[a for a in self.assertions if a.aid not in identifiers],
            facts=[f for f in self.facts if f.fid not in identifiers],
        )


def resolve_graph_segments(graph: "EvidenceGraph", bundle: EvidenceBundle) -> "EvidenceGraph":
    """A copy with every provenance item pointed at its segment where that is
    unambiguous (a literal repair -- ai.services.provenance.resolve_segments)."""

    copy = graph.model_copy(deep=True)
    for item in copy.items():
        resolve_segments(item.provenance, bundle=bundle)
    return copy


def cited_segments(item) -> set[str]:
    return {p.segment_id for p in getattr(item, "provenance", []) if getattr(p, "segment_id", None)}


def item_id(item) -> str:
    return getattr(item, "eid", None) or getattr(item, "aid", None) or getattr(item, "fid", None) or ""


def item_provenance(item) -> list[Provenance]:
    return list(getattr(item, "provenance", []) or [])


def validate_evidence_graph(graph: EvidenceGraph, *, bundle: EvidenceBundle, intent_text: str, known_ids=frozenset()) -> list[AIIssue]:
    """
    Structure and provenance only -- deliberately no index/catalogue
    parameter (I1). `known_ids` are ids already in the graph this one is
    being appended to: references to them are valid, reusing them is not.
    """

    issues: list[AIIssue] = []
    items = graph.items()
    if len(items) > settings.AI_EVIDENCE_MAX_ITEMS:
        issues.append(issue("too_many_items", f"At most {settings.AI_EVIDENCE_MAX_ITEMS} evidence items are allowed."))

    counts: dict[str, int] = {}
    for item in items:
        identifier = item_id(item)
        counts[identifier] = counts.get(identifier, 0) + 1
    for identifier, count in counts.items():
        if not identifier.strip():
            issues.append(issue("malformed_item", "Every entity, assertion and fact needs a non-empty id."))
        elif count > 1 or identifier in known_ids:
            issues.append(issue("duplicate_id", f"Id '{identifier}' is used more than once.", item_id=identifier))

    entity_ids = {e.eid for e in graph.entities} | set(known_ids)
    referable = entity_ids | {a.aid for a in graph.assertions} | set(known_ids)
    fact_ids = {f.fid for f in graph.facts} | set(known_ids)

    def check(item, where):
        check_provenance(item.provenance, item_id=item_id(item), where=where, bundle=bundle, intent_text=intent_text, issues=issues)

    for entity in graph.entities:
        where = f"Entity '{entity.eid}'"
        if not entity.name.strip():
            issues.append(issue("malformed_item", f"{where} needs a name.", item_id=entity.eid))
        if not entity.type_label.strip():
            issues.append(issue("malformed_item", f"{where} needs a type_label (the source's word for its kind).", item_id=entity.eid))
        check(entity, where)

    for assertion in graph.assertions:
        where = f"Assertion '{assertion.aid}'"
        for label, endpoint in (("subject", assertion.subject_eid), ("object", assertion.object_eid)):
            if not (endpoint or "").strip():
                # Typically a list squeezed into one predicate ("includes the
                # teams A, B and C"): correctable, never a silent drop.
                issues.append(issue(
                    "missing_endpoint",
                    f"{where} has no {label}. An assertion relates exactly two entities: state one assertion per "
                    "counterpart (each member of a list is its own assertion), extracting any entity that is missing.",
                    item_id=assertion.aid,
                ))
            elif endpoint not in entity_ids:
                issues.append(issue("dangling_reference", f"{where}: {label} '{endpoint}' is not an entity.", item_id=assertion.aid))
        if (assertion.subject_eid or "").strip() and assertion.subject_eid == assertion.object_eid:
            # Typically the entity the predicate names was never extracted --
            # it lives only in the predicate's wording.
            issues.append(issue(
                "self_reference",
                f"{where} relates '{assertion.subject_eid}' to itself. If the source names a separate entity the predicate "
                "refers to, extract that entity under the name the source uses and relate to it; if the source does not "
                "name one, withdraw the claim. An entity must never live only in predicate text.",
                item_id=assertion.aid,
            ))
        if not assertion.predicate.strip():
            issues.append(issue("malformed_item", f"{where} needs a predicate.", item_id=assertion.aid))
        check(assertion, where)

    for fact in graph.facts:
        where = f"Fact '{fact.fid}'"
        if not (fact.subject_id or "").strip():
            issues.append(issue("missing_endpoint", f"{where} has no subject: name the entity or assertion it describes.", item_id=fact.fid))
        elif fact.subject_id not in referable:
            issues.append(issue("dangling_reference", f"{where}: subject '{fact.subject_id}' is not an entity or assertion.", item_id=fact.fid))
        if not fact.label.strip():
            issues.append(issue("malformed_item", f"{where} needs a label.", item_id=fact.fid))
        if fact.supersedes is not None:
            if fact.supersedes.target_fid and fact.supersedes.target_fid not in fact_ids:
                issues.append(issue("dangling_reference", f"{where}: supersedes unknown fact '{fact.supersedes.target_fid}'.", item_id=fact.fid))
            if not excerpt_in_any_source(fact.supersedes.excerpt, bundle=bundle, intent_text=intent_text):
                issues.append(issue("excerpt_not_found", f"{where}: the supersedes excerpt must quote the source.", item_id=fact.fid))
        check(fact, where)

    return issues
