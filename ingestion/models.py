import uuid

from django.conf import settings
from django.db import models


class ImportSource(models.Model):
    """
    An uploaded structured file (CSV / XLSX / XLS) that a Data Import reads,
    persisted as a model-owned source artifact.

    Conceptually distinct from Evidence: this is the artifact, while each
    ProposalChange an import produces gets its own EvidenceReference whose
    text `source` is this row's `stored_name` -- a generated, unique name, so
    the reference identifies one specific file rather than a possibly
    duplicated original filename (which is kept only for display).

    The bytes live in the database, not on disk: nothing is served or
    executable, rollback is transactional with the Proposal, and deleting the
    Model (FK cascade) removes them. Only ingestion.services touches
    `content`; it is deferred out of ordinary queries.

    Lifecycle: created *staged* (imported_at NULL) at upload and private to
    its uploader. An import that yields changes stamps imported_at and records
    the Proposal; from then on it is a model asset for as long as that
    Proposal exists. An import with no changes deletes it, and abandoned
    uploads / proposals are swept (ingestion.services.source_file.sweep).
    """

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel workbook (.xlsx)"
        XLS = "xls", "Excel 97-2003 (.xls)"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    model = models.ForeignKey(
        "model.Model",
        on_delete=models.CASCADE,
        related_name="import_sources",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="import_sources",
    )

    # The Proposal this source produced. SET_NULL: abandoning the Proposal
    # leaves the source unreferenced, which the sweep then removes.
    proposal = models.ForeignKey(
        "model.Proposal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_sources",
    )

    # Display metadata only, sanitised; never used as a path or identity.
    original_filename = models.CharField(
        max_length=255,
    )

    # Generated "<uuid4 hex>.<ext>". This is what EvidenceReference.source holds.
    stored_name = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
    )

    file_format = models.CharField(
        max_length=10,
        choices=Format.choices,
    )

    size_bytes = models.PositiveIntegerField()

    sha256 = models.CharField(
        max_length=64,
    )

    row_count = models.PositiveIntegerField(
        default=0,
    )

    content = models.BinaryField(
        editable=False,
    )

    imported_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["model", "imported_at"]),
        ]

    def __str__(self):
        return self.original_filename
