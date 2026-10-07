"""
The one deterministic check OnyxJar makes about any AI claim's support: every
quoted excerpt must really occur, verbatim (whitespace/case/quote-insensitive),
in the source it cites. Ontology-free by construction -- shared by the
EvidenceGraph validator, Adjudication/Gap Probe/Verification answers and the
ChangeSet resolver.
"""

from __future__ import annotations

from django.conf import settings

from ai.services.evidence_bundle import INTENT_SOURCE_ID, EvidenceBundle, excerpt_occurs, source_text
from ai.services.feedback import AIIssue, issue


def check_provenance(provenance, *, item_id, where, bundle: EvidenceBundle, intent_text: str, issues: list[AIIssue]) -> None:
    if not provenance:
        issues.append(issue("missing_provenance", f"{where} has no provenance; cite the source text that supports it.", item_id=item_id))
        return
    for item in provenance:
        if not check_excerpt(item.source_id, item.excerpt, item_id=item_id, where=where, bundle=bundle, intent_text=intent_text, issues=issues):
            continue
        segment_id = getattr(item, "segment_id", None)
        if segment_id:
            segment = bundle.segment(segment_id)
            if segment is None or segment.source_id != item.source_id:
                issues.append(issue("unknown_segment", f"{where} cites segment '{segment_id}', which is not a segment of '{item.source_id}'.", item_id=item_id))
            elif not excerpt_occurs(item.excerpt, segment.text):
                issues.append(issue(
                    "excerpt_not_in_segment",
                    f"{where}: the excerpt \"{(item.excerpt or '')[:120]}\" does not occur in segment '{segment_id}'.",
                    item_id=item_id,
                ))


def resolve_segments(provenance, *, bundle: EvidenceBundle) -> None:
    """
    Deterministic literal repair (never semantic): a provenance item with no
    segment_id -- or one whose cited segment doesn't contain the excerpt --
    is pointed at the single segment of its source that does contain it.
    Ambiguous or absent matches are left for validation to report.
    """

    for item in provenance:
        if item.source_id == INTENT_SOURCE_ID:
            continue
        current = bundle.segment(item.segment_id) if item.segment_id else None
        if current is not None and current.source_id == item.source_id and excerpt_occurs(item.excerpt, current.text):
            continue
        matches = bundle.segments_containing(item.source_id, item.excerpt)
        if len(matches) == 1:
            item.segment_id = matches[0].segment_id
        if not item.locator and item.segment_id:
            item.locator = item.segment_id


def check_excerpt(source_id, excerpt, *, item_id, where, bundle: EvidenceBundle, intent_text: str, issues: list[AIIssue]) -> bool:
    text = source_text(bundle, intent_text, source_id)
    if text is None:
        valid = sorted(bundle.source_ids() | {INTENT_SOURCE_ID})
        issues.append(issue("unknown_source", f"{where} cites source '{source_id}'; valid sources are {', '.join(valid)}.", item_id=item_id))
        return False
    if len(excerpt or "") > settings.AI_PROVENANCE_MAX_EXCERPT_CHARS:
        issues.append(
            issue(
                "excerpt_too_long",
                f"{where}: excerpts may be at most {settings.AI_PROVENANCE_MAX_EXCERPT_CHARS} characters; quote only the relevant part.",
                item_id=item_id,
            )
        )
        return False
    if not excerpt_occurs(excerpt, text):
        if _quotes_context(excerpt, bundle, source_id):
            issues.append(issue(
                "context_not_quotable",
                f"{where}: \"{(excerpt or '')[:120]}\" is a heading path, not source text. To rely on a heading, cite the heading's own "
                "segment_id and quote its own text (and set support='structural').",
                item_id=item_id,
            ))
            return False
        issues.append(
            issue(
                "excerpt_not_found",
                f"{where}: the excerpt \"{(excerpt or '')[:120]}\" does not occur in source '{source_id}'. Quote the source verbatim.",
                item_id=item_id,
            )
        )
        return False
    return True


def _quotes_context(excerpt, bundle: EvidenceBundle, source_id) -> bool:
    """An excerpt made of heading texts joined like a path ("A > B")."""

    if ">" not in (excerpt or ""):
        return False
    source = bundle.source(source_id)
    headings = [s.text for s in (source.segments if source else []) if s.kind in ("heading", "table")]
    parts = [p.strip() for p in excerpt.split(">") if p.strip()]
    return bool(parts) and all(any(excerpt_occurs(part, h) for h in headings) for part in parts)


def excerpt_in_any_source(excerpt, *, bundle: EvidenceBundle, intent_text: str) -> bool:
    """For answers that quote without naming a source (adjudication/objection excerpts)."""

    if not (excerpt or "").strip():
        return False
    return excerpt_occurs(excerpt, intent_text) or any(excerpt_occurs(excerpt, s.text) for s in bundle.sources)
