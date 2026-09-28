"""
Previewing and publishing.

``preview`` and ``publish`` run the *same* pipeline (load the canonical dataset,
sanitise the definition, apply the scope, build the bundle), so the preview a
user looks at is exactly the data that gets published. ``publish`` additionally
verifies, under the model's row lock, that nothing changed since that preview
(the revision and the content digest must match), then records the Publication,
generates the document and hands it back, all in one transaction:

    lock model -> load canonical -> normalise -> scope -> bundle
      -> compare with what was previewed -> create Publication
      -> render document -> validate document -> commit

Anything that fails rolls the whole transaction back, so a failed attempt leaves
no Publication row (and consumes no sequence number). The generated HTML is
never stored: it lives in memory until the caller has sent it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from model.models.model import Model
from model.services.appearance import schema as appearance_schema
from model.services.model_graph.loader import load_effective_dataset

from ..models import Publication
from .bundle import build_bundle, canonical_json, with_publication
from .config import ConfigError
from .normalise import normalise_config
from .portable.renderer import render_document
from .portable.validator import validate_document

logger = logging.getLogger(__name__)

DEFAULT_MAX_OBJECTS = 25_000
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class PublicationError(Exception):
    """Base for failures the caller can explain to the user. ``status`` is the HTTP status to use."""

    status = 400
    code = "error"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.details = details


class InvalidPublication(PublicationError):
    status = 400
    code = "invalid"


class PublicationStale(PublicationError):
    """The model changed since the preview the user is publishing."""

    status = 409
    code = "changed"


class PublicationTooLarge(PublicationError):
    status = 422
    code = "too_large"


class PublicationGenerationFailed(PublicationError):
    status = 500
    code = "generation_failed"


def max_objects() -> int:
    return getattr(settings, "PUBLICATION_MAX_OBJECTS", DEFAULT_MAX_OBJECTS)


def max_bytes() -> int:
    return getattr(settings, "PUBLICATION_MAX_BYTES", DEFAULT_MAX_BYTES)


@dataclass(frozen=True)
class Preview:
    revision: int
    summary: dict
    notices: list
    config: object
    bundle: dict | None  # None when the selection is too large to preview or publish
    digest: str | None
    too_large: str | None = None
    roots: dict | None = None  # the starting objects' names, for labelling them in the page


@dataclass(frozen=True)
class PublishedArtifact:
    publication: Publication
    html: str

    @property
    def filename(self) -> str:
        return self.publication.filename


def _summary(canonical, published) -> dict:
    return {
        "objects": len(published.objects),
        "relationships": len(published.relationships),
        "totalObjects": len(canonical.objects),
        "totalRelationships": len(canonical.relationships),
    }


def named_objects(canonical, object_ids) -> dict:
    """``{id: {name, typeName}}`` for the given objects (those that exist)."""
    named = {}
    for object_id in object_ids:
        obj = canonical.object(object_id)
        if obj:
            named[object_id] = {"name": obj.name, "typeName": canonical.object_types[obj.type_id].name}
    return named


def _normalise(model, raw_config, canonical):
    try:
        return normalise_config(model, raw_config, canonical)
    except ConfigError as error:
        raise InvalidPublication(str(error)) from None


def _size_problem(published, bundle=None) -> str | None:
    if len(published.objects) > max_objects():
        return (
            f"This selection has {len(published.objects):,} objects; a publication can hold at most "
            f"{max_objects():,}. Narrow the scope to publish it."
        )
    if bundle is not None and len(canonical_json(bundle)) > max_bytes():
        return "This selection is too large to publish as a single file. Narrow the scope to publish it."
    return None


def load_publishable_dataset(model):
    """
    The active data a publication is built from: active objects and relationships only
    (never inactive ones), including the active records of an inactive type.
    """
    return load_effective_dataset(model, None, keep_inactive_types=True)


def load_canonical(model_id):
    """
    ``(model, canonical_dataset)`` at one consistent revision, without locking.

    The revision is read before and after the load; if a proposal committed in
    between, the load is retried once so the two always belong together.
    """
    for attempt in range(2):
        model = Model.objects.get(pk=model_id)
        canonical = load_publishable_dataset(model)
        current = Model.objects.values_list("revision", flat=True).get(pk=model_id)
        if current == model.revision or attempt == 1:
            return model, canonical
    raise AssertionError("unreachable")


def preview(model_id, raw_config) -> Preview:
    """What would be published for ``raw_config`` right now. Read-only."""
    model, canonical = load_canonical(model_id)
    result = _normalise(model, raw_config, canonical)

    summary = _summary(canonical, result.published)
    roots = named_objects(canonical, result.config.scope.roots)

    def unpublishable(problem):
        return Preview(model.revision, summary, result.notices, result.config, None, None, problem, roots)

    problem = _size_problem(result.published)
    if problem:
        return unpublishable(problem)

    bundle = build_bundle(model, result.published, result.config)
    problem = _size_problem(result.published, bundle)
    if problem:
        return unpublishable(problem)

    return Preview(model.revision, summary, result.notices, result.config, bundle, bundle["digest"], None, roots)


def _check_expectation(expected, revision: int, digest: str) -> None:
    if not isinstance(expected, dict) or "revision" not in expected or "digest" not in expected:
        raise InvalidPublication("Preview the publication before publishing it.")
    if expected["revision"] != revision or expected["digest"] != digest:
        raise PublicationStale(
            "The model has changed since your preview. Review the refreshed preview, then publish again.",
            revision=revision,
        )


def publish(model_id, user, raw_config, expected) -> PublishedArtifact:
    """
    Publish exactly what ``expected`` (the revision and digest of the user's
    preview) describes. Raises a ``PublicationError`` subclass on any failure,
    having stored nothing.
    """
    try:
        with transaction.atomic():
            # The same lock a proposal commit and a model deletion take: the revision
            # and the data read below belong together, and nothing changes underneath.
            locked = Model.objects.select_for_update().get(pk=model_id)
            canonical = load_publishable_dataset(locked)
            result = _normalise(locked, raw_config, canonical)

            problem = _size_problem(result.published)
            if problem:
                raise PublicationTooLarge(problem)
            bundle = build_bundle(locked, result.published, result.config)
            problem = _size_problem(result.published, bundle)
            if problem:
                raise PublicationTooLarge(problem)

            _check_expectation(expected, locked.revision, bundle["digest"])

            config = result.config
            sequence = (Publication.objects.filter(model=locked).aggregate(top=Max("sequence"))["top"] or 0) + 1
            publication = Publication.objects.create(
                model=locked,
                sequence=sequence,
                source_revision=locked.revision,
                title=config.title,
                description=config.description,
                filename=config.filename,
                scope=config.scope.to_dict(),
                presentation=config.presentation.to_dict(),
                default_view=config.default_view.to_dict(),
                appearance_snapshot=appearance_schema.sanitise_document(locked.appearance),
                object_count=len(result.published.objects),
                relationship_count=len(result.published.relationships),
                content_digest=bundle["digest"],
                published_by=user,
                published_at=timezone.now(),
            )

            html = render_document(
                with_publication(
                    bundle,
                    {
                        "id": str(publication.id),
                        "sequence": publication.sequence,
                        "publishedAt": publication.published_at.isoformat(),
                    },
                )
            )
            validate_document(html)
    except PublicationError:
        raise
    except Model.DoesNotExist:
        raise
    except Exception as error:
        # Never log the document or the data; the ids are enough to investigate.
        logger.exception("Publishing model %s failed", model_id)
        raise PublicationGenerationFailed(
            "The publication could not be generated, so nothing was published. Please try again."
        ) from error

    logger.info("Published model %s as publication %s (revision %s)", model_id, publication.id, publication.source_revision)
    return PublishedArtifact(publication=publication, html=html)


__all__ = [
    "InvalidPublication",
    "Preview",
    "PublicationError",
    "PublicationGenerationFailed",
    "PublicationStale",
    "PublicationTooLarge",
    "PublishedArtifact",
    "load_canonical",
    "named_objects",
    "preview",
    "publish",
]
