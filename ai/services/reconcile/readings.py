"""
Readings: the AI's schema-level semantic interpretation of document structure,
and its deterministic expansion (.Documentation/reconcile-architecture-plan.md,
Phase 2; ai/README.md).

    DEM (structure) -> Reading (meaning, once per table/section schema)
        -> expansion (every conforming row) -> EvidenceGraph claims
           (origin=reading, basis_refs) -> the unchanged governance core

A Reading is made of SLOTS that OnyxJar lays out from the DEM (`skeleton`)
and the AI fills, each from OnyxJar-offered options plus `none` /
`undecidable`, citing its structural basis:

    role:<col>              what a column's cells are (an entity of a
                            catalogue type -- specific or generic --, a
                            value, or nothing)
    split:<col>             for a column whose cells all carry one separator
                            (a DEM fact): what the parts are, and how each
                            relates to the cell's own entity
    relation:<a>><b>        which catalogue relationship (and orientation)
                            the layout states between two columns' entities
    heading_entity          whether a heading itself names an entity
    section_relation        (optional, by omission `none`) a relationship
                            between a heading's entity and a column's
                            entities in a table under it

Invariants this module carries (plan, "Architectural invariants"):

- Reading-derived claims are ALREADY MAPPED: the selected catalogue
  identities travel in the `ReadingOverlay`, and analysis takes their type /
  map decisions from it (basis `reading`) -- never through lexical, hint or AI
  mapping (invariant 15). `mapping.direct_options` is used only to offer and
  validate options.
- Expansion never invents meaning: no Reading, no claim (`expand(dem, [])`
  is empty -- invariant 3). Every expanded claim lists in `basis_refs` every
  Reading it depends on (invariant 4), and is ledgered `structural` over those
  Readings' `read:` slot claims.
- A row is expanded only if it passes `structurally_conforms` (DEM) and
  `reading_conforms` (here): DEM structural facts plus the exceptions the
  Reading DECLARED -- never a fresh interpretation of raw strings
  (invariants 5, 17). Text overlap alone is never an anomaly.
- Ownership is explicit and element-level (`owns`), and prose eligibility
  is decided by the DEM's classification: structured content reaches claims
  only through a validated Reading; only `not_a_table` returns it to prose
  (invariants 10, 12, 16).
- Correction happens at slot level: a pin on `reading_slot:<slot id>` (an
  Adjudication answer, or a reviewer's objection to `read:<slot id>`)
  replaces the slot's choice, bumps the Reading's revision and re-expands
  every row it governs (invariant 9). Readings are recomputed into claims on
  every analysis, so superseded claims simply stop existing.

Ids (deterministic -- invariant 18):

    Reading            rd/<table or heading segment id>
    slot               rd/<element>/role/c2 | /split/c2 | /relation/c1>c2 |
                       /heading_entity | /section_relation/<column id>
    entity             x/<cell id> | x/<cell id>/p<k> (a split part) |
                       x/<heading segment id>
    assertion          x/<row id>/<a>><b> | x/<cell id>/p<k>/rel |
                       x/<heading id>/<cell id>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from django.conf import settings
from pydantic import BaseModel, Field

from ai.services.artifacts import Provenance
from ai.services.document.queries import structurally_conforms
from ai.services.evidence_bundle import excerpt_occurs
from ai.services.evidence_graph import EvidenceAssertion, EvidenceEntity, EvidenceGraph
from ai.services.feedback import AIIssue, issue
from ai.services.reconcile import questions as q
from ai.services.reconcile.mapping import AS_STATED, CONVERSE, direct_options
from ai.services.reconcile.normalise import singular
from ai.services.sources import tokens

READING, READ = "reading", "read"
VALUE, NONE, UNDECIDABLE = "value", q.NONE, q.UNDECIDABLE
NOT_A_TABLE = "not_a_table"
NOT_A_TABLE_REASONS = ("layout_grid", "form", "decorative_alignment", "unusable_recovery")
EXCEPTION_KINDS = ("placeholder", "generic", "role_conflict", "ontology_contradiction", "other")
RESERVED = (NONE, UNDECIDABLE)
# A role choice "generic:<type key>": the column's cells refer to unidentified
# instances of the type -- an explicit, justified decision, never a default.
GENERIC_PREFIX = "generic:"


# -- the Reading model ------------------------------------------------------------------


class SlotBasis(BaseModel):
    """A structural citation: a DEM id (cell, column, table/row/heading
    segment) and verbatim text of it."""

    dem_id: str
    excerpt: str


class Slot(BaseModel):
    slot_id: str
    kind: Literal["role", "split", "relation", "heading_entity", "section_relation"]
    # role/split: [column]; relation: [a, b]; section_relation: [column].
    columns: list[str] = Field(default_factory=list)
    heading_id: Optional[str] = None
    separator: Optional[str] = None
    # The advisory shortlist OnyxJar offered (ranked; never the closed universe).
    options: list[str] = Field(default_factory=list)
    # A catalogue key, "<relationship key>:<orientation>", "value", "none",
    # "undecidable" -- or None while unanswered.
    choice: Optional[str] = None
    specificity: Literal["specific", "generic"] = "specific"
    # split: how the cell's entity (subject) relates to each part.
    part_relation: Optional[str] = None
    state: Literal["decided", "undecidable", "pending", "rejected"] = "pending"
    set_by: str = READING
    basis: list[SlotBasis] = Field(default_factory=list)


class RowException(BaseModel):
    exception_id: str
    row_ids: list[str] = Field(default_factory=list)
    slot_id: str
    kind: str
    state: Literal["decided", "undecidable"] = "decided"
    reason: str = ""


class Reading(BaseModel):
    reading_id: str
    element_kind: Literal["table", "section"]
    element_id: str
    dem_digest: str = ""
    status: Literal["proposed", "validated", "not_a_table", "superseded", "rejected"] = "proposed"
    not_a_table_reason: Optional[str] = None
    basis: list[SlotBasis] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)
    exceptions: list[RowException] = Field(default_factory=list)
    # Readings whose output a slot consumes read-only (section_relation -> table).
    references: list[str] = Field(default_factory=list)
    # DEM ids this Reading explicitly interprets (plan, section 3.2a).
    owns: list[str] = Field(default_factory=list)
    revision: int = 1
    history: list[dict] = Field(default_factory=list)

    def slot(self, slot_id) -> Slot | None:
        return next((s for s in self.slots if s.slot_id == slot_id), None)


def reading_id(element_id: str) -> str:
    return f"rd/{element_id}"


def _short(column_id: str) -> str:
    return column_id.rsplit(".", 1)[-1]


def slot_decision_id(slot_id: str) -> str:
    return f"read:{slot_id}"


def slot_question_key(slot_id: str) -> str:
    return q.key("reading_slot", slot_id)


def exception_question_key(exception_id: str) -> str:
    return q.key("row_exception", exception_id)


# -- candidate options (recall, never lexical exclusion) ------------------------------


def _similarity(label: str, *names) -> int:
    wanted = set(tokens(label))
    return max((len(wanted & set(tokens(n))) for n in names if n), default=0)


def type_options(index, label: str) -> list[str]:
    """Every active ObjectType, ranked by lexical similarity to `label`
    (ranking only: a type that doesn't resemble the label is still offered,
    and a key outside the shortlist is still accepted -- `resolve_type`)."""

    active = [t for t in index.object_types.values() if t.is_active]
    ranked = sorted(active, key=lambda t: (-_similarity(label, t.name, t.key.replace("_", " ")), t.key))
    return [t.key for t in ranked][: settings.AI_READING_MAX_OPTIONS]


def relation_options(index, *labels) -> list[str]:
    """Every (active RelationshipType, orientation) some rule allows, ranked
    by similarity to the column labels."""

    found = []
    for relationship_type in index.relationship_types.values():
        if not relationship_type.is_active:
            continue
        if any(rule.relationship_type_id == relationship_type.id for rule in index.rules.values()):
            score = max((_similarity(label, relationship_type.name, relationship_type.key.replace("_", " ")) for label in labels), default=0)
            found += [(-score, relationship_type.key, f"{relationship_type.key}:{AS_STATED}"),
                      (-score, relationship_type.key, f"{relationship_type.key}:{CONVERSE}")]
    return [option for *_, option in sorted(found)][: 2 * settings.AI_READING_MAX_OPTIONS]


def resolve_type(index, key):
    item = index.object_type_by_key(key) if key else None
    return item if item is not None and item.is_active else None


def resolve_relation(index, value):
    """'played_at:converse' -> (relationship type, orientation) or None --
    validated against the FULL catalogue (the escape valve)."""

    key, _, orientation = str(value or "").partition(":")
    item = index.relationship_type_by_key(key)
    if item is None or not item.is_active or orientation not in (AS_STATED, CONVERSE):
        return None
    return item, orientation


# -- the skeleton: which slots a document's structure asks about ---------------------


@dataclass
class Element:
    element_id: str
    kind: str  # table | section
    slots: list
    payload: dict
    size: int = 0


def _sample_rows(table, limit: int) -> list:
    """All rows when few; otherwise the first `limit` plus every structural
    outlier (a row atypical of the table's signature, or with a cell whose
    length deviates strongly from its column) -- a statistical, structural
    selection, never a semantic one."""

    rows = list(table.rows)
    if len(rows) <= limit:
        return rows
    lengths = {}
    for row in rows:
        for cell in row.cells:
            lengths.setdefault(cell.column_id, []).append(len(tokens(cell.text)))
    medians = {c: sorted(v)[len(v) // 2] for c, v in lengths.items()}

    def outlier(row):
        if not structurally_conforms(row, table.signature).conforms:
            return True
        return any(len(tokens(c.text)) > 2 * medians.get(c.column_id, 0) + 2 or (not c.text.strip()) != (medians.get(c.column_id, 0) == 0)
                   for c in row.cells)

    chosen = rows[:limit]
    return chosen + [r for r in rows[limit:] if outlier(r)]


def skeleton(document, bundle, index) -> list[Element]:
    """Every table, and every heading a table sits under, as an Element with
    the slots a Reading of it must fill and the payload the AI is shown."""

    elements = []
    limit = settings.AI_READING_SAMPLE_ROWS
    headings_used = []
    for table in sorted(document.tables.values(), key=lambda t: (t.source_id, bundle.segment(t.table_id).position)):
        rid = reading_id(table.table_id)
        slots = []
        for column in table.columns:
            label = column.label or " ".join(bundle.segment(h).text for h in table.ancestor_ids[-1:])
            slots.append(Slot(slot_id=f"{rid}/role/{_short(column.column_id)}", kind="role", columns=[column.column_id],
                              options=[*type_options(index, label), VALUE, NONE, UNDECIDABLE]))
            separator = table.signature.separator(column.column_id)
            if separator:
                slots.append(Slot(slot_id=f"{rid}/split/{_short(column.column_id)}", kind="split", columns=[column.column_id],
                                  separator=separator, options=[*type_options(index, ""), NONE, UNDECIDABLE]))
        for i, a in enumerate(table.columns):
            for b in table.columns[i + 1:]:
                slots.append(Slot(slot_id=f"{rid}/relation/{_short(a.column_id)}>{_short(b.column_id)}", kind="relation",
                                  columns=[a.column_id, b.column_id],
                                  options=[*relation_options(index, a.label, b.label), NONE, UNDECIDABLE]))
        rows = _sample_rows(table, limit)
        payload = {
            "element_id": table.table_id, "kind": "table",
            "within": [{"segment_id": h, "text": bundle.segment(h).text} for h in table.ancestor_ids],
            "columns": [{"column_id": c.column_id, "label": c.label,
                         **({"recurring_separator": table.signature.separator(c.column_id)} if table.signature.separator(c.column_id) else {})}
                        for c in table.columns],
            "rows": [{"row_id": r.row_id, "cells": [{"cell_id": c.cell_id, "text": c.text} for c in r.cells]} for r in rows],
            "rows_total": len(table.rows), "rows_shown": len(rows),
            "slots": [_slot_payload(s) for s in slots],
        }
        elements.append(Element(table.table_id, "table", slots, payload))
        headings_used += [h for h in table.ancestor_ids if h not in headings_used]

    for heading_id in headings_used:
        heading = bundle.segment(heading_id)
        rid = reading_id(heading_id)
        slot = Slot(slot_id=f"{rid}/heading_entity", kind="heading_entity", heading_id=heading_id,
                    options=[*type_options(index, heading.text), NONE, UNDECIDABLE])
        below = [t for t in document.tables.values() if heading_id in t.ancestor_ids]
        payload = {
            "element_id": heading_id, "kind": "section",
            "heading": {"segment_id": heading_id, "text": heading.text},
            "within": [{"segment_id": a, "text": bundle.segment(a).text} for a in heading.ancestor_ids],
            "tables_below": [{"table_id": t.table_id, "columns": [{"column_id": c.column_id, "label": c.label} for c in t.columns]} for t in below],
            "slots": [_slot_payload(slot)],
            "section_relation_options": relation_options(index, heading.text),
        }
        elements.append(Element(heading_id, "section", [slot], payload))

    for element in elements:
        element.size = len(str(element.payload))
    return elements


def _slot_payload(slot: Slot) -> dict:
    data = {"slot_id": slot.slot_id, "kind": slot.kind, "options": slot.options}
    if slot.columns:
        data["columns"] = slot.columns
    if slot.separator:
        data["separator"] = slot.separator
    if slot.heading_id:
        data["heading_id"] = slot.heading_id
    return data


def plan_reading_batches(elements: list[Element], max_chars: int) -> list[list[str]]:
    batches, current, used = [], [], 0
    for element in elements:
        if current and used + element.size > max_chars:
            batches.append(current)
            current, used = [], 0
        current.append(element.element_id)
        used += element.size
    if current:
        batches.append(current)
    return batches


# -- validating a Reading response ------------------------------------------------------


def dem_text(dem_id, document, bundle) -> str | None:
    if dem_id in document.cells:
        return document.cells[dem_id].text
    if dem_id in document.columns:
        return document.columns[dem_id].label
    segment = bundle.segment(dem_id)
    return segment.text if segment is not None else None


def _basis_issues(where, basis, document, bundle) -> list[str]:
    problems = []
    for citation in basis:
        text = dem_text(citation.dem_id, document, bundle)
        if text is None:
            problems.append(f"{where}: '{citation.dem_id}' is not a cell, column or segment id shown.")
        elif not excerpt_occurs(citation.excerpt, text):
            problems.append(f"{where}: \"{citation.excerpt[:80]}\" does not occur in '{citation.dem_id}'.")
    return problems


def basis_sufficient(slot: Slot, basis, document, bundle) -> bool:
    """The plan's basis rule (section 3.2): header (or, headerless, section /
    ancestor context) plus representative cells -- or, with no data rows,
    the header / section context alone. Nothing is fabricated: a structure
    with neither gives no sufficient basis for a role."""

    cited = {b.dem_id for b in basis}
    if slot.kind in ("heading_entity",):
        return slot.heading_id in cited
    table = None
    for column_id in slot.columns:
        column = document.columns.get(column_id)
        if column is not None:
            table = document.tables[column.table_id]
    if table is None:
        return bool(cited)
    context = {table.table_id, *(c.column_id for c in table.columns if c.label), *table.ancestor_ids}
    if slot.kind == "section_relation" and slot.heading_id:
        context.add(slot.heading_id)
    cells = {c.cell_id for r in table.rows for c in r.cells}
    has_context = bool(cited & context)
    if not table.rows:
        return has_context and table.has_header
    return has_context and bool(cited & cells)


@dataclass
class ReadingAnswerSet:
    readings: list = field(default_factory=list)
    issues: list = field(default_factory=list)  # [AIIssue] keyed by element id


def apply_result(result, elements: dict, document, bundle, index, *, final: bool) -> ReadingAnswerSet:
    """Validate a ReadingResult for the batch's `elements` ({element id:
    Element}). -> the Readings that validated, and shape issues per element.
    With `final` (the batch's one re-ask is spent), an invalid slot settles
    as `undecidable` (rejected) instead of being re-asked."""

    answers = {r.element_id: r for r in result.readings}
    out = ReadingAnswerSet()
    for element_id, element in elements.items():
        answer = answers.get(element_id)
        if answer is None:
            if final:
                out.readings.append(_unanswered(element, document))
            else:
                out.issues.append(issue("unanswered_element", f"Read element '{element_id}': answer every slot.", item_id=element_id))
            continue
        reading, problems = _validate_element(element, answer, document, bundle, index)
        if problems and not final:
            out.issues.append(issue("invalid_reading", f"Element '{element_id}': " + " ".join(problems[:6]), item_id=element_id))
            continue
        if problems:
            reading.history.append({"revision": reading.revision, "rejected": problems[:6]})
        out.readings.append(reading)
    return out


def _unanswered(element, document) -> Reading:
    slots = [s.model_copy(update={"state": "rejected", "choice": None}) for s in element.slots]
    return Reading(reading_id=reading_id(element.element_id), element_kind=element.kind, element_id=element.element_id,
                   dem_digest=document.digest, status="rejected", slots=slots)


def _validate_element(element, answer, document, bundle, index):
    rid = reading_id(element.element_id)
    reading = Reading(reading_id=rid, element_kind=element.kind, element_id=element.element_id, dem_digest=document.digest)
    problems = []
    if answer.status == NOT_A_TABLE:
        if element.kind != "table":
            problems.append("only a table can be not_a_table.")
        if answer.not_a_table_reason not in NOT_A_TABLE_REASONS:
            problems.append(f"not_a_table needs a reason, one of {', '.join(NOT_A_TABLE_REASONS)}; it is never a substitute "
                            "for 'none' or 'undecidable' in a valid table.")
        basis = [SlotBasis(dem_id=b.dem_id, excerpt=b.excerpt) for b in answer.basis]
        if not basis:
            problems.append("not_a_table needs a structural basis (cite what shows the structure is unusable).")
        problems += _basis_issues("not_a_table", basis, document, bundle)
        if problems:
            reading.status = "rejected"
            reading.slots = [s.model_copy(update={"state": "rejected"}) for s in element.slots]
            return reading, problems
        reading.status, reading.not_a_table_reason, reading.basis = NOT_A_TABLE, answer.not_a_table_reason, basis
        reading.slots = [s.model_copy(update={"state": "rejected"}) for s in element.slots]
        return reading, []

    given = {a.slot_id: a for a in answer.slots}
    roles: dict[str, object] = {}  # column id -> ObjectType for decided entity roles
    slots = []
    for template in element.slots:
        slot = template.model_copy(deep=True)
        found = given.get(slot.slot_id)
        if found is None:
            problems.append(f"slot '{slot.slot_id}' was not answered.")
            slot.state = "rejected"
            slots.append(slot)
            continue
        slot.choice = (found.choice or "").strip()
        # Specificity is a role decision only, and specific by default: a
        # column is generic only by an explicit, justified generic choice.
        slot.specificity = "specific"
        generic_problem = None
        if slot.choice.startswith(GENERIC_PREFIX):
            if slot.kind != "role":
                generic_problem = f"{slot.slot_id}: only a role slot can be generic."
            elif not (found.generic_reason or "").strip():
                generic_problem = (f"{slot.slot_id}: a generic reading needs generic_reason -- why the cells name no identifiable "
                                   "entity. Cells that name things (even all things of one kind) are the plain type key.")
            slot.choice, slot.specificity = slot.choice[len(GENERIC_PREFIX):].strip(), "generic"
        slot.part_relation = (found.part_relation or None)
        slot.basis = [SlotBasis(dem_id=b.dem_id, excerpt=b.excerpt) for b in found.basis]
        own = [generic_problem] if generic_problem else []
        if slot.choice == UNDECIDABLE:
            slot.state = "undecidable"
        else:
            own += _basis_issues(slot.slot_id, slot.basis, document, bundle)
            if not basis_sufficient(slot, slot.basis, document, bundle):
                own.append(f"{slot.slot_id}: cite its structural basis -- the header (or, with no header, the section heading) "
                           "and at least one cell of the column(s) it interprets.")
            if slot.kind in ("role", "heading_entity") and slot.choice not in (VALUE, NONE):
                type_item = resolve_type(index, slot.choice)
                if type_item is None or (slot.kind == "heading_entity" and slot.choice == VALUE):
                    own.append(f"{slot.slot_id}: '{slot.choice}' is not an active catalogue type key (or value / none / undecidable).")
                elif slot.kind == "role":
                    roles[slot.columns[0]] = type_item
                elif _names_its_kind(bundle.segment(slot.heading_id).text, type_item):
                    own.append(f"{slot.slot_id}: the heading '{bundle.segment(slot.heading_id).text}' names the kind {type_item.name}, "
                               "not one entity of it -- answer 'none'.")
            if slot.kind == "split" and slot.choice != NONE:
                if resolve_type(index, slot.choice) is None:
                    own.append(f"{slot.slot_id}: '{slot.choice}' is not an active catalogue type key.")
                elif resolve_relation(index, slot.part_relation) is None:
                    own.append(f"{slot.slot_id}: give part_relation as '<relationship key>:as_stated|converse' (the cell's entity is the subject).")
            if slot.kind == "relation" and slot.choice != NONE and resolve_relation(index, slot.choice) is None:
                own.append(f"{slot.slot_id}: '{slot.choice}' is not '<relationship key>:as_stated|converse', none or undecidable.")
            slot.state = "rejected" if own else "decided"
            problems += own
        slots.append(slot)

    # Legality of relationships against the roles decided in the same Reading.
    for slot in slots:
        if slot.state != "decided":
            continue
        if slot.kind == "relation" and slot.choice != NONE:
            subject_type, object_type = roles.get(slot.columns[0]), roles.get(slot.columns[1])
            legal = _legal(index, slot.choice, subject_type, object_type)
            if legal is not None:
                problems.append(f"{slot.slot_id}: {legal}")
                slot.state = "rejected"
        if slot.kind == "split" and slot.choice != NONE:
            legal = _legal(index, slot.part_relation, roles.get(slot.columns[0]), resolve_type(index, slot.choice))
            if legal is not None:
                problems.append(f"{slot.slot_id}: {legal}")
                slot.state = "rejected"

    reading.slots = slots
    for item in answer.exceptions:
        table = document.tables.get(element.element_id)
        rows = [r for r in item.row_ids if table is not None and r in {row.row_id for row in table.rows}]
        if not rows or reading.slot(item.slot_id) is None or item.kind not in EXCEPTION_KINDS:
            problems.append(f"exception on '{item.slot_id}': name rows of this table, one of its slots, and a kind ({', '.join(EXCEPTION_KINDS)}).")
            continue
        reading.exceptions.append(RowException(
            exception_id=f"{item.slot_id}/{item.kind}", row_ids=rows, slot_id=item.slot_id, kind=item.kind,
            state="decided" if item.decided else "undecidable", reason=item.reason or ""))

    if element.kind == "section":
        for relation in answer.section_relations:
            column = document.columns.get(relation.column_id)
            if column is None or element.element_id not in document.tables[column.table_id].ancestor_ids:
                problems.append(f"section relation to '{relation.column_id}': name a column of a table under this heading.")
                continue
            slot = Slot(slot_id=f"{reading.reading_id}/section_relation/{relation.column_id}", kind="section_relation",
                        columns=[relation.column_id], heading_id=element.element_id, choice=relation.choice.strip(),
                        basis=[SlotBasis(dem_id=b.dem_id, excerpt=b.excerpt) for b in relation.basis])
            own = _basis_issues(slot.slot_id, slot.basis, document, bundle)
            if relation.choice.strip() == UNDECIDABLE:
                slot.state = "undecidable"
            elif resolve_relation(index, slot.choice) is None:
                own.append(f"{slot.slot_id}: '{slot.choice}' is not '<relationship key>:as_stated|converse' or undecidable.")
            elif not basis_sufficient(slot, slot.basis, document, bundle):
                own.append(f"{slot.slot_id}: cite the heading and a cell of the column.")
            slot.state = "rejected" if own else ("undecidable" if slot.choice == UNDECIDABLE else "decided")
            problems += own
            reading.slots.append(slot)
            reading.references = sorted({*reading.references, reading_id(column.table_id)})

    reading.status = "validated"
    reading.owns = _owns(reading, document)
    return reading, problems


def _names_its_kind(text, type_item) -> bool:
    """A heading whose words are just the type's own name ('Venues' for
    Venue) labels a kind; it names no entity of it."""

    words = tokens(text)
    return bool(words) and words in (tokens(type_item.name), tokens(type_item.key.replace("_", " ")))


def _legal(index, value, subject_type, object_type) -> str | None:
    """None when `value` is a legal relationship between the two types."""

    resolved = resolve_relation(index, value)
    if resolved is None:
        return f"'{value}' is not a catalogue relationship."
    if subject_type is None or object_type is None:
        return "a relationship needs both ends to be entity columns of a catalogue type."
    relationship_type, orientation = resolved
    if (relationship_type.id, orientation) not in direct_options(index, subject_type.id, object_type.id):
        return (f"'{value}' is not legal between {subject_type.key} and {object_type.key} "
                f"(legal: {', '.join(f'{index.relationship_types[r].key}:{o}' for r, o in direct_options(index, subject_type.id, object_type.id)) or 'none'}).")
    return None


def _owns(reading: Reading, document) -> list[str]:
    """Exactly the DEM elements the Reading interprets (plan, section 3.2a)."""

    if reading.status != "validated":
        return []
    owned = []
    if reading.element_kind == "table":
        table = document.tables[reading.element_id]
        slotted = {c for s in reading.slots if s.kind in ("role", "split", "relation") for c in s.columns}
        owned.append(table.table_id)
        for column in table.columns:
            if column.column_id in slotted:
                owned.append(column.column_id)
                owned += [c.cell_id for r in table.rows for c in r.cells if c.column_id == column.column_id]
    else:
        heading = next((s for s in reading.slots if s.kind == "heading_entity"), None)
        if heading is not None and heading.state == "decided" and heading.choice not in (NONE, VALUE):
            owned.append(reading.element_id)
    return owned


# -- pins: slot-level correction -------------------------------------------------------


def effective(readings: list, pins: dict) -> list:
    """The Readings as their latest claims make them: a claimed pin on a slot
    (`reading_slot:<slot id>`) or an exception (`row_exception:<id>`)
    replaces that choice and bumps the revision."""

    result = []
    for reading in readings:
        reading = reading.model_copy(deep=True)
        changes = 0
        for slot in reading.slots:
            pin = pins.get(slot_question_key(slot.slot_id))
            if pin is None or not q.is_claim(pin):
                continue
            changes += 1
            slot.choice, slot.specificity = pin.option_id, "specific"
            if slot.kind == "role" and pin.option_id.startswith(GENERIC_PREFIX):
                slot.choice, slot.specificity = pin.option_id[len(GENERIC_PREFIX):], "generic"
            slot.set_by = pin.basis
            slot.state = "undecidable" if pin.option_id == UNDECIDABLE else "decided"
        if reading.element_kind == "section" and reading.status == "validated":
            # A section relation the Reading left out (none by omission) and a
            # challenge then decided: the answer is the slot.
            prefix = slot_question_key(f"{reading.reading_id}/section_relation/")
            present = {s.slot_id for s in reading.slots}
            for key, pin in sorted(pins.items()):
                slot_id = key[len("reading_slot:"):]
                if not key.startswith(prefix) or slot_id in present or not q.is_claim(pin):
                    continue
                changes += 1
                reading.slots.append(Slot(slot_id=slot_id, kind="section_relation", columns=[slot_id.rsplit("/", 1)[-1]],
                                          heading_id=reading.element_id, choice=pin.option_id, set_by=pin.basis,
                                          state="undecidable" if pin.option_id == UNDECIDABLE else "decided"))
        for exception in reading.exceptions:
            pin = pins.get(exception_question_key(exception.exception_id))
            if pin is None or not q.is_claim(pin):
                continue
            changes += 1
            exception.state = "undecidable" if pin.option_id == UNDECIDABLE else "decided"
            if pin.option_id == "include":
                exception.kind = "included"
        reading.revision = 1 + changes
        result.append(reading)
    return result


def basis_ref(reading: Reading) -> str:
    return f"{reading.reading_id}@{reading.revision}"


# -- expansion ---------------------------------------------------------------------------


@dataclass
class Anomaly:
    row_id: str
    slot_id: str
    check: str  # structurally_conforms | reading_conforms
    reason: str
    resolved: bool = True  # False: awaiting a row_exception / Reading decision


@dataclass
class ReadingOverlay:
    """Catalogue identities of Reading-derived claims -- kept beside the
    EvidenceGraph (which stays catalogue-free, I1)."""

    types: dict = field(default_factory=dict)  # eid -> (type id, [decision ids])
    relations: dict = field(default_factory=dict)  # aid -> (relationship type id, orientation, [decision ids])


@dataclass
class Expansion:
    graph: EvidenceGraph = field(default_factory=EvidenceGraph)
    overlay: ReadingOverlay = field(default_factory=ReadingOverlay)
    anomalies: list = field(default_factory=list)
    # item id -> the read: slot decisions it rests on, and the DEM ids it was expanded from.
    inputs: dict = field(default_factory=dict)
    dem: dict = field(default_factory=dict)


def _choice(slot) -> str | None:
    return slot.choice if slot is not None and slot.state == "decided" else None


def reading_conforms(row, reading: Reading, structural, slot: Slot) -> tuple[bool, str]:
    """Whether `slot` may be expanded on `row`: the row's structural facts
    (`structural`, from structurally_conforms) and the exceptions the
    Reading DECLARED. Checks only consequences of the Reading's decisions --
    a cell its decided role needs is non-empty, a split part count holds --
    and never interprets the cells' text (invariant 17)."""

    blocking = [i for i in structural.issues if i in ("arity", "header_repeat", "spanning")
                or (slot.kind == "split" and i == f"separator:{slot.columns[0]}")]
    if blocking:
        return False, f"structure: {', '.join(blocking)}"
    for exception in reading.exceptions:
        if exception.slot_id == slot.slot_id and row.row_id in exception.row_ids and exception.kind != "included":
            return False, f"exception:{exception.kind}:{exception.state}"
    cells = {c.column_id: c for c in row.cells}
    for column_id in slot.columns:
        cell = cells.get(column_id)
        if cell is None or not cell.text.strip():
            return False, f"empty:{column_id}"
    if slot.kind == "split":
        parts = [p for p in cells[slot.columns[0]].text.split(slot.separator)]
        if len(parts) < 2 or any(not p.strip() for p in parts):
            return False, "split_parts"
    return True, ""


