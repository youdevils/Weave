import uuid

from django.db import models


class EvidenceReference(models.Model):
    """
    A deliberately generic pointer to whatever supports a single
    ProposalChange: a document, a URL, a conversation, a ticket.

    It belongs to exactly one persisted ProposalChange. Deleting the
    change (discarding it, abandoning its proposal) deletes its evidence
    with it; committing the proposal leaves the evidence in place so it
    remains available for provenance.

    Not to be confused with ProposalChange.source, which is who authored
    the change (user / AI). Here `source` is free text naming the evidence
    itself; `locator` says where inside it to look (page, section, URL
    fragment); `note` is any human comment.

    Evidence is optional and never takes part in proposal validation,
    submission or approval.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    change = models.ForeignKey(
        "model.ProposalChange",
        on_delete=models.CASCADE,
        related_name="evidence",
    )

    source = models.CharField(
        max_length=500,
    )

    locator = models.CharField(
        max_length=500,
        blank=True,
    )

    note = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.source
