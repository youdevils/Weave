"""
Initial values for a new publication.

The most recent *successful* publication of the model supplies the defaults
(scope, opening view, theme colour, title, description, filename). They are
copied into a fresh in-memory definition and reconciled against the current
canonical model; the previous Publication is only ever read, never modified.
Because a failed publication leaves no row, "most recent" is simply the highest
sequence.
"""

from __future__ import annotations

import copy

from model.services.model_graph.dataset import EffectiveDataset

from ..models import Publication
from .filenames import default_filename
from .normalise import NormalisedConfig, normalise_config


def previous_publication(model) -> Publication | None:
    return Publication.objects.filter(model=model).order_by("-sequence").first()


def _raw_from_previous(model, previous: Publication) -> dict:
    # A name that was just the auto-generated one for its revision follows the
    # new revision; a name the publisher chose themselves is kept as is.
    was_generated = previous.filename == default_filename(model.name, previous.source_revision)
    return copy.deepcopy(
        {
            "title": previous.title,
            "description": previous.description,
            "filename": default_filename(model.name, model.revision) if was_generated else previous.filename,
            "scope": previous.scope,
            "presentation": previous.presentation,
            "default_view": previous.default_view,
        }
    )


def resolve_defaults(model, canonical: EffectiveDataset) -> tuple[NormalisedConfig, Publication | None]:
    """``(definition, previous_publication)``; the definition has any stale settings already reconciled."""
    previous = previous_publication(model)
    raw = _raw_from_previous(model, previous) if previous else {}
    return normalise_config(model, raw, canonical), previous
