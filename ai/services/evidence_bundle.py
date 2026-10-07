"""
The EvidenceBundle: the user's supplied evidence as stable, addressable
sources ("S1", "S2", ...), plus the one deterministic check OnyxJar can make
cheaply about an AI's claimed support -- that a quoted excerpt really occurs
in the source it cites.

Each source is also segmented (ai.services.sources): addressable headings,
text blocks, list items, tables and rows that Extraction batches, Gap Probe
evidence packs, Verification and provenance locators all work in. A source's
text is its segments rendered in order. Format readers may hand over
structured `blocks` (assisted.services.evidence_extraction); plain text is
segmented here.

Source text is passed through verbatim -- never sanitised or rewritten,
including text that happens to look like an identifier.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ai.services.sources import Segment, blocks_from_text, build_segments, render

# The user's own intent statement may also be cited as provenance (e.g. it
# names the existing Tournament the evidence's stages belong to).
INTENT_SOURCE_ID = "intent"

_TRUNCATION_MARKER = "[... evidence truncated at"

_QUOTE_TRANSLATION = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "–": "-", "—": "-", "−": "-", " ": " ",
    }
)


class EvidenceSource(BaseModel):
    source_id: str
    name: str
    mime_type: str = ""
    text: str
    truncated: bool = False
    segments: list[Segment] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    sources: list[EvidenceSource] = Field(default_factory=list)

    @classmethod
    def from_assets(cls, assets) -> "EvidenceBundle":
        """`assets` is the {"name", "content", "mime_type"} shape
        assisted.services.execution already produces per evidence file."""

        sources = []
        for position, asset in enumerate(assets or (), start=1):
            source_id = f"S{position}"
            content = str(asset.get("content") or "")
            blocks = asset.get("blocks")
            segments = build_segments(source_id, blocks if blocks else blocks_from_text(content))
            text = render(segments)
            if not text.strip() and content.strip():
                segments = build_segments(source_id, [{"kind": "paragraph", "text": content}])
                text = render(segments)
            sources.append(
                EvidenceSource(
                    source_id=source_id,
                    name=str(asset.get("name") or f"Source {position}"),
                    mime_type=str(asset.get("mime_type") or ""),
                    text=text,
                    truncated=_TRUNCATION_MARKER in content,
                    segments=segments,
                )
            )
        return cls(sources=sources)

    def source(self, source_id) -> EvidenceSource | None:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        return None

    def source_ids(self) -> set[str]:
        return {source.source_id for source in self.sources}

    def segments(self) -> list[Segment]:
        return [segment for source in self.sources for segment in source.segments]

    def segment(self, segment_id) -> Segment | None:
        for source in self.sources:
            for segment in source.segments:
                if segment.segment_id == segment_id:
                    return segment
        return None

    def segments_containing(self, source_id, excerpt) -> list[Segment]:
        source = self.source(source_id)
        return [s for s in (source.segments if source else []) if excerpt_occurs(excerpt, s.text)]

    def neighbours(self, segment: Segment, distance: int = 1) -> list[Segment]:
        source = self.source(segment.source_id)
        if source is None:
            return []
        position = next((i for i, s in enumerate(source.segments) if s.segment_id == segment.segment_id), None)
        if position is None:
            return []
        return [source.segments[i] for i in range(max(0, position - distance), min(len(source.segments), position + distance + 1)) if i != position]


def normalize_for_matching(text) -> str:
    """Whitespace-, case-, quote- and dash-insensitive form, for excerpt matching only."""

    text = unicodedata.normalize("NFKC", str(text or "")).translate(_QUOTE_TRANSLATION)
    return re.sub(r"\s+", " ", text).strip().casefold()


def excerpt_occurs(excerpt, text) -> bool:
    needle = normalize_for_matching(excerpt)
    return bool(needle) and needle in normalize_for_matching(text)


def source_text(bundle: EvidenceBundle, intent_text: str, source_id) -> str | None:
    if source_id == INTENT_SOURCE_ID:
        return intent_text
    source = bundle.source(source_id)
    return source.text if source else None


def source_name(bundle: EvidenceBundle, source_id) -> str:
    if source_id == INTENT_SOURCE_ID:
        return "Intent"
    source = bundle.source(source_id)
    return source.name if source else str(source_id)