def expand(document, readings: list, bundle, index) -> Expansion:
    """Every claim the (effective) Readings state over every conforming row.
    No Readings -> nothing (invariant 3)."""

    out = Expansion()
    by_id = {r.reading_id: r for r in readings}
    graph = out.graph
    # cell id -> eid of the entity expanded for it (what section relations reference).
    cell_entities: dict[str, str] = {}
    cell_reading: dict[str, Reading] = {}

    def add_entity(eid, name, type_item, specificity, segment_id, excerpt, locator, reading_refs, decisions, dem_ids, label):
        if graph.entity(eid) is not None:
            return
        graph.entities.append(EvidenceEntity(
            eid=eid, name=name, type_label=label or type_item.name, type_hint=type_item.key, specificity=specificity,
            provenance=[Provenance(source_id=segment_id.split("#")[0], excerpt=excerpt, segment_id=segment_id, locator=locator)],
            origin="reading", basis_refs=sorted(reading_refs),
        ))
        out.overlay.types[eid] = (type_item.id, list(decisions))
        out.inputs[eid], out.dem[eid] = list(decisions), list(dem_ids)

    def add_assertion(aid, subject, obj, relation, provenance, reading_refs, decisions, dem_ids, *, support="explicit"):
        relationship_type, orientation = relation
        graph.assertions.append(EvidenceAssertion(
            aid=aid, subject_eid=subject, predicate=relationship_type.name, object_eid=obj, support=support,
            provenance=provenance, origin="reading", basis_refs=sorted(reading_refs),
        ))
        out.overlay.relations[aid] = (relationship_type.id, orientation, list(decisions))
        out.inputs[aid], out.dem[aid] = list(decisions), list(dem_ids)

    for reading in readings:
        if reading.element_kind != "table" or reading.status != "validated":
            continue
        table = document.tables.get(reading.element_id)
        if table is None:
            continue
        ref = basis_ref(reading)
        roles = {s.columns[0]: s for s in reading.slots if s.kind == "role" and _choice(s) not in (None, NONE, VALUE)}
        for row in table.rows:
            structural = structurally_conforms(row, table.signature)
            if "header_repeat" in structural.issues or "spanning" in structural.issues:
                out.anomalies.append(Anomaly(row.row_id, reading.reading_id, "structurally_conforms", ", ".join(structural.issues)))
                continue
            cells = {c.column_id: c for c in row.cells}
            row_text = bundle.segment(row.row_id).text
            for column_id, slot in roles.items():
                ok, reason = reading_conforms(row, reading, structural, slot)
                if not ok:
                    out.anomalies.append(Anomaly(row.row_id, slot.slot_id, "reading_conforms", reason, resolved="undecidable" not in reason))
                    continue
                cell = cells[column_id]
                type_item = resolve_type(index, slot.choice)
                eid = f"x/{cell.cell_id}"
                add_entity(eid, cell.text.strip(), type_item, slot.specificity, row.row_id, cell.text, cell.cell_id, [ref],
                           [slot_decision_id(slot.slot_id)], [cell.cell_id, column_id], document.columns[column_id].label)
                cell_entities[cell.cell_id], cell_reading[cell.cell_id] = eid, reading
            for slot in reading.slots:
                choice = _choice(slot)
                if choice in (None, NONE) or slot.kind not in ("split", "relation"):
                    continue
                if any(c not in roles or c not in cells or cells[c].cell_id not in cell_entities for c in slot.columns):
                    continue  # an end is not an entity column, or was not expanded on this row (anomaly recorded above)
                ok, reason = reading_conforms(row, reading, structural, slot)
                if not ok:
                    out.anomalies.append(Anomaly(row.row_id, slot.slot_id, "reading_conforms", reason, resolved="undecidable" not in reason))
                    continue
                if slot.kind == "relation":
                    a, b = (cells[c] for c in slot.columns)
                    decisions = [slot_decision_id(slot.slot_id), *(slot_decision_id(roles[c].slot_id) for c in slot.columns)]
                    add_assertion(f"x/{row.row_id}/{_short(a.column_id)}>{_short(b.column_id)}", f"x/{a.cell_id}", f"x/{b.cell_id}",
                                  resolve_relation(index, choice),
                                  [Provenance(source_id=row.row_id.split("#")[0], excerpt=row_text, segment_id=row.row_id,
                                              locator=f"{a.cell_id},{b.cell_id}")],
                                  [ref], decisions, [a.cell_id, b.cell_id])
                else:  # split
                    cell = cells[slot.columns[0]]
                    part_type = resolve_type(index, choice)
                    relation = resolve_relation(index, slot.part_relation)
                    for k, part in enumerate(cell.text.split(slot.separator), start=1):
                        part_eid = f"x/{cell.cell_id}/p{k}"
                        decisions = [slot_decision_id(slot.slot_id), slot_decision_id(roles[slot.columns[0]].slot_id)]
                        add_entity(part_eid, part.strip(), part_type, "specific", row.row_id, part.strip(), cell.cell_id, [ref],
                                   decisions, [cell.cell_id], part_type.name)
                        add_assertion(f"{part_eid}/rel", f"x/{cell.cell_id}", part_eid, relation,
                                      [Provenance(source_id=row.row_id.split("#")[0], excerpt=cell.text, segment_id=row.row_id,
                                                  locator=cell.cell_id)],
                                      [ref], decisions, [cell.cell_id])

    for reading in readings:
        if reading.element_kind != "section" or reading.status != "validated":
            continue
        heading_slot = next((s for s in reading.slots if s.kind == "heading_entity"), None)
        choice = _choice(heading_slot)
        if choice in (None, NONE, VALUE):
            continue
        heading = bundle.segment(reading.element_id)
        type_item = resolve_type(index, choice)
        heading_eid = f"x/{reading.element_id}"
        ref = basis_ref(reading)
        add_entity(heading_eid, heading.text.strip(), type_item, "specific", heading.segment_id, heading.text, heading.segment_id, [ref],
                   [slot_decision_id(heading_slot.slot_id)], [heading.segment_id], type_item.name)
        for slot in reading.slots:
            relation_choice = _choice(slot)
            if slot.kind != "section_relation" or relation_choice in (None, NONE):
                continue
            column_id = slot.columns[0]
            for cell in (c for c in document.cells.values() if c.column_id == column_id):
                eid = cell_entities.get(cell.cell_id)
                if eid is None:
                    continue
                table_reading = cell_reading[cell.cell_id]
                decisions = [slot_decision_id(slot.slot_id), slot_decision_id(heading_slot.slot_id),
                             *out.inputs.get(eid, [])]
                add_assertion(f"x/{reading.element_id}/{cell.cell_id}", heading_eid, eid, resolve_relation(index, relation_choice),
                              [Provenance(source_id=heading.source_id, excerpt=heading.text, segment_id=heading.segment_id),
                               Provenance(source_id=heading.source_id, excerpt=bundle.segment(cell.row_id).text, segment_id=cell.row_id,
                                          locator=cell.cell_id)],
                              [ref, basis_ref(table_reading)], decisions, [heading.segment_id, cell.cell_id], support="structural")
    return out


