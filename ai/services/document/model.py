"""
The Document Evidence Model (DEM): what the evidence structurally contains.

INVARIANT (.Documentation/reconcile-architecture-plan.md, invariant 1): the
DEM is structural, never semantic. It records tables, columns, rows, cells,
sections, their containment and exact text, and deterministic textual facts
(recurring in-cell separators, string occurrences). It never says what a
cell IS ("New Zealand v Fiji" is a Match), never relates two entities, and
never offers a catalogue type or relationship. Those are Reading decisions.

Enforced by tests (ai.tests.test_document_model): this package may not
import the semantic index, the catalogue, mapping or the EvidenceGraph, and
no DEM type carries a field outside FIELD_ALLOWLIST.

Ids are deterministic (the plan, section 3.1):

    row / table / heading / item ids   the segment ids (S1#t3.r1, S1#t3, S1#15)
    column id                          <table segment id>.c<k>   (S1#t3.c2)
    cell id                            <row segment id>.c<k>     (S1#t3.r1.c2)
    section id                         its heading segment's id

k is the 1-based position of the cell in Segment.cells (= in Segment.header).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

DEM_VERSION = "1"

# A segment's structural class: table/row content is `structured` (it reaches
# semantic claims only through a Reading -- invariant 12); text blocks and
# list items are `prose`; headings are `context` (citable, never extraction
# targets in their own right).
SegmentClass = Literal["structured", "prose", "context"]
STRUCTURED, PROSE, CONTEXT = "structured", "prose", "context"

# Candidate in-cell separators whose recurrence in a column is a textual
# fact (" v " in "New Zealand v Fiji"). What the parts MEAN is a Reading.
SEPARATORS = (" v ", " vs ", " vs. ", " versus ", " & ", " / ", ", ", " and ")


@dataclass(frozen=True)
class Cell:
    cell_id: str
    row_id: str
    column_id: str
    ordinal: int
    text: str


@dataclass(frozen=True)
class Column:
    column_id: str
    table_id: str
    ordinal: int
    # The header cell's text; "" for a header-less table.
    label: str


@dataclass(frozen=True)
class Row:
    row_id: str
    table_id: str
    cells: tuple


@dataclass(frozen=True)
class SeparatorPattern:
    """How often one candidate separator occurs in a column's non-empty cells."""

    column_id: str
    separator: str
    cells_with: int
    cells_nonempty: int
    # Part counts seen (a cell with the separator once has 2 parts).
    part_counts: tuple = ()

    @property
    def dominant(self) -> bool:
        return self.cells_nonempty >= 2 and self.cells_with == self.cells_nonempty


@dataclass(frozen=True)
class Signature:
    """A table's structural shape -- what a row must look like to be
    structurally typical of it (`queries.structurally_conforms`)."""

    table_id: str
    arity: int
    header: tuple
    # column id -> the separator every non-empty cell of it carries (or None).
    separators: tuple
    # column id -> number of empty cells in it.
    empty_counts: tuple

    def separator(self, column_id) -> Optional[str]:
        return dict(self.separators).get(column_id)


@dataclass(frozen=True)
class Table:
    table_id: str
    source_id: str
    has_header: bool
    columns: tuple
    rows: tuple
    # Heading segment ids the table sits under, outermost first.
    ancestor_ids: tuple
    signature: Signature
    separator_patterns: tuple = ()


@dataclass(frozen=True)
class Section:
    section_id: str
    source_id: str
    heading: str
    depth: int
    parent_id: Optional[str]
    # Segments whose nearest heading is this one (tables count once, by table id).
    member_ids: tuple
    # Every segment under this heading, at any depth (rows included).
    descendant_ids: tuple


@dataclass(frozen=True)
class Conformance:
    row_id: str
    # Structural deviations from the signature: "arity", "header_repeat",
    # "spanning", "separator:<column id>". Empty = structurally typical.
    issues: tuple = ()

    @property
    def conforms(self) -> bool:
        return not self.issues


@dataclass
class DocumentModel:
    version: str = DEM_VERSION
    tables: dict = field(default_factory=dict)  # table id -> Table
    sections: dict = field(default_factory=dict)  # section id -> Section
    classes: dict = field(default_factory=dict)  # segment id -> SegmentClass
    columns: dict = field(default_factory=dict)  # column id -> Column
    cells: dict = field(default_factory=dict)  # cell id -> Cell
    rows: dict = field(default_factory=dict)  # row id -> Row
    digest: str = ""


# Every field name a DEM type may carry. Anything ontological (a type, kind,
# relationship, hint, option, role ...) is a Reading's business, never the
# DEM's -- a test fails if a field outside this list appears.
FIELD_ALLOWLIST = frozenset({
    "cell_id", "row_id", "column_id", "ordinal", "text", "table_id", "label", "cells", "separator", "cells_with",
    "cells_nonempty", "part_counts", "arity", "header", "separators", "empty_counts", "source_id", "has_header",
    "columns", "rows", "ancestor_ids", "signature", "separator_patterns", "section_id", "heading", "depth", "parent_id",
    "member_ids", "descendant_ids", "issues", "version", "tables", "sections", "classes", "digest",
})
