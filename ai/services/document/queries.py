"""
Structural queries over the evidence -- the one home for what OnyxJar knows
about document layout (headings, containment, table headers and cells).

Before the DEM these predicates were spread over coverage, near_miss,
grounding and analysis; they live here now and those modules delegate. Every
query is structural or textual: names and labels are passed in by the
caller as plain strings and only ever compared lexically (word-boundary,
case/plural-insensitive -- ai.services.sources.mentions). No query knows the
catalogue, decides what something is, or creates a claim.
"""

from __future__ import annotations

from ai.services.document.model import CONTEXT, PROSE, STRUCTURED, Conformance, DocumentModel
from ai.services.evidence_bundle import INTENT_SOURCE_ID
from ai.services.sources import mentions, tokens

# Segment kinds that carry statements (headings and table header segments are context).
SEARCHED = ("text_block", "list_item", "table_row")


# -- segment layout --------------------------------------------------------------------


def header_labelled(segment, labels) -> bool:
    """A table row whose header row names a kind -- the layout, never the
    row's own words."""

    return segment.kind == "table_row" and mentions(" | ".join(segment.header or []), labels)


def labelled_by(segment, labels) -> bool:
    """A structured segment that names a kind: in its own text, or -- a table
    row -- in its table's header row."""

    if segment.kind not in ("table_row", "list_item"):
        return False
    return mentions(segment.text, labels) or header_labelled(segment, labels)


def relational(segment) -> bool:
    """A table row with two or more non-empty cells."""

    return segment.kind == "table_row" and sum(1 for c in segment.cells if c.strip()) >= 2


def related(a, b) -> bool:
    """Two cited units (anything with segment_id / source_id / ancestor_ids)
    in an ancestor/descendant relation within one source."""

    if a.source_id != b.source_id or a.source_id == INTENT_SOURCE_ID:
        return False
    return (a.segment_id is not None and a.segment_id in b.ancestor_ids) or (b.segment_id is not None and b.segment_id in a.ancestor_ids)


def relationship_anchors(subject_names: list[str], object_names: list[str], bundle) -> dict:
    """Where a relationship between something named by `subject_names` and
    something named by `object_names` could actually be cited -- a locator,
    never a claim and never proof a relationship does or doesn't exist.

        direct       segment ids whose own text mentions both sides
        structural   (segment_id, segment_id) ancestor/descendant pairs, one
                     naming each side
        subject_only/object_only  only when neither of the above exists
    """

    segments = list(bundle.segments())
    subject_hits = [s for s in segments if mentions(s.text, subject_names)]
    object_hits = [s for s in segments if mentions(s.text, object_names)]
    object_ids = {s.segment_id for s in object_hits}
    subject_ids = {s.segment_id for s in subject_hits}
    direct = [s.segment_id for s in subject_hits if s.segment_id in object_ids]
    subject_only = [s for s in subject_hits if s.segment_id not in object_ids]
    object_only = [s for s in object_hits if s.segment_id not in subject_ids]
    structural = [(a.segment_id, b.segment_id) for a in subject_only for b in object_only if related(a, b)]
    if direct or structural:
        return {"direct": direct, "structural": structural}
    return {"direct": [], "structural": [], "subject_only": [s.segment_id for s in subject_only][:5],
            "object_only": [s.segment_id for s in object_only][:5]}


# -- sections and labelled evidence ----------------------------------------------------


def section_members(bundle, names, counterpart_labels) -> list:
    """Segments under a heading that names the entity; those in a section
    whose own heading names the counterpart's kind first."""

    anchors = {s.segment_id for s in bundle.segments() if s.kind == "heading" and mentions(s.text, names)}
    if not anchors:
        return []
    members = [s for s in bundle.segments() if s.kind in SEARCHED and anchors & set(s.ancestor_ids)]
    return sorted(members, key=lambda s: (not mentions(" ".join(s.heading_path), counterpart_labels), s.source_id, s.position))


def header_evidence(segment, wanted, counterpart_labels) -> dict | None:
    """A table row with a cell that IS the entity (`wanted`: token lists),
    under a header with a column naming the kind, whose cell in this row is
    another, non-empty cell."""

    if not header_labelled(segment, counterpart_labels):
        return None
    cells = list(segment.cells)
    own = {i for i, cell in enumerate(cells) if tokens(cell) in wanted}
    for column, label in enumerate(segment.header):
        if mentions(label, counterpart_labels) and column < len(cells) and cells[column].strip() and own - {column}:
            return {"header": " | ".join(segment.header), "column": label, "cell": cells[column]}
    return None


