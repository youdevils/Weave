"""
One entry point that turns a raw publication definition into a sanitised one and
the dataset it selects.

Defaults, the live preview and the publish step all go through
``normalise_config``, which is what guarantees they agree on what is published.
"""

from __future__ import annotations

from dataclasses import dataclass

from model.services.appearance import AppearanceService
from model.services.model_graph.dataset import EffectiveDataset

from .config import (
    DESCRIPTION_MAX,
    TITLE_MAX,
    ConfigError,
    DefaultView,
    PublicationConfig,
    sanitise_default_view,
    sanitise_description,
    sanitise_presentation,
    sanitise_scope,
    sanitise_text,
)
from .filenames import default_filename, normalise_filename
from .scoping import apply_scope


@dataclass(frozen=True)
class NormalisedConfig:
    config: PublicationConfig
    published: EffectiveDataset  # the scoped canonical dataset: exactly what goes in the file
    notices: list


def normalise_config(model, raw, canonical: EffectiveDataset) -> NormalisedConfig:
    """
    ``raw`` is a definition as submitted by the page or as saved on a previous
    publication: ``{title, description, filename, scope, presentation, default_view}``.
    Stale references are dropped and reported in ``notices``; anything missing
    takes its default. Raises ``ConfigError`` only for a structurally bad request.
    """
    if not isinstance(raw, dict):
        raise ConfigError("The publication definition must be an object.")

    scope, notices = sanitise_scope(raw.get("scope"), canonical)
    published = apply_scope(canonical, scope)

    presentation, presentation_notices = sanitise_presentation(
        raw.get("presentation"), AppearanceService.resolve_theme(model).accent
    )
    default_view, view_notices = sanitise_default_view(raw.get("default_view"), published)

    config = PublicationConfig(
        title=sanitise_text(raw.get("title"), maximum=TITLE_MAX, fallback=sanitise_text(model.name, maximum=TITLE_MAX)),
        description=sanitise_description(raw.get("description"))[:DESCRIPTION_MAX],
        filename=normalise_filename(raw.get("filename"), default_filename(model.name, model.revision)),
        scope=scope,
        presentation=presentation,
        default_view=default_view,
    )
    return NormalisedConfig(config, published, notices + presentation_notices + view_notices)


__all__ = ["ConfigError", "DefaultView", "NormalisedConfig", "normalise_config"]