# -- ownership and prose eligibility ---------------------------------------------------


def owned_source_segments(readings: list, document) -> set[str]:
    """Reading ownership (DEM ids) projected onto source segment ids: a
    validated Table Reading excludes its table segment and every row of its
    table (anomalous rows go to row_exception, never to prose); a Section
    Reading excludes only the heading it owns. Containment alone excludes
    nothing."""

    owned = set()
    for reading in readings:
        if reading.status != "validated":
            continue
        if reading.element_kind == "table":
            table = document.tables.get(reading.element_id)
            if table is not None:
                owned.add(table.table_id)
                owned |= {r.row_id for r in table.rows}
        else:
            owned |= {o for o in reading.owns if o == reading.element_id}
    return owned


def prose_eligible(document, readings: list) -> set[str]:
    """What prose extraction may see (plan, section 3.2a): DEM-classified
    prose not owned by a Reading, plus the tables a Reading explicitly judged
    not_a_table. Structured content whose Reading is pending, rejected or
    superseded -- or that has no Reading -- is NOT prose-eligible."""

    from ai.services.document.queries import prose_segments

    eligible = prose_segments(document) - owned_source_segments(readings, document)
    for reading in readings:
        if reading.status == NOT_A_TABLE and reading.element_id in document.tables:
            table = document.tables[reading.element_id]
            eligible |= {table.table_id, *(r.row_id for r in table.rows)}
    return eligible


