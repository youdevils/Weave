"""
Read-only object search over the effective dataset.

``searchable_fields`` is the single place that decides what text of an object
is searchable. Today that is its name plus every populated attribute value;
when searchable attributes become configurable, only that function changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dataset import EffectiveDataset, EffectiveObject, EffectiveObjectType, is_populated
from .projection import Projection

DEFAULT_RESULT_LIMIT = 25
_SNIPPET_LENGTH = 80

# Ranking tiers: lower sorts first.
_NAME_EXACT, _NAME_PREFIX, _NAME_CONTAINS, _ATTRIBUTE_EXACT, _ATTRIBUTE_CONTAINS = range(5)


def searchable_fields(obj: EffectiveObject, object_type: EffectiveObjectType) -> list[tuple[str, str]]:
    """``(label, text)`` pairs; the first is always the name."""
    fields = [("Name", obj.name)]
    for spec in object_type.attributes:
        value = obj.attributes.get(spec.key)
        if spec.data_type != "boolean" and is_populated(value):
            fields.append((spec.name, str(value)))
    return fields


def _snippet(text: str) -> str:
    return text if len(text) <= _SNIPPET_LENGTH else text[: _SNIPPET_LENGTH - 1] + "…"


def _best_match(needle: str, fields):
    """The best (tier, field label, text) for the needle, or None."""
    best = None
    for index, (label, text) in enumerate(fields):
        folded = text.casefold()
        if needle not in folded:
            continue
        if index == 0:
            tier = _NAME_EXACT if folded == needle else _NAME_PREFIX if folded.startswith(needle) else _NAME_CONTAINS
        else:
            tier = _ATTRIBUTE_EXACT if folded == needle else _ATTRIBUTE_CONTAINS
        if best is None or tier < best[0]:
            best = (tier, label, text)
    return best


def _subtitle(obj: EffectiveObject, object_type: EffectiveObjectType) -> str | None:
    """A short identifying detail, to tell apart objects that share a name."""
    for label, text in searchable_fields(obj, object_type)[1:]:
        return f"{label}: {_snippet(text)}"
    return None


@dataclass(frozen=True)
class SearchResults:
    query: str
    total: int
    limit: int
    results: tuple

    @property
    def truncated(self) -> bool:
        return self.total > len(self.results)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "total": self.total,
            "limit": self.limit,
            "truncated": self.truncated,
            "results": list(self.results),
        }


def search_objects(
    dataset: EffectiveDataset,
    q: str,
    *,
    projection: Projection | None = None,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> SearchResults:
    """Case-insensitive partial match over names and populated attribute values."""
    normalised = " ".join((q or "").split())
    needle = normalised.casefold()
    if not needle:
        return SearchResults(query="", total=0, limit=limit, results=())

    ranked = []
    for obj in dataset.objects.values():
        object_type = dataset.object_types[obj.type_id]
        match = _best_match(needle, searchable_fields(obj, object_type))
        if match is not None:
            ranked.append((match[0], obj.name.casefold(), obj.id, obj, object_type, match))

    ranked.sort(key=lambda item: item[:3])

    results = tuple(
        {
            "id": obj.id,
            "name": obj.name,
            "typeId": object_type.id,
            "typeName": object_type.name,
            "isProposed": obj.is_proposed,
            "inView": projection.contains_object(obj.id) if projection is not None else None,
            "connections": dataset.degree(obj.id),
            "subtitle": _subtitle(obj, object_type),
            "match": (
                {"field": match[1], "snippet": _snippet(match[2])} if match[0] >= _ATTRIBUTE_EXACT else None
            ),
        }
        for _tier, _name, _id, obj, object_type, match in ranked[:limit]
    )

    return SearchResults(query=normalised, total=len(ranked), limit=limit, results=results)
