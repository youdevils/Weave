"""
The publication definition: scope, presentation and opening view.

These are the documents persisted on a Publication (as versioned JSON). Every
one is *sanitised* against the data it refers to rather than trusted: stale or
unknown ids and invalid filters are dropped and reported as notices so a saved
definition can never make Publishing unusable. Only a structurally malformed
request (not an object) is an error.

Scope decides which records are in the file; the opening view decides what a
reader sees first; presentation is how the container looks. They are separate
documents so each can grow independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from model.services.appearance import schema as appearance_schema
from model.services.model_graph.dataset import EffectiveDataset
from model.services.model_graph.query import (
    ExplorerQuery,
    QueryError,
    known_ids,
    normalise_id,
    parse_filter_entries,
)

DOCUMENT_VERSION = 1

MAX_DEPTH = 5
DEFAULT_DEPTH = 1

TITLE_MAX = 200
DESCRIPTION_MAX = 1000


class ConfigError(ValueError):
    """The submitted definition is not structurally usable (not the same as stale)."""


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


# ------------------------------------------------------------------------------------
# Notices
# ------------------------------------------------------------------------------------

_DROPPED_LABELS = {
    "object_type": "an object type",
    "relationship_type": "a relationship type",
    "object": "an object",
    "attribute_filter": "an attribute filter",
    "selection": "the selected item",
    "colour": "the theme colour",
}


def notices_from_dropped(section: str, dropped: list[dict]) -> list[dict]:
    """Turn ``dropped`` entries into user-facing notices (``kind`` for the UI, ``message`` for people)."""
    notices = []
    for entry in dropped:
        label = _DROPPED_LABELS.get(entry.get("kind"), "a setting")
        notices.append(
            {
                "kind": entry.get("kind", "setting"),
                "section": section,
                "message": f"{section}: {label} that no longer applies was removed.",
            }
        )
    return notices


# ------------------------------------------------------------------------------------
# Scope
# ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicationScope:
    """
    What is included in the publication.

    Exclusions (types and attribute filters) always win. ``roots`` optionally
    narrows the result to what is reachable from those objects within ``depth``
    hops (``None`` = unlimited); with no roots the whole remaining model is
    published.
    """

    excluded_object_types: tuple = ()
    excluded_relationship_types: tuple = ()
    attribute_filters: tuple = ()
    roots: tuple = ()
    depth: int | None = DEFAULT_DEPTH

    def to_dict(self) -> dict:
        return {
            "version": DOCUMENT_VERSION,
            "object_types": {"excluded": sorted(self.excluded_object_types)},
            "relationship_types": {"excluded": sorted(self.excluded_relationship_types)},
            "attribute_filters": [f.to_dict() for f in self.attribute_filters],
            "traversal": {"roots": list(self.roots), "depth": self.depth},
        }

    @property
    def is_whole_model(self) -> bool:
        return not (
            self.excluded_object_types or self.excluded_relationship_types or self.attribute_filters or self.roots
        )


def _clean_depth(traversal: dict):
    if "depth" not in traversal:
        return DEFAULT_DEPTH
    depth = traversal["depth"]
    if depth is None:
        return None
    if isinstance(depth, bool) or not isinstance(depth, (int, float)) or depth != depth:
        return DEFAULT_DEPTH
    return max(0, min(MAX_DEPTH, int(depth)))


def sanitise_scope(raw, dataset: EffectiveDataset) -> tuple[PublicationScope, list[dict]]:
    """Reconcile a raw scope document against the canonical dataset. Returns ``(scope, notices)``."""
    raw = _as_dict(raw)
    dropped: list[dict] = []

    excluded_object_types = known_ids(
        _as_list(_as_dict(raw.get("object_types")).get("excluded")), dataset.object_types, "object_type", dropped
    )
    excluded_relationship_types = known_ids(
        _as_list(_as_dict(raw.get("relationship_types")).get("excluded")),
        dataset.relationship_types,
        "relationship_type",
        dropped,
    )

    raw_filters = raw.get("attribute_filters")
    if raw_filters is not None and not isinstance(raw_filters, list):
        raise ConfigError("attribute_filters must be a list.")
    attribute_filters = parse_filter_entries(raw_filters or [], dataset, dropped)

    traversal = _as_dict(raw.get("traversal"))
    roots = known_ids(_as_list(traversal.get("roots")), dataset.objects, "object", dropped)

    scope = PublicationScope(
        excluded_object_types=tuple(excluded_object_types),
        excluded_relationship_types=tuple(excluded_relationship_types),
        attribute_filters=tuple(attribute_filters),
        roots=tuple(roots),
        depth=_clean_depth(traversal),
    )
    return scope, notices_from_dropped("Scope", dropped)


# ------------------------------------------------------------------------------------
# Presentation
# ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Presentation:
    """How the published container looks. One colour today; logos and more colours later."""

    theme_colour: str

    def to_dict(self) -> dict:
        return {"version": DOCUMENT_VERSION, "theme_colour": self.theme_colour}


def sanitise_presentation(raw, fallback_colour: str) -> tuple[Presentation, list[dict]]:
    raw = _as_dict(raw)
    dropped: list[dict] = []
    colour = fallback_colour

    if "theme_colour" in raw:
        try:
            colour = appearance_schema.clean_value(
                appearance_schema.THEME, "accent", raw["theme_colour"], model_level=True
            )
        except appearance_schema.AppearanceValidationError:
            dropped.append({"kind": "colour"})

    return Presentation(theme_colour=colour), notices_from_dropped("Presentation", dropped)


# ------------------------------------------------------------------------------------
# Opening view
# ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DefaultView:
    """The state a reader's Explorer opens in (and returns to on "Reset view")."""

    query: ExplorerQuery = field(default_factory=ExplorerQuery)
    selection: dict | None = None

    def to_dict(self) -> dict:
        return {
            "version": DOCUMENT_VERSION,
            "state": self.query.to_state(),
            "selection": self.selection,
            "limit": self.query.limit,
        }


def sanitise_default_view(raw, published: EffectiveDataset) -> tuple[DefaultView, list[dict]]:
    """Reconcile an opening view against the *published* dataset (what a reader can actually see)."""
    raw = _as_dict(raw)
    state = dict(_as_dict(raw.get("state")))
    state["limit"] = raw.get("limit")

    try:
        query, dropped = ExplorerQuery.from_state(state, published)
    except QueryError as error:
        raise ConfigError(str(error)) from None

    selection = None
    raw_selection = raw.get("selection")
    if isinstance(raw_selection, dict):
        kind = raw_selection.get("kind")
        item_id = normalise_id(raw_selection.get("id"))
        lookup = {"object": published.objects, "relationship": published.relationships}.get(kind)
        if item_id is not None and lookup is not None and item_id in lookup:
            selection = {"kind": kind, "id": item_id}
        else:
            dropped.append({"kind": "selection"})

    return DefaultView(query=query, selection=selection), notices_from_dropped("Opening view", dropped)


# ------------------------------------------------------------------------------------
# Metadata
# ------------------------------------------------------------------------------------


def sanitise_text(raw, *, maximum: int, fallback: str = "") -> str:
    text = " ".join(str(raw).split()) if isinstance(raw, str) else ""
    return text[:maximum].rstrip() or fallback


def sanitise_description(raw) -> str:
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:DESCRIPTION_MAX]


# ------------------------------------------------------------------------------------
# The whole definition
# ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PublicationConfig:
    """Metadata plus the three definition documents; what a Publication row records."""

    title: str
    description: str
    filename: str
    scope: PublicationScope
    presentation: Presentation
    default_view: DefaultView