def locked_segments(document, readings: list) -> set[str]:
    """Structured segments no AI claim may cite (only Readings interpret them)."""

    from ai.services.document.queries import structured_source_segments

    return structured_source_segments(document) - prose_eligible(document, readings)


# -- structural coverage (Phase 3) -------------------------------------------------------

READ_, IGNORED, UNREAD = "read", "ignored", "unread"


def structured_coverage(document, readings: list) -> dict:
    """Coverage of structure in Reading terms: every table column and every
    heading above a table is `read` (a validated Reading decided what it is),
    `ignored` (a Reading decided `none` for it -- a SEMANTIC decision, never a
    negative evidence result, open to challenge), or `unread` (no validated
    Reading, a rejected or undecidable slot, or a not_a_table structure).
    -> {dem id: {"status", "reading_id", "slot_id", "kind"}}."""

    by_element = {r.element_id: r for r in readings}
    found = {}
    for table in document.tables.values():
        reading = by_element.get(table.table_id)
        for column in table.columns:
            slot = reading.slot(f"{reading.reading_id}/role/{_short(column.column_id)}") if reading is not None else None
            if reading is None or reading.status != "validated" or slot is None or slot.state != "decided":
                status = UNREAD
            else:
                status = IGNORED if slot.choice == NONE else READ_
            found[column.column_id] = {"status": status, "kind": "column", "reading_id": reading.reading_id if reading else None,
                                       "slot_id": slot.slot_id if slot else None}
    headings = {h for t in document.tables.values() for h in t.ancestor_ids}
    for heading_id in sorted(headings):
        reading = by_element.get(heading_id)
        slot = next((s for s in reading.slots if s.kind == "heading_entity"), None) if reading is not None else None
        if reading is None or reading.status != "validated" or slot is None or slot.state != "decided":
            status = UNREAD
        else:
            status = IGNORED if slot.choice == NONE else READ_
        found[heading_id] = {"status": status, "kind": "heading", "reading_id": reading.reading_id if reading else None,
                             "slot_id": slot.slot_id if slot else None}
    return found


