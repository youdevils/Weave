"""
Pure layering of appearance:

    built-in default  ->  model customisation  ->  type override

Functions take already-sanitised layers (plain dicts), so they need no
database and no viewer and are trivially testable.
"""

from __future__ import annotations

from . import defaults
from .resolved import (
    ResolvedObjectAppearance,
    ResolvedRelationshipAppearance,
    ResolvedTheme,
)


def resolve_theme(model_theme: dict) -> ResolvedTheme:
    values = {**defaults.THEME_DEFAULTS, **model_theme}
    return ResolvedTheme(**values)


def resolve_object(
    theme: ResolvedTheme,
    model_layer: dict,
    type_layer: dict,
) -> ResolvedObjectAppearance:
    # The border falls back to the theme accent rather than a fixed colour.
    values = {"border": theme.accent, **defaults.OBJECT_DEFAULTS, **model_layer, **type_layer}
    return ResolvedObjectAppearance(font_family=theme.font_family, **values)


def resolve_relationship(
    theme: ResolvedTheme,
    model_layer: dict,
    type_layer: dict,
) -> ResolvedRelationshipAppearance:
    values = {**defaults.RELATIONSHIP_DEFAULTS, **model_layer, **type_layer}
    return ResolvedRelationshipAppearance(
        font_family=theme.font_family,
        label_halo=theme.canvas_background,
        **values,
    )
