"""
AIIssue: OnyxJar's deterministic feedback to an AI stage, and the translation
of model.services.validation's ValidationIssues into it.

A ValidationIssue addresses its target by canonical UUID. That UUID never
crosses into AI-facing context; instead it is translated to the action that
caused it (for an entity this ChangeSet creates -- its id was minted by
OnyxJar from a "new" token, see ai.services.resolution.RefMap) or to the
existing entity's semantic reference. A cardinality failure on a brand-new
Match therefore comes back as "action m1 (token match_1): has 1 has_team,
minimum 2" rather than as unattributable prose.
"""

from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from pydantic import BaseModel


class AIIssue(BaseModel):
    code: str
    message: str
    action_id: Optional[str] = None
    # An EvidenceGraph item id, Adjudication question id or Gap Probe
    # requirement id the issue is about.
    item_id: Optional[str] = None
    ref: Optional[dict[str, Any]] = None
    field: Optional[str] = None


def issue(code, message, *, action_id=None, item_id=None, ref=None, field=None) -> AIIssue:
    return AIIssue(code=code, message=message, action_id=action_id, item_id=item_id, ref=ref, field=field)


_CARDINALITY_SIDES = {
    # code -> (the target is this end of the rule, the minimum/maximum field, the other end)
    "object_cardinality_minimum": ("subject_type_id", "object_minimum", "object_type_id"),
    "object_cardinality_maximum": ("subject_type_id", "object_maximum", "object_type_id"),
    "subject_cardinality_minimum": ("object_type_id", "subject_minimum", "subject_type_id"),
    "subject_cardinality_maximum": ("object_type_id", "subject_maximum", "subject_type_id"),
}


def _cardinality_hint(item, *, type_id, index) -> str:
    """Names the exact rule(s) behind a cardinality failure by key, so the
    correction never has to map a display name back to a key."""

    side = _CARDINALITY_SIDES.get(getattr(item, "code", ""))
    if side is None or not type_id or index is None:
        return ""
    own_end, bound_field, other_end = side
    hints = []
    for rule in index.rules_touching(type_id):
        bound = getattr(rule, bound_field)
        if getattr(rule, own_end) != type_id or bound in (None, 0):
            continue
        relationship_type = index.relationship_types[rule.relationship_type_id].key
        other = index.object_types[getattr(rule, other_end)].key
        direction = "to" if own_end == "subject_type_id" else "from"
        limit = "at least" if bound_field.endswith("minimum") else "at most"
        hints.append(f"'{relationship_type}' {direction} '{other}' ({limit} {bound})")
    if not hints:
        return ""
    return (
        " Rule: " + "; ".join(hints) + ". Add what the evidence supports, or omit the entity that requires it."
        if "minimum" in item.code
        else " Rule: " + "; ".join(hints) + "."
    )


def translate_validation_issues(issues, *, ref_map, index) -> list[AIIssue]:
    translated = []
    for item in issues:
        action_id = None
        ref = None
        type_id = None
        target_id = getattr(item, "target_id", None)
        if target_id is not None:
            minted = ref_map.minted.get(str(target_id)) if ref_map is not None else None
            if minted is not None:
                action_id = minted.action_id
                ref = {"entity": minted.domain, "token": minted.token} if minted.token else None
                type_id = minted.parent_id if minted.domain == "object" else None
            elif index is not None:
                ref = index.semantic_ref(getattr(item, "target_type", "") or "", target_id)
                obj = index.objects.get(str(target_id))
                type_id = obj.type_id if obj else None
        translated.append(
            AIIssue(
                code=getattr(item, "code", "") or "validation_error",
                message=(getattr(item, "message", "") or "") + _cardinality_hint(item, type_id=type_id, index=index),
                action_id=action_id,
                ref=ref,
                field=getattr(item, "field", None),
            )
        )
    return translated


def bounded_issues(issues) -> list[AIIssue]:
    """De-duplicated (code, action, ref, message) and capped at AI_FEEDBACK_MAX_ISSUES."""

    seen = set()
    result = []
    for item in issues:
        marker = (item.code, item.action_id, item.item_id, repr(item.ref), item.message)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    limit = settings.AI_FEEDBACK_MAX_ISSUES
    if len(result) > limit:
        omitted = len(result) - limit
        result = result[:limit] + [
            AIIssue(code="more_issues_omitted", message=f"{omitted} further issue(s) omitted; fix these first.")
        ]
    return result
