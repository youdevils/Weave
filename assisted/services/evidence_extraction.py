"""
Turns raw evidence bytes into real text, instead of the
`bytes.decode("utf-8", errors="replace")` this used to do for every file
regardless of type -- which produced mostly-U+FFFD garbage for any binary
format and was the actual cause of oversized OpenAI requests, not anything
`AI_CONTEXT_MAX_BYTES` could ever bound (see assisted/README.md).

`extract_text` is called from both `assisted.services.evidence` (upload-time
validation -- the extracted text itself is discarded, only used to reject
unsupported/corrupt files early) and `assisted.services.execution`
(worker-time, where the extracted text is what actually gets sent to the AI),
so the "how do I read a PDF/docx" logic exists exactly once.

Alongside the text, PDFs and .docx files also yield neutral structural
*blocks* (headings, paragraphs, list items, tables with their rows) that
ai.services.sources turns into addressable evidence segments. Structure is
recovered only as far as it is reliable -- PDF tables from the positions of
their text runs (bold first row = header), .docx tables natively -- and
anything uncertain degrades to plain paragraphs. Nothing here interprets
meaning. Plain text is segmented on the ai side.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field

import magic
from docx import Document
from PyPDF2 import PdfReader


class EvidenceExtractionError(ValueError):
    """Evidence content could not be turned into usable text."""


class UnsupportedEvidenceType(EvidenceExtractionError):
    """Evidence is a type OnyxJar doesn't know how to read."""


@dataclass
class ExtractedEvidence:
    mime_type: str  # sniffed from content, never the client-declared header
    text: str
    # Neutral structural blocks (see module docstring); None for plain text,
    # which ai.services.sources segments itself.
    blocks: list | None = field(default=None)


