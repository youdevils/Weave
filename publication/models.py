import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ImmutablePublicationError(Exception):
    """A Publication is a snapshot: once written it can never be edited."""


class PublicationQuerySet(models.QuerySet):
    """Refuses bulk edits so no code path can rewrite published history."""

    def update(self, **kwargs):
        raise ImmutablePublicationError("Publications are immutable and cannot be updated.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutablePublicationError("Publications are immutable and cannot be updated.")


class Publication(models.Model):
    """
    An immutable snapshot of one canonical revision of a Model, plus the scope
    and presentation it was published with.

    The record both *describes* the publication (what revision, which scope, how
    it was presented, what it contained via ``content_digest``) and *is* the
    snapshot: ``bundle`` holds the fully resolved graph, facets and provenance,
    so a View or a Download later reads back exactly what was published, never
    the live model. The rendered HTML itself is still never stored: it is
    produced on demand from ``bundle`` (at publish time, for validation; at View
    or Download time, for display), and forgotten again afterwards.

    A row only exists for a publication that generated successfully: publishing
    is a single transaction, so a failed attempt leaves nothing behind. "The most
    recent successful publication" is therefore simply the highest ``sequence``.
    """

    FORMAT_VERSION = 1

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="publications",
    )

    # 1, 2, 3 ... per model, assigned under the model row lock. Orders
    # publications without depending on timestamps (which can tie).
    sequence = models.PositiveIntegerField()

    # Model.revision at the moment of the snapshot.
    source_revision = models.PositiveIntegerField()

    # -- publication metadata ------------------------------------------------

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # The *suggested* download filename; the browser decides where it is saved.
    filename = models.CharField(max_length=120)

    # -- the definition that was applied (sanitised, versioned documents) -----

    scope = models.JSONField(default=dict)
    presentation = models.JSONField(default=dict)
    default_view = models.JSONField(default=dict)

    # The resolved snapshot: everything the portable Explorer needs, exactly as
    # published (see publication.services.bundle.build_bundle). This is what makes
    # the publication reproducible later, independent of the live model. A row
    # written before this field existed has ``{}`` here: there is no way to
    # reconstruct its bundle after the fact, so View/Download treat that as "no
    # snapshot available" rather than falling back to the live model.
    bundle = models.JSONField(default=dict)

    # Model.appearance as it was resolved into the file. Appearance is not
    # governed by revisions, so this is what makes the styling reproducible.
    appearance_snapshot = models.JSONField(default=dict)

    # -- what was published ----------------------------------------------------

    object_count = models.PositiveIntegerField(default=0)
    relationship_count = models.PositiveIntegerField(default=0)

    # sha256 of the embedded dataset (see publication.services.bundle).
    content_digest = models.CharField(max_length=64)
    format_version = models.PositiveSmallIntegerField(default=FORMAT_VERSION)

    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publications",
    )

    published_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = PublicationQuerySet.as_manager()

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["model", "sequence"],
                name="unique_publication_sequence_per_model",
            ),
        ]
        indexes = [
            models.Index(fields=["model", "-sequence"], name="publication_model_seq_idx"),
        ]

    def __str__(self):
        return f"{self.title} (#{self.sequence}, revision {self.source_revision})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutablePublicationError("Publications are immutable and cannot be saved again.")
        super().save(*args, **kwargs)
