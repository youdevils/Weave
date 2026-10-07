"""
The SourceIndex substrate: each evidence source as ordered, addressable
Segments -- headings, text blocks, list items, tables and their rows -- with
stable ids ("S1#4", "S1#t2.r3"), heading paths, table headers and adjacency.

Scope (deliberately narrow): this is an *evidence substrate*, not a document
understanding system. It supports only the structures Reconcile needs and
never interprets meaning. Structural context (heading path, header, parent)
is metadata shown alongside a segment; it is never a claim. When structure
can't be recovered confidently, text falls back to plain text_block segments
-- always correct, merely less structured.

Format readers (assisted.services.evidence_extraction) hand over neutral
*blocks*; plain text is segmented here (`blocks_from_text`). A source's text
is the segments rendered in order (`render`), so every excerpt an AI quotes
from a segment occurs in its source.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal, Optional

from pydantic import BaseModel, Field

SegmentKind = Literal["heading", "text_block", "list_item", "table", "table_row"]


class Segment(BaseModel):
    segment_id: str
    source_id: str
    kind: SegmentKind
    text: str
    # Texts of the headings this segment sits under (outermost first), and their ids.
    heading_path: list[str] = Field(default_factory=list)
    ancestor_ids: list[str] = Field(default_factory=list)
    # Table rows: the column headers (when the table has a header row) and the cells.
    header: list[str] = Field(default_factory=list)
    cells: list[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    position: int = 0

    def context(self) -> dict:
        """
        The AI-facing form: literal text, where it is, and the ids of the
        segments it sits under (`within`: its headings and, for a row, its
        table -- whose own text is the header row). Structure is expressed only
        as references to real, citable segments, never as rendered text a
        model could mistake for a quotation.
        """

        data = {"segment_id": self.segment_id, "source_id": self.source_id, "kind": self.kind, "text": self.text}
        if self.ancestor_ids:
            data["within"] = list(self.ancestor_ids)
        return data


# -- mention matching (shared by grounding, coverage and retrieval) -------------


def _singular_word(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text) -> list[str]:
    """Case/accent/punctuation-insensitive, plural-insensitive word tokens."""

    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    return [_singular_word(w) for w in re.findall(r"[0-9a-z]+", value)]


def contains_tokens(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    first = needle[0]
    for start, word in enumerate(haystack):
        if word == first and haystack[start:start + len(needle)] == needle:
            return True
    return False


def mentions(text, names) -> bool:
    """Whether `text` mentions any of `names` as whole words (word-boundary,
    case/punctuation/plural-insensitive) -- a lexical check, never semantic."""

    hay = tokens(text)
    return any(contains_tokens(hay, tokens(name)) for name in names if (name or "").strip())


_NUMBER = re.compile(r"\d[\d,_ ]*(?:\.\d+)?")


def numbers_in(text) -> set[float]:
    found = set()
    for match in _NUMBER.findall(str(text or "")):
        try:
            found.add(float(re.sub(r"[,_ ]", "", match)))
        except ValueError:
            continue
    return found


def value_occurs(value, text) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    compact = re.sub(r"[,_\s]", "", raw)
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", compact):
        return float(compact) in numbers_in(text)
    return contains_tokens(tokens(text), tokens(raw))


# -- plain text -> blocks ----------------------------------------------------------

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str):
    if "\t" in line:
        cells = [c.strip() for c in line.split("\t")]
    elif "|" in line:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
    else:
        return None
    cells = [c for c in cells]
    return cells if sum(1 for c in cells if c) >= 2 else None


def _all_caps_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters) and len(line.split()) <= 10


def blocks_from_text(text: str, *, line_blocks: bool = False) -> list[dict]:
    """
    Plain text -> neutral blocks. Pipe/tab-separated runs become tables (the
    first row is taken as the header, by convention); markdown/ALL-CAPS lines
    become headings; bulleted/numbered lines become list items (indented
    continuation lines attach); everything else is paragraphs split on blank
    lines (or one block per line with `line_blocks`, for flattened layouts
    whose blank lines mean nothing). A short line directly before a table or
    list is treated as its heading.
    """

    blocks: list[dict] = []
    paragraph: list[str] = []
    table: list[list[str]] = []

    def flush_paragraph():
        if paragraph:
            blocks.append({"kind": "paragraph", "text": "\n".join(paragraph)})
            paragraph.clear()

    def flush_table():
        if table:
            rows = [r for r in table]
            header = rows[0] if len(rows) >= 2 else []
            blocks.append({"kind": "table", "header": header, "rows": rows[1:] if header else rows})
            table.clear()

    def promote_caption():
        # "Venues" on its own line, directly before a table/list -> its heading.
        if blocks and blocks[-1]["kind"] == "paragraph":
            last = blocks[-1]["text"]
            if "\n" not in last and len(last.split()) <= 5 and not last.rstrip().endswith((".", ",", ";")):
                blocks[-1] = {"kind": "heading", "text": last.strip().rstrip(":"), "level": 3}

    for raw in str(text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_table()
            continue
        cells = _cells(line)
        if cells is not None or (table and _SEPARATOR.match(line)):
            if not table:
                flush_paragraph()
                promote_caption()
            if cells is not None:
                table.append(cells)
            continue
        flush_table()
        heading = _MD_HEADING.match(line)
        if heading:
            flush_paragraph()
            blocks.append({"kind": "heading", "text": heading.group(2), "level": len(heading.group(1))})
            continue
        if _all_caps_heading(line.strip()) and not _BULLET.match(line):
            flush_paragraph()
            blocks.append({"kind": "heading", "text": line.strip(), "level": 2})
            continue
        if _BULLET.match(line):
            flush_paragraph()
            if not blocks or blocks[-1]["kind"] != "list_item":
                promote_caption()
            blocks.append({"kind": "list_item", "text": line.strip()})
            continue
        if blocks and blocks[-1]["kind"] == "list_item" and not paragraph and raw[:1].isspace():
            blocks[-1]["text"] += "\n" + line.strip()
            continue
        if line_blocks:
            flush_paragraph()
            blocks.append({"kind": "paragraph", "text": line.strip()})
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    flush_table()
    return blocks


# -- blocks -> segments ---------------------------------------------------------------


def build_segments(source_id: str, blocks: list[dict]) -> list[Segment]:
    segments: list[Segment] = []
    stack: list[tuple[int, str, str]] = []  # (level, text, id)
    counter = table_counter = 0

    def path():
        return [text for _, text, _ in stack], [sid for _, _, sid in stack]

    for block in blocks:
        kind = block.get("kind")
        if kind == "heading":
            level = int(block.get("level") or 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            counter += 1
            texts, ids = path()
            segment = Segment(segment_id=f"{source_id}#{counter}", source_id=source_id, kind="heading", text=block["text"].strip(),
                              heading_path=texts, ancestor_ids=ids, position=len(segments))
            segments.append(segment)
            stack.append((level, segment.text, segment.segment_id))
        elif kind == "table":
            table_counter += 1
            table_id = f"{source_id}#t{table_counter}"
            header = [str(c or "").strip() for c in block.get("header") or []]
            texts, ids = path()
            segments.append(Segment(segment_id=table_id, source_id=source_id, kind="table", text=" | ".join(header),
                                    heading_path=texts, ancestor_ids=ids, header=header, position=len(segments)))
            for row_number, row in enumerate(block.get("rows") or [], start=1):
                cells = [str(c or "").strip() for c in row]
                if not any(cells):
                    continue
                segments.append(Segment(
                    segment_id=f"{table_id}.r{row_number}", source_id=source_id, kind="table_row", text=" | ".join(cells),
                    heading_path=texts, ancestor_ids=[*ids, table_id], header=header, cells=cells, parent_id=table_id,
                    position=len(segments),
                ))
        else:
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            counter += 1
            texts, ids = path()
            segments.append(Segment(
                segment_id=f"{source_id}#{counter}", source_id=source_id,
                kind="list_item" if kind == "list_item" else "text_block", text=text,
                heading_path=texts, ancestor_ids=ids, position=len(segments),
            ))
    return segments


def with_ancestors(bundle, segment_ids) -> list[Segment]:
    """The segments plus every heading/table segment they sit under, deduped,
    in document order -- what any payload showing segments must include so
    structure can be cited by id."""

    wanted = []
    for segment_id in segment_ids:
        segment = bundle.segment(segment_id)
        if segment is None:
            continue
        wanted += [*segment.ancestor_ids, segment.segment_id]
    order = {s.segment_id: (s.source_id, s.position) for s in bundle.segments()}
    unique = sorted({sid for sid in wanted if sid in order}, key=lambda sid: order[sid])
    return [bundle.segment(sid) for sid in unique]


def render(segments: list[Segment]) -> str:
    return "\n".join(s.text for s in segments if s.text)
