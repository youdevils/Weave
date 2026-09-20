from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count

from model.models.evidence_reference import EvidenceReference
from model.models.proposal import Proposal, ProposalChange

EDITABLE_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.FAILED,
)

SOURCE_MAX_LENGTH = EvidenceReference._meta.get_field("source").max_length
LOCATOR_MAX_LENGTH = EvidenceReference._meta.get_field("locator").max_length
NOTE_MAX_LENGTH = 2000
CHANGE_NOTE_MAX_LENGTH = 2000
MAX_EVIDENCE_PER_CHANGE = 20


class EvidenceService:
    """
    Manual management of Evidence References and the proposal-level Change
    Note, from Proposal Review.

    Evidence and the Change Note are optional context. Nothing here touches a
    change's review_status or the proposal's validation_status, and nothing
    in validation or submission reads them. This is also the one entry point
    other mechanisms should use to attach evidence to a change.

    Lookups go through the proposal (`proposal.changes`,
    `change__proposal=proposal`), so an id belonging to another proposal is
    simply not found.
    """

    # -----------------------------------------------------------------
    # Guards / normalisation
    # -----------------------------------------------------------------

    @staticmethod
    def _require_editable(proposal):

        if proposal.status not in EDITABLE_STATUSES:
            raise ValueError("Evidence can only be edited on an editable proposal.")

    @staticmethod
    def _clean(source, locator, note):

        source = (source or "").strip()
        locator = (locator or "").strip()
        note = (note or "").strip()

        if not source:
            raise ValueError("Evidence needs a source.")

        if len(source) > SOURCE_MAX_LENGTH:
            raise ValueError(f"Source can be at most {SOURCE_MAX_LENGTH} characters.")

        if len(locator) > LOCATOR_MAX_LENGTH:
            raise ValueError(f"Locator can be at most {LOCATOR_MAX_LENGTH} characters.")

        if len(note) > NOTE_MAX_LENGTH:
            raise ValueError(f"Note can be at most {NOTE_MAX_LENGTH} characters.")

        return source, locator, note

    @staticmethod
    def _get_evidence(proposal, evidence_id):

        try:
            evidence = EvidenceReference.objects.select_related("change").filter(
                id=evidence_id,
                change__proposal=proposal,
            ).first()
        except (ValueError, TypeError, ValidationError):
            # Not a valid UUID.
            evidence = None

        if evidence is None:
            raise EvidenceReference.DoesNotExist("Evidence not found.")

        return evidence

    # -----------------------------------------------------------------
    # Evidence
    # -----------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def add(proposal, change_id, source, locator="", note=""):
        """
        Attach a new Evidence Reference to one change of the proposal.
        Raises ValueError for invalid input or a locked proposal, and
        ProposalChange.DoesNotExist if the change is not in the proposal.
        """

        EvidenceService._require_editable(proposal)

        source, locator, note = EvidenceService._clean(source, locator, note)

        try:
            change = proposal.changes.filter(id=change_id).first()
        except (ValueError, TypeError, ValidationError):
            change = None

        if change is None:
            raise ProposalChange.DoesNotExist("Change not found.")

        if change.evidence.count() >= MAX_EVIDENCE_PER_CHANGE:
            raise ValueError(
                f"A change can have at most {MAX_EVIDENCE_PER_CHANGE} evidence references."
            )

        return EvidenceReference.objects.create(
            change=change,
            source=source,
            locator=locator,
            note=note,
        )

    @staticmethod
    @transaction.atomic
    def add_for_changes(proposal, change_ids, source, locator="", note=""):
        """
        Attach an identical, independent Evidence Reference to each of many
        changes of the proposal (one reference per change -- a reference
        belongs to exactly one change). The bulk counterpart of `add` for
        mechanisms such as Data Import that evidence every change they
        create with the same source.

        Same guards as `add`: editable proposal, valid input, every id must be
        a change of this proposal, and the per-change cap.
        """

        EvidenceService._require_editable(proposal)

        source, locator, note = EvidenceService._clean(source, locator, note)

        change_ids = list(change_ids)

        found = {
            change.id: change
            for change in proposal.changes.filter(id__in=change_ids).annotate(
                evidence_total=Count("evidence")
            )
        }

        if len(found) != len(set(change_ids)):
            raise ProposalChange.DoesNotExist("Change not found.")

        if any(change.evidence_total >= MAX_EVIDENCE_PER_CHANGE for change in found.values()):
            raise ValueError(
                f"A change can have at most {MAX_EVIDENCE_PER_CHANGE} evidence references."
            )

        return EvidenceReference.objects.bulk_create(
            [
                EvidenceReference(
                    change_id=change_id,
                    source=source,
                    locator=locator,
                    note=note,
                )
                for change_id in change_ids
            ],
            batch_size=1000,
        )

    @staticmethod
    @transaction.atomic
    def update(proposal, evidence_id, source, locator="", note=""):

        EvidenceService._require_editable(proposal)

        source, locator, note = EvidenceService._clean(source, locator, note)

        evidence = EvidenceService._get_evidence(proposal, evidence_id)

        evidence.source = source
        evidence.locator = locator
        evidence.note = note
        evidence.save(update_fields=["source", "locator", "note", "updated_at"])

        return evidence

    @staticmethod
    @transaction.atomic
    def remove(proposal, evidence_id):
        """Returns the change the evidence belonged to."""

        EvidenceService._require_editable(proposal)

        evidence = EvidenceService._get_evidence(proposal, evidence_id)
        change = evidence.change

        evidence.delete()

        return change

    # -----------------------------------------------------------------
    # Change note
    # -----------------------------------------------------------------

    @staticmethod
    def set_change_note(proposal, text):
        """
        Set (or, with blank text, clear) the proposal's Change Note. Stored
        in Proposal.summary.
        """

        EvidenceService._require_editable(proposal)

        text = (text or "").strip()

        if len(text) > CHANGE_NOTE_MAX_LENGTH:
            raise ValueError(
                f"A change note can be at most {CHANGE_NOTE_MAX_LENGTH} characters."
            )

        proposal.summary = text
        proposal.save(update_fields=["summary", "updated_at"])

        return proposal