def section_evidence(bundle, segment, names, counterpart_labels) -> dict | None:
    """An item under a heading naming the entity, inside a section whose own
    (different) heading names the kind."""

    if segment.kind not in SEARCHED:
        return None
    headings = [h for h in (bundle.segment(a) for a in segment.ancestor_ids) if h is not None and h.kind == "heading"]
    for outer, entity in enumerate(headings):
        if not mentions(entity.text, names):
            continue
        kind = next((h for h in headings[outer + 1:] if mentions(h.text, counterpart_labels)), None)
        if kind is not None:
            return {"heading": kind.text, "under": entity.text}
    return None


def labelled_evidence(bundle, segments, names, counterpart_labels) -> list[dict]:
    """Of `segments`, those whose layout associates the entity (`names`) with
    the counterpart's kind (`counterpart_labels`) -- header or section; a kind
    word in the row's own text, or the entity inside a larger cell, is not
    layout and does not count."""

    wanted = [tokens(n) for n in names if (n or "").strip()]
    found = []
    for segment in segments:
        entry = header_evidence(segment, wanted, counterpart_labels) or section_evidence(bundle, segment, names, counterpart_labels)
        if entry is not None:
            found.append({"segment_id": segment.segment_id, **entry})
    return found


def labelled_segments(bundle, labels) -> list[str]:
    """Where evidence of a kind would be: structured segments labelled by it
    (in their text or table header), any segment naming it, and everything
    under a heading naming it. Nothing labelled: the whole document."""

    headings = {s.segment_id for s in bundle.segments() if s.kind == "heading" and mentions(s.text, labels)}
    found = [
        s.segment_id for s in bundle.segments()
        if s.kind in SEARCHED and (labelled_by(s, labels) or mentions(s.text, labels) or headings & set(s.ancestor_ids))
    ]
    return found or [s.segment_id for s in bundle.segments() if s.kind in SEARCHED]


def leads(bundle, names, counterpart_labels) -> list[dict]:
    """Structural leads for "is the entity named by `names` related to
    something of the kind `counterpart_labels`?": the labelled evidence among
    the segments naming the entity and the members of sections headed by it.
    A lead is where layout says to look -- never an answer."""

    hits = [s for s in bundle.segments() if s.kind in SEARCHED and mentions(s.text, names)]
    seen = {s.segment_id for s in hits}
    hits += [s for s in section_members(bundle, names, counterpart_labels) if s.segment_id not in seen]
    return labelled_evidence(bundle, hits, names, counterpart_labels)


# -- the DEM ---------------------------------------------------------------------------


def structured_source_segments(document: DocumentModel) -> set[str]:
    """Every segment the DEM recognises as structured (tables and their rows).
    Such content reaches semantic claims only through a Reading."""

    return {sid for sid, cls in document.classes.items() if cls == STRUCTURED}


def prose_segments(document: DocumentModel) -> set[str]:
    return {sid for sid, cls in document.classes.items() if cls == PROSE}


def context_segments(document: DocumentModel) -> set[str]:
    return {sid for sid, cls in document.classes.items() if cls == CONTEXT}


def column_cells(document: DocumentModel, column_id: str) -> list:
    return [c for c in document.cells.values() if c.column_id == column_id]


def header_for(document: DocumentModel, row_id: str) -> tuple:
    row = document.rows.get(row_id)
    return document.tables[row.table_id].signature.header if row is not None else ()


def structurally_conforms(row, signature) -> Conformance:
    """Purely structural: is `row` (a DEM Row) typical of `signature`?

        arity           a different number of cells than the table's columns
        header_repeat   the row repeats the header
        spanning        a multi-column table row with one non-empty cell
                        (a caption, subtotal or section line)
        separator:<col> a column whose every cell carries a separator, here
                        without it (or with a different part count)
    """

    issues = []
    texts = [c.text for c in row.cells]
    if signature.arity and len(texts) != signature.arity:
        issues.append("arity")
    if signature.header and [t.strip().casefold() for t in texts] == [h.strip().casefold() for h in signature.header]:
        # A repeated header (a table continued across pages) is not data: the
        # data-row expectations below do not apply to it.
        return Conformance(row_id=row.row_id, issues=("header_repeat",))
    if signature.arity >= 2 and sum(1 for t in texts if t.strip()) == 1:
        issues.append("spanning")
    for cell in row.cells:
        separator = signature.separator(cell.column_id)
        if separator and cell.text.strip() and separator not in cell.text:
            issues.append(f"separator:{cell.column_id}")
    return Conformance(row_id=row.row_id, issues=tuple(issues))
