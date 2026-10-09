"""
Building the DEM from an EvidenceBundle's segments -- deterministic, and
independent of any catalogue or model (its only input is the segmented
evidence, so the same document always yields the same DEM and digest).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from ai.services.document.model import (
    CONTEXT,
    DEM_VERSION,
    PROSE,
    SEPARATORS,
    STRUCTURED,
    Cell,
    Column,
    DocumentModel,
    Row,
    Section,
    SeparatorPattern,
    Signature,
    Table,
)

_CLASS = {"table": STRUCTURED, "table_row": STRUCTURED, "text_block": PROSE, "list_item": PROSE, "heading": CONTEXT}


def column_id(table_id: str, ordinal: int) -> str:
    return f"{table_id}.c{ordinal}"


def cell_id(row_id: str, ordinal: int) -> str:
    return f"{row_id}.c{ordinal}"


def build_document(bundle) -> DocumentModel:
    segments = list(bundle.segments())
    by_id = {s.segment_id: s for s in segments}
    model = DocumentModel()
    model.classes = {s.segment_id: _CLASS.get(s.kind, PROSE) for s in segments}

    for table_segment in (s for s in segments if s.kind == "table"):
        _add_table(model, table_segment, [s for s in segments if s.kind == "table_row" and s.parent_id == table_segment.segment_id], by_id)

    for heading in (s for s in segments if s.kind == "heading"):
        heading_ancestors = [a for a in heading.ancestor_ids if by_id.get(a) is not None and by_id[a].kind == "heading"]
        members, descendants = [], []
        for segment in segments:
            if heading.segment_id not in segment.ancestor_ids:
                continue
            descendants.append(segment.segment_id)
            nearest = [a for a in segment.ancestor_ids if by_id.get(a) is not None and by_id[a].kind == "heading"]
            if nearest and nearest[-1] == heading.segment_id and segment.kind != "table_row":
                members.append(segment.segment_id)
        model.sections[heading.segment_id] = Section(
            section_id=heading.segment_id, source_id=heading.source_id, heading=heading.text, depth=len(heading_ancestors),
            parent_id=heading_ancestors[-1] if heading_ancestors else None, member_ids=tuple(members),
            descendant_ids=tuple(descendants),
        )

    model.digest = _digest(model)
    return model


def _add_table(model: DocumentModel, table_segment, row_segments, by_id) -> None:
    table_id = table_segment.segment_id
    header = tuple(table_segment.header or ())
    lengths = Counter(len(r.cells) for r in row_segments)
    arity = len(header) if header else (lengths.most_common(1)[0][0] if lengths else 0)
    width = max([arity, *lengths.keys()]) if lengths else arity

    columns = tuple(
        Column(column_id=column_id(table_id, k), table_id=table_id, ordinal=k, label=header[k - 1] if k <= len(header) else "")
        for k in range(1, width + 1)
    )
    rows = []
    for row_segment in row_segments:
        cells = tuple(
            Cell(cell_id=cell_id(row_segment.segment_id, k), row_id=row_segment.segment_id, column_id=column_id(table_id, k),
                 ordinal=k, text=text)
            for k, text in enumerate(row_segment.cells, start=1)
        )
        rows.append(Row(row_id=row_segment.segment_id, table_id=table_id, cells=cells))

    patterns, dominant, empty = [], [], []
    for column in columns:
        texts = [c.text for r in rows for c in r.cells if c.column_id == column.column_id]
        nonempty = [t for t in texts if t.strip()]
        empty.append((column.column_id, len(texts) - len(nonempty)))
        chosen = None
        for separator in SEPARATORS:
            with_it = [t for t in nonempty if separator in t]
            if not with_it:
                continue
            pattern = SeparatorPattern(column_id=column.column_id, separator=separator, cells_with=len(with_it),
                                       cells_nonempty=len(nonempty),
                                       part_counts=tuple(sorted({t.count(separator) + 1 for t in with_it})))
            patterns.append(pattern)
            if chosen is None and pattern.dominant:
                chosen = separator
        dominant.append((column.column_id, chosen))

    heading_ancestors = tuple(a for a in table_segment.ancestor_ids if by_id.get(a) is not None and by_id[a].kind == "heading")
    signature = Signature(table_id=table_id, arity=arity, header=header, separators=tuple(dominant), empty_counts=tuple(empty))
    table = Table(table_id=table_id, source_id=table_segment.source_id, has_header=bool(header), columns=columns, rows=tuple(rows),
                  ancestor_ids=heading_ancestors, signature=signature, separator_patterns=tuple(patterns))
    model.tables[table_id] = table
    model.columns.update({c.column_id: c for c in columns})
    model.rows.update({r.row_id: r for r in rows})
    model.cells.update({c.cell_id: c for r in rows for c in r.cells})


def _digest(model: DocumentModel) -> str:
    canonical = {
        "version": DEM_VERSION,
        "classes": sorted(model.classes.items()),
        "tables": [
            {"id": t.table_id, "header": list(t.signature.header), "columns": [[c.column_id, c.label] for c in t.columns],
             "rows": [[c.cell_id, c.text] for r in t.rows for c in r.cells], "separators": list(t.signature.separators),
             "ancestors": list(t.ancestor_ids)}
            for t in sorted(model.tables.values(), key=lambda t: t.table_id)
        ],
        "sections": [
            [s.section_id, s.heading, s.depth, s.parent_id, list(s.member_ids)]
            for s in sorted(model.sections.values(), key=lambda s: s.section_id)
        ],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