# -- ledger and questions --------------------------------------------------------------


def register(ledger, readings: list, expansion: Expansion) -> None:
    """Reading slots are AI semantic claims (`read:<slot id>`, with their
    verbatim structural basis); every expanded item is a structural
    consequence resting on the slots it was expanded from (I2)."""

    for reading in readings:
        if reading.status == NOT_A_TABLE:
            ledger.claim(f"read:{reading.reading_id}", step=READING, basis=READING, subject_ids=[reading.element_id],
                         outcome=NOT_A_TABLE, excerpts=[b.excerpt for b in reading.basis],
                         detail={"reason": reading.not_a_table_reason, "revision": reading.revision})
            continue
        for slot in reading.slots:
            if slot.state not in ("decided", "undecidable"):
                continue
            ledger.claim(
                slot_decision_id(slot.slot_id), step=READING, basis=slot.set_by, subject_ids=[slot.slot_id],
                outcome=slot.choice if slot.state == "decided" else UNDECIDABLE, excerpts=[b.excerpt for b in slot.basis][:4],
                options=[{"option_id": o} for o in slot.options],
                detail={"reading_id": reading.reading_id, "revision": reading.revision, "kind": slot.kind, "columns": slot.columns,
                        **({"part_relation": slot.part_relation} if slot.part_relation else {}),
                        **({"specificity": slot.specificity} if slot.kind == "role" else {})},
                question_key=slot_question_key(slot.slot_id),
            )
    for item in expansion.graph.items():
        identifier = getattr(item, "eid", None) or getattr(item, "aid", None)
        ledger.structural(identifier, step=READING, basis=READING, subject_ids=[identifier], inputs=expansion.inputs.get(identifier, []),
                          outcome="expanded", detail={"basis_refs": item.basis_refs, "dem": expansion.dem.get(identifier, [])})