def extract_text(data: bytes, *, filename: str = "") -> ExtractedEvidence:
    mime = magic.from_buffer(data, mime=True)

    if mime.startswith("text/"):
        try:
            return ExtractedEvidence(mime_type=mime, text=data.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise EvidenceExtractionError(f"'{filename}' is not valid UTF-8 text.") from error

    if mime == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as error:
            # PyPDF2 raises a variety of internal exception types for
            # corrupt/encrypted/malformed PDFs -- deliberately broad, all map
            # to the same user-facing rejection.
            raise EvidenceExtractionError(f"'{filename}' could not be read as a PDF.") from error
        return ExtractedEvidence(mime_type=mime, text=text, blocks=_pdf_blocks(reader))

    # A .docx is a zip container -- libmagic often reports it as plain
    # application/zip rather than the more specific OOXML type, depending on
    # the installed magic database version.
    is_docx_candidate = mime in (
        "application/zip",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    if is_docx_candidate and filename.lower().endswith(".docx"):
        try:
            document = Document(io.BytesIO(data))
            blocks = _docx_blocks(document)
            text = "\n\n".join(_block_text(b) for b in blocks).strip()
        except Exception as error:
            raise EvidenceExtractionError(f"'{filename}' could not be read as a .docx file.") from error
        return ExtractedEvidence(mime_type=mime, text=text, blocks=blocks)

    raise UnsupportedEvidenceType(
        f"'{filename}' is a type OnyxJar can't read yet -- only plain text, PDF, and .docx are supported."
    )


def bounded(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... evidence truncated at {max_chars} characters]"


def bounded_blocks(blocks, *, max_chars: int):
    """-> (blocks, truncated). Whole blocks only; a table keeps as many whole
    rows as fit."""

    kept, used = [], 0
    for block in blocks:
        size = len(_block_text(block)) + 1
        if used + size <= max_chars:
            kept.append(block)
            used += size
            continue
        if block.get("kind") == "table":
            rows = []
            used += len(" | ".join(block.get("header") or [])) + 1
            for row in block.get("rows") or []:
                row_size = len(" | ".join(row)) + 1
                if used + row_size > max_chars:
                    break
                rows.append(row)
                used += row_size
            if rows:
                kept.append({**block, "rows": rows})
        kept.append({"kind": "paragraph", "text": f"[... evidence truncated at {max_chars} characters]"})
        return kept, True
    return kept, False


def _block_text(block) -> str:
    if block.get("kind") == "table":
        lines = [" | ".join(block.get("header") or [])] if block.get("header") else []
        lines += [" | ".join(row) for row in block.get("rows") or []]
        return "\n".join(lines)
    return str(block.get("text") or "")


# -- PDF: structure from text-run positions -------------------------------------

_BULLETS = ("-", "\u2022", "\u2013", "*")


@dataclass
class _Run:
    x: float
    y: float
    size: float
    bold: bool
    text: str


@dataclass
class _Line:
    y: float
    runs: list

    @property
    def x(self):
        return self.runs[0].x

    @property
    def size(self):
        return max(r.size for r in self.runs)

    @property
    def bold(self):
        return all(r.bold for r in self.runs)

    @property
    def text(self):
        return " ".join(r.text for r in self.runs).strip()

    def columns(self, gap):
        """Cells: runs separated horizontally by more than `gap` points."""

        cells, current = [], [self.runs[0]]
        for run in self.runs[1:]:
            if run.x - current[-1].x > gap and run.x - current[0].x > gap:
                cells.append(current)
                current = [run]
            else:
                current.append(run)
        cells.append(current)
        return [(c[0].x, " ".join(r.text for r in c).strip()) for c in cells]


def _page_lines(page) -> list[_Line]:
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        for part in str(text or "").split("\n"):
            if not part.strip():
                continue
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            name = str((font_dict or {}).get("/BaseFont", "")) if hasattr(font_dict, "get") else ""
            runs.append(_Run(x=float(x), y=float(y), size=float(font_size or 0), bold="bold" in name.lower(), text=part.strip()))

    page.extract_text(visitor_text=visit)
    lines: list[_Line] = []
    for run in runs:
        # Same baseline (within 1pt) and same font size: one visual line.
        # Different sizes on nearly the same baseline (a heading just above
        # a bullet) stay separate lines.
        line = next((line for line in lines if abs(line.y - run.y) <= 1.0 and abs(line.runs[0].size - run.size) < 0.5), None)
        if line is None:
            lines.append(_Line(y=run.y, runs=[run]))
        else:
            line.runs.append(run)
    for line in lines:
        line.runs.sort(key=lambda r: r.x)
    lines.sort(key=lambda line: -line.y)
    return lines


def _aligned(a, b, tolerance=3.0) -> bool:
    xs_a, xs_b = [x for x, _ in a], [x for x, _ in b]
    return len(xs_a) == len(xs_b) and all(abs(p - q) <= tolerance for p, q in zip(xs_a, xs_b))


def _pdf_blocks(reader) -> list[dict] | None:
    """Positions -> blocks. Returns None (flat-text fallback) when a page yields
    no positioned runs at all."""

    pages = []
    for page in reader.pages:
        lines = _page_lines(page)
        if not lines and (page.extract_text() or "").strip():
            return None
        pages.append(lines)
    all_lines = [line for lines in pages for line in lines]
    if not all_lines:
        return []
    body = Counter(round(line.size, 1) for line in all_lines if not line.bold).most_common(1)
    body_size = body[0][0] if body else 10.0
    heading_sizes = sorted({round(line.size, 1) for line in all_lines if line.bold and line.size > body_size}, reverse=True)

    blocks: list[dict] = []
    for lines in pages:
        index = 0
        while index < len(lines):
            line = lines[index]
            gap = max(line.size * 2.0, 12.0)
            columns = line.columns(gap)
            # A table: two or more consecutive lines whose cells share column positions.
            if len(columns) >= 2:
                rows, bolds, cursor = [columns], [line.bold], index + 1
                while cursor < len(lines):
                    nxt = lines[cursor]
                    nxt_columns = nxt.columns(max(nxt.size * 2.0, 12.0))
                    if not _aligned(columns, nxt_columns) or abs(lines[cursor - 1].y - nxt.y) > max(nxt.size, 1) * 3.5:
                        break
                    rows.append(nxt_columns)
                    bolds.append(nxt.bold)
                    cursor += 1
                if len(rows) >= 2:
                    cells = [[text for _, text in row] for row in rows]
                    header = cells[0] if bolds[0] and not any(bolds[1:]) else []
                    blocks.append({"kind": "table", "header": header, "rows": cells[1:] if header else cells})
                    index = cursor
                    continue
            text = line.text
            if line.bold and line.size > body_size and len(columns) == 1:
                level = heading_sizes.index(round(line.size, 1)) + 1 if round(line.size, 1) in heading_sizes else 3
                if blocks and blocks[-1]["kind"] == "heading" and blocks[-1].get("level") == level and blocks[-1].get("_y", 0) - line.y <= line.size * 1.6:
                    blocks[-1]["text"] += " " + text
                else:
                    blocks.append({"kind": "heading", "text": text, "level": level})
                blocks[-1]["_y"] = line.y
            elif text.startswith(_BULLETS):
                blocks.append({"kind": "list_item", "text": text, "_y": line.y, "_x": line.x, "_size": line.size})
            elif (
                blocks and blocks[-1]["kind"] in ("paragraph", "list_item") and "_y" in blocks[-1]
                and blocks[-1]["_y"] - line.y <= line.size * 1.8 and abs(blocks[-1].get("_x", line.x) - line.x) <= 3.0
            ):
                blocks[-1]["text"] += "\n" + text
                blocks[-1]["_y"] = line.y
            else:
                blocks.append({"kind": "paragraph", "text": text, "_y": line.y, "_x": line.x, "_size": line.size})
            index += 1
        for block in blocks:
            block.pop("_y", None)
            block.pop("_x", None)
            block.pop("_size", None)
    return blocks


# -- DOCX: native structure ---------------------------------------------------------


def _docx_blocks(document) -> list[dict]:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            if style.startswith("Heading") or style == "Title":
                digits = "".join(ch for ch in style if ch.isdigit())
                blocks.append({"kind": "heading", "text": text, "level": int(digits) if digits else 1})
            elif "List" in style or child.find(".//{*}numPr") is not None:
                blocks.append({"kind": "list_item", "text": text})
            else:
                blocks.append({"kind": "paragraph", "text": text})
        elif tag == "tbl":
            table = Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            rows = [row for row in rows if any(row)]
            if not rows:
                continue
            header = rows[0] if len(rows) >= 2 else []
            blocks.append({"kind": "table", "header": header, "rows": rows[1:] if header else rows})
    return blocks
