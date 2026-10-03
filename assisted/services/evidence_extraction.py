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
"""

from __future__ import annotations

import io
from dataclasses import dataclass

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
        return ExtractedEvidence(mime_type=mime, text=text)

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
            text = "\n\n".join(p.text for p in document.paragraphs).strip()
        except Exception as error:
            raise EvidenceExtractionError(f"'{filename}' could not be read as a .docx file.") from error
        return ExtractedEvidence(mime_type=mime, text=text)

    raise UnsupportedEvidenceType(
        f"'{filename}' is a type OnyxJar can't read yet -- only plain text, PDF, and .docx are supported."
    )


def bounded(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... evidence truncated at {max_chars} characters]"