def questions(readings: list, pins: dict, asked, *, index=None, document=None) -> list:
    """Typed questions for what a Reading left open: an `undecidable` slot,
    and each group of rows the Reading declared an undecidable exception for
    (one question per exception -- never per row)."""

    found = []
    for reading in readings:
        for slot in reading.slots:
            key = slot_question_key(slot.slot_id)
            if slot.state != "undecidable" or key in pins or key in asked:
                continue
            legal = slot_options(slot.slot_id, readings, index, document) if index is not None and document is not None else None
            found.append(q.Question(
                question_id=key, kind="reading_slot", subject_ids=[slot.slot_id],
                prompt=_slot_prompt(slot),
                options=q.standard_options(legal if legal is not None else
                                           [q.QuestionOption(option_id=o, label=o) for o in slot.options if o not in RESERVED]),
                excerpts=[b.excerpt for b in slot.basis][:3],
            ))
        for exception in reading.exceptions:
            key = exception_question_key(exception.exception_id)
            if exception.state != "undecidable" or key in pins or key in asked:
                continue
            found.append(q.Question(
                question_id=key, kind="row_exception", subject_ids=[exception.exception_id, *exception.row_ids],
                prompt=(f"In rows {', '.join(exception.row_ids)}, does '{exception.slot_id}' apply as it does to the other rows, or are "
                        f"these rows an exception ({exception.kind}: {exception.reason or 'no reason given'})?"),
                options=[q.QuestionOption(option_id="exclude", label="An exception: do not read these rows this way"),
                         q.QuestionOption(option_id="include", label="Read these rows like the others"),
                         q.QuestionOption(option_id=UNDECIDABLE, label="Cannot be decided from the evidence")],
            ))
    return found


