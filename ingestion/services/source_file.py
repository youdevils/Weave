"""
Persistence of uploaded import sources (see ingestion.models.ImportSource).

Everything about an uploaded file that is not parsing lives here: choosing the
format, generating the stored name, sanitising the display name, the staged
lifecycle, and the sweep of sources nothing refers to any more. Callers pass in
an already-authorised Model and user; no function here reads a request.
"""

import hashlib
import os
import unicodedata
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ingestion.models import ImportSource
from ingestion.services import limits
from ingestion.services.errors import SourceFileError
from ingestion.services.parsing import parse_table

EXTENSION_FORMATS = {
    ".csv": ImportSource.Format.CSV,
    ".xlsx": ImportSource.Format.XLSX,
    ".xls": ImportSource.Format.XLS,
}

DISPLAY_NAME_MAX_LENGTH = 200


def sanitise_filename(name) -> str:
    """
    A display-only rendition of an untrusted filename: no directory parts, no
    control or bidirectional-override characters, bounded length. It is never
    used as a path, a storage key or an identity.
    """

    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]

    cleaned = "".join(
        char
        for char in (" " if char.isspace() else char for char in name)
        if unicodedata.category(char) not in ("Cc", "Cf", "Cs", "Co", "Cn")
    )

    cleaned = " ".join(cleaned.split())

    if len(cleaned) > DISPLAY_NAME_MAX_LENGTH:
        stem, extension = os.path.splitext(cleaned)
        cleaned = stem[: DISPLAY_NAME_MAX_LENGTH - len(extension)] + extension

    return cleaned or "upload"


def detect_format(filename) -> str:
    """The format implied by the extension. The content is checked by the parser."""

    extension = os.path.splitext(sanitise_filename(filename))[1].lower()

    file_format = EXTENSION_FORMATS.get(extension)

    if file_format is None:
        raise SourceFileError(
            "Unsupported file type. Upload a .csv, .xlsx or .xls file.",
            code="unsupported_format",
        )

    return file_format


def generate_stored_name(file_format) -> str:
    return f"{uuid.uuid4().hex}.{file_format}"


@transaction.atomic
def store_upload(model, user, filename, data: bytes):
    """
    Validate and persist an upload as a *staged* source.

    The content is parsed here, so a file that cannot be read never becomes a
    source; the returned (source, table) carries what the upload step shows.
    The uploader's earlier staged sources for this model are replaced, and
    stale sources are swept.
    """

    if len(data) > limits.max_file_bytes():
        raise SourceFileError(
            f"The file is larger than the {limits.max_file_bytes() // (1024 * 1024)} MB limit.",
            code="file_too_large",
        )

    if not data:
        raise SourceFileError("The file is empty.", code="empty_file")

    file_format = detect_format(filename)

    table = parse_table(file_format, data)

    sweep(model)

    ImportSource.objects.filter(
        model=model,
        uploaded_by=user,
        imported_at__isnull=True,
    ).delete()

    source = ImportSource.objects.create(
        model=model,
        uploaded_by=user,
        original_filename=sanitise_filename(filename),
        stored_name=generate_stored_name(file_format),
        file_format=file_format,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        row_count=table.row_count,
        content=data,
    )

    return source, table


def get_staged_source(model, user, source_id) -> ImportSource:
    """
    The caller's own staged source for this model. Staged sources are private
    to their uploader: another Editor's id, an imported source, another
    model's source and a malformed id are all simply not found.
    """

    try:
        return ImportSource.objects.get(
            id=source_id,
            model=model,
            uploaded_by=user,
            imported_at__isnull=True,
        )
    except (ImportSource.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ImportSource.DoesNotExist("Import source not found.")


def read_content(source) -> bytes:
    return bytes(source.content)


def discard(source):
    source.delete()


def sweep(model):
    """
    Remove sources nothing refers to any more, opportunistically:

      * staged uploads older than the TTL (abandoned imports);
      * imported sources whose Proposal has since been abandoned (the
        Proposal's deletion leaves `proposal` NULL and takes every evidence
        reference with it).

    A source whose Proposal still exists is a model asset and is kept, even
    if individual changes or evidence have been discarded from it.
    """

    cutoff = timezone.now() - limits.staged_source_ttl()

    return ImportSource.objects.filter(model=model).filter(
        Q(imported_at__isnull=True, created_at__lt=cutoff)
        | Q(imported_at__isnull=False, proposal__isnull=True)
    ).delete()
