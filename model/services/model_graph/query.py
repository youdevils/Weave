"""
ExplorerQuery: the *request* for a graph projection (what the user is
investigating), independent of how it is rendered.

``from_params`` sanitises client input against the effective dataset: stale
or unknown ids and invalid filters are dropped rather than trusted, and each
drop is reported so the client can reconcile its own state with the echo.
Only malformed JSON is a hard error.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from .dataset import EffectiveDataset, is_populated

DEFAULT_LIMIT = 300
MIN_LIMIT = 1
MAX_LIMIT = 1000

OP_IN = "in"
OP_CONTAINS = "contains"
OP_RANGE = "range"

# The operator each attribute data type supports.
OPERATOR_BY_DATA_TYPE = {
    "choice": OP_IN,
    "boolean": OP_IN,
    "text": OP_CONTAINS,
    "number": OP_RANGE,
    "date": OP_RANGE,
    "datetime": OP_RANGE,
}


class QueryError(ValueError):
    """The request is malformed (as opposed to merely stale)."""


@dataclass(frozen=True)
class AttributeFilter:
    """
    Constrain objects *of one type* by one attribute. ``value`` is a tuple of
    accepted strings for ``in``, a needle for ``contains``, and a
    ``(minimum, maximum)`` pair (either may be None) for ``range``.
    """

    type_id: str
    key: str
    op: str
    value: object

    def to_dict(self) -> dict:
        if self.op == OP_RANGE:
            value = {"min": self.value[0], "max": self.value[1]}
        elif self.op == OP_IN:
            value = list(self.value)
        else:
            value = self.value
        return {"type_id": self.type_id, "key": self.key, "op": self.op, "value": value}

    def matches(self, raw) -> bool:
        if not is_populated(raw):
            return False
        if self.op == OP_IN:
            return str(raw).casefold() in {v.casefold() for v in self.value}
        if self.op == OP_CONTAINS:
            return self.value.casefold() in str(raw).casefold()
        return self._in_range(raw)

    def _in_range(self, raw) -> bool:
        minimum, maximum = self.value
        if isinstance(minimum, float) or isinstance(maximum, float):  # numeric bounds
            try:
                number = float(raw)
            except (TypeError, ValueError):
                return False
            return (minimum is None or number >= minimum) and (maximum is None or number <= maximum)
        if not isinstance(raw, str):  # date/datetime values are ISO strings
            return False
        text = raw
        if minimum is not None and text < minimum:
            return False
        # Truncate so a date-only maximum includes the whole day of a datetime.
        return maximum is None or text[: len(maximum)] <= maximum


@dataclass(frozen=True)
class ExplorerQuery:
    hidden_object_types: frozenset = frozenset()
    hidden_relationship_types: frozenset = frozenset()
    attribute_filters: tuple = ()
    include: frozenset = frozenset()
    limit: int = DEFAULT_LIMIT

    def to_state(self) -> dict:
        """The sanitised query as the client should hold it."""
        return {
            "hiddenObjectTypes": sorted(self.hidden_object_types),
            "hiddenRelationshipTypes": sorted(self.hidden_relationship_types),
            "attributeFilters": [f.to_dict() for f in self.attribute_filters],
            "include": sorted(self.include),
        }

    def filters_for_type(self, type_id: str) -> list[AttributeFilter]:
        return [f for f in self.attribute_filters if f.type_id == type_id]

    @classmethod
    def from_params(cls, params, dataset: EffectiveDataset):
        """Returns ``(query, dropped)``; ``dropped`` lists what was discarded and why."""
        dropped: list[dict] = []

        hidden_object_types = known_ids(
            _getlist(params, "hide_objects"), dataset.object_types, "object_type", dropped
        )
        hidden_relationship_types = known_ids(
            _getlist(params, "hide_relationships"), dataset.relationship_types, "relationship_type", dropped
        )
        include = known_ids(_getlist(params, "include"), dataset.objects, "object", dropped)
        attribute_filters = _parse_filters(_first(params, "filters"), dataset, dropped)

        return (
            cls(
                hidden_object_types=frozenset(hidden_object_types),
                hidden_relationship_types=frozenset(hidden_relationship_types),
                attribute_filters=tuple(attribute_filters),
                include=frozenset(include),
                limit=_parse_limit(_first(params, "limit")),
            ),
            dropped,
        )

    @classmethod
    def from_state(cls, state, dataset: EffectiveDataset):
        """
        Same sanitising as ``from_params`` for a state document (the shape
        ``to_state`` returns, and the Explorer client holds):
        ``hiddenObjectTypes``, ``hiddenRelationshipTypes``, ``attributeFilters``,
        ``include`` and an optional ``limit``. Anything other than a dict is
        treated as an empty state; a malformed ``attributeFilters`` list is an error.
        """
        state = state if isinstance(state, dict) else {}
        dropped: list[dict] = []

        hidden_object_types = known_ids(
            _as_list(state.get("hiddenObjectTypes")), dataset.object_types, "object_type", dropped
        )
        hidden_relationship_types = known_ids(
            _as_list(state.get("hiddenRelationshipTypes")), dataset.relationship_types, "relationship_type", dropped
        )
        include = known_ids(_as_list(state.get("include")), dataset.objects, "object", dropped)

        raw_filters = state.get("attributeFilters")
        if raw_filters is not None and not isinstance(raw_filters, list):
            raise QueryError("attributeFilters must be a list.")
        attribute_filters = parse_filter_entries(raw_filters or [], dataset, dropped)

        return (
            cls(
                hidden_object_types=frozenset(hidden_object_types),
                hidden_relationship_types=frozenset(hidden_relationship_types),
                attribute_filters=tuple(attribute_filters),
                include=frozenset(include),
                limit=_parse_limit(state.get("limit")),
            ),
            dropped,
        )


# -- parameter helpers ---------------------------------------------------------


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _getlist(params, key) -> list:
    if hasattr(params, "getlist"):
        return params.getlist(key)
    value = params.get(key, [])
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _first(params, key):
    value = params.get(key)
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _parse_limit(raw) -> int:
    try:
        return max(MIN_LIMIT, min(MAX_LIMIT, int(raw)))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def normalise_id(raw):
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, AttributeError, TypeError):
        return None


def known_ids(raw_ids, known, kind, dropped) -> list[str]:
    kept = []
    for raw in raw_ids:
        normalised = normalise_id(raw)
        if normalised is None or normalised not in known:
            dropped.append({"kind": kind, "id": str(raw), "reason": "unknown"})
        elif normalised not in kept:
            kept.append(normalised)
    return kept


def _parse_filters(raw, dataset, dropped) -> list[AttributeFilter]:
    if raw in (None, ""):
        return []
    try:
        entries = json.loads(raw)
    except (TypeError, ValueError):
        raise QueryError("filters must be valid JSON.") from None
    if not isinstance(entries, list):
        raise QueryError("filters must be a list.")
    return parse_filter_entries(entries, dataset, dropped)


def parse_filter_entries(entries, dataset, dropped) -> list[AttributeFilter]:
    """
    Sanitise a list of ``{type_id, key, op, value}`` filter documents against
    the dataset: unknown types/attributes and invalid values are dropped and
    reported, duplicates collapse. Shared by the Explorer and Publishing scope.
    """
    parsed = []
    for entry in entries:
        attribute_filter = _parse_filter(entry, dataset)
        if attribute_filter is None:
            dropped.append({"kind": "attribute_filter", "id": json.dumps(entry, default=str), "reason": "invalid"})
        elif attribute_filter not in parsed:
            parsed.append(attribute_filter)
    return parsed


def _parse_filter(entry, dataset) -> AttributeFilter | None:
    if not isinstance(entry, dict):
        return None
    type_id = normalise_id(entry.get("type_id"))
    object_type = dataset.object_type(type_id) if type_id else None
    if object_type is None:
        return None

    spec = next((s for s in object_type.attributes if s.key == entry.get("key")), None)
    if spec is None:
        return None

    op = OPERATOR_BY_DATA_TYPE.get(spec.data_type)
    if op is None or entry.get("op", op) != op:
        return None

    value = _clean_value(op, spec.data_type, entry.get("value"))
    if value is None:
        return None
    return AttributeFilter(type_id=type_id, key=spec.key, op=op, value=value)


def _clean_value(op, data_type, raw):
    if op == OP_IN:
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return None
        values = tuple(dict.fromkeys(str(v).strip() for v in raw if str(v).strip()))
        return values or None

    if op == OP_CONTAINS:
        text = raw.strip() if isinstance(raw, str) else ""
        return text or None

    if not isinstance(raw, dict):
        return None
    bounds = []
    for bound in (raw.get("min"), raw.get("max")):
        if bound in (None, ""):
            bounds.append(None)
        elif data_type == "number":
            try:
                bounds.append(float(bound))
            except (TypeError, ValueError):
                return None
        else:
            bounds.append(str(bound).strip() or None)
    if bounds == [None, None]:
        return None
    return tuple(bounds)