def _slot_prompt(slot: Slot) -> str:
    if slot.kind == "role":
        return f"What are the cells of column {slot.columns[0]}? Choose the catalogue type they are, 'value', or none."
    if slot.kind == "split":
        return f"The cells of column {slot.columns[0]} all contain '{slot.separator}'. What are the parts it separates?"
    if slot.kind == "relation":
        return f"Which relationship does the table's layout state between columns {slot.columns[0]} and {slot.columns[1]}?"
    if slot.kind == "heading_entity":
        return f"Does heading {slot.heading_id} itself name an entity, and of which type?"
    return f"Which relationship does heading {slot.heading_id} state with the entities of column {slot.columns[0]}?"


def _parse_slot_id(slot_id: str):
    """'rd/<element>/<kind>/<rest>' -> (element id, kind, rest) -- also for a
    slot no Reading holds yet (an omitted section relation being challenged)."""

    if not (slot_id or "").startswith("rd/"):
        return None
    body = slot_id[3:]
    for kind in ("section_relation", "heading_entity", "relation", "split", "role"):
        marker = f"/{kind}"
        if marker in body:
            element, _, rest = body.partition(marker)
            return element, kind, rest.lstrip("/")
    return None


def _table_segments(table) -> list[str]:
    return [table.table_id, *(r.row_id for r in table.rows[:3])]


