"""
Evidence file validation and storage for an Assisted Create setup request.
Not a second ingestion subsystem: no parsing, no staging/TTL lifecycle --
just enough to store bytes so the Celery worker (running later, in a
different process) can read what the user attached.
"""

import hashlib

from django.conf import settings

from assisted.models import AssistedTaskEvidence


class AssistedEvidenceInvalid(ValueError):
    """The supplied evidence files are not usable."""


def create_evidence(task, files) -> None:
    if len(files) > settings.ASSISTED_MAX_EVIDENCE_FILES:
        raise AssistedEvidenceInvalid(f"Attach at most {settings.ASSISTED_MAX_EVIDENCE_FILES} files.")

    total = 0
    for f in files:
        if f.size > settings.ASSISTED_MAX_EVIDENCE_FILE_BYTES:
            raise AssistedEvidenceInvalid(f"'{f.name}' is larger than the per-file limit.")
        total += f.size

    if total > settings.ASSISTED_MAX_EVIDENCE_TOTAL_BYTES:
        raise AssistedEvidenceInvalid("The attached files are too large in total.")

    for f in files:
        data = f.read()
        AssistedTaskEvidence.objects.create(
            task=task,
            original_filename=f.name[:255],
            content_type=(f.content_type or "")[:100],
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content=data,
        )