def subject_segments(subject: str, readings: list, document) -> list[str]:
    """The segments a Reading question is about (for its evidence payload):
    the heading, the table and representative rows -- for a slot a Reading
    holds, for one it omitted (parsed from its id), for an exception, or a
    lead row itself. Never empty for a Reading subject."""

    for reading in readings:
        for slot in reading.slots:
            if slot.slot_id == subject:
                found = [slot.heading_id] if slot.heading_id else []
                for column_id in slot.columns:
                    column = document.columns.get(column_id)
                    if column is not None:
                        table = document.tables[column.table_id]
                        found += [table.table_id, *(r.row_id for r in table.rows[:3])]
                return list(dict.fromkeys(f for f in found if f))
        for exception in reading.exceptions:
            if exception.exception_id == subject:
                return [reading.element_id, *exception.row_ids]
    if subject in document.classes:  # a segment named directly (a lead row, a heading, prose)
        return [subject]
    parsed = _parse_slot_id(subject)
    if parsed is None:
        return []
    element, kind, rest = parsed
    found = []
    if element in document.tables:
        found += _table_segments(document.tables[element])
    else:
        found.append(element)  # a heading
        column = document.columns.get(rest) if kind == "section_relation" else None
        if column is not None:
            found += _table_segments(document.tables[column.table_id])
    return list(dict.fromkeys(f for f in found if f))


def _role_type(readings, column_id, index):
    for reading in readings:
        for slot in reading.slots:
            if slot.kind == "role" and slot.columns == [column_id] and slot.state == "decided":
                return resolve_type(index, slot.choice)
    return None


def slot_options(slot_id: str, readings: list, index, document) -> list | None:
    """Meaningful, LEGAL options for a question about a relationship slot:
    only the (relationship, orientation) pairs some rule allows between the
    two ends' decided types (catalogue rules -- ontology compatibility, never
    lexical), each labelled with the relationship's name and description.
    -> [QuestionOption]; None when the ends' types are not decided (the
    caller keeps the slot's own options)."""

    parsed = _parse_slot_id(slot_id)
    if parsed is None:
        return None
    element, kind, rest = parsed
    by_element = {r.element_id: r for r in readings}
    if kind == "section_relation":
        heading = by_element.get(element)
        heading_slot = heading.slot(f"{heading.reading_id}/heading_entity") if heading is not None else None
        subject = resolve_type(index, heading_slot.choice) if heading_slot is not None and heading_slot.state == "decided" else None
        obj = _role_type(readings, rest, index)
    elif kind == "relation":
        a, _, b = rest.partition(">")
        subject, obj = _role_type(readings, f"{element}.{a}", index), _role_type(readings, f"{element}.{b}", index)
    else:
        return None
    if subject is None or obj is None:
        return None
    options = []
    for relationship_type_id, orientation in direct_options(index, subject.id, obj.id):
        relationship = index.relationship_types[relationship_type_id]
        first, second = (subject, obj) if orientation == AS_STATED else (obj, subject)
        options.append(q.QuestionOption(
            option_id=f"{relationship.key}:{orientation}",
            label=f"{first.name} -{relationship.name}-> {second.name} ({relationship.key})",
            detail=relationship.description or "",
        ))
    return options


_ID = re.compile(r"^rd/")


def is_reading_subject(subject: str) -> bool:
    return bool(_ID.match(subject or ""))
