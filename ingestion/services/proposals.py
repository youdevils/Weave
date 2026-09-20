"""
From a plan to one governed Proposal.

`create_import_proposal` is the only place an import writes anything besides its
own source row, and it writes through the existing Proposal services:

    lock the Model row -> cap check -> plan against the canonical model as it is
    *now* -> (blocked? refuse) -> (nothing to change? clean up, create nothing)
    -> one new WORKING proposal -> its changes -> one EvidenceReference per
    change pointing at the persisted source -> mark the source imported

All of it is one transaction: any failure leaves no proposal, no change, no
evidence and no half-imported source. Canonical data is never touched.
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ingestion.models import ImportSource
from ingestion.services import source_file
from ingestion.services.errors import ImportBlocked
from ingestion.services.parsing import parse_table
from ingestion.services.plan import ImportPlan
from ingestion.services.planner import build_plan
from model.models.model import Model
from model.services.proposal.evidence import EvidenceService
from model.services.proposal.proposal import ProposalService

TITLE_MAX_LENGTH = 200


@dataclass
class ImportResult:
    plan: ImportPlan
    proposal: object = None  # None when the import produced no changes

    @property
    def no_changes(self) -> bool:
        return self.proposal is None


def preview_import(model, source, mapping_payload) -> ImportPlan:
    """The plan for `source` under `mapping_payload`. Writes nothing."""

    table = parse_table(source.file_format, source_file.read_content(source))

    return build_plan(model, table, mapping_payload)


def create_import_proposal(model, user, source, mapping_payload) -> ImportResult:
    """
    Create the Working Proposal for an import, or report that there is nothing
    to change. `source` must be a staged source of `user` for `model` (the view
    resolves it that way).

    Raises ProposalLimitReached (the user's live-proposal cap), ImportBlocked
    (unresolved/ambiguous identity, ...), SourceFileError, TargetError or
    MappingError. In every such case nothing has been created.
    """

    with transaction.atomic():

        # Serialises with other imports and with proposal processing for this
        # model, so the cap check below and the insert are one step, and the
        # canonical data planned against cannot move under us.
        locked = Model.objects.select_for_update().get(pk=model.pk)

        ProposalService.assert_capacity(locked, user)

        table = parse_table(source.file_format, source_file.read_content(source))

        plan = build_plan(locked, table, mapping_payload)

        if plan.blocked:
            raise ImportBlocked(plan.problems)

        if not plan.changes:
            source_file.discard(source)
            return ImportResult(plan=plan)

        proposal = ProposalService.create_working(
            locked,
            user,
            title=f"Import: {source.original_filename}"[:TITLE_MAX_LENGTH],
        )

        EvidenceService.set_change_note(proposal, _change_note(source, plan))

        created = ProposalService.record_changes_bulk(
            proposal=proposal,
            specs=[change.to_spec() for change in plan.changes],
        )

        # One reference per change: a reference belongs to exactly one change,
        # so the same file is evidence many times over, independently.
        EvidenceService.add_for_changes(
            proposal,
            [change.id for change in created],
            source.stored_name,
            "",
            f"Data import: {source.original_filename}",
        )

        ImportSource.objects.filter(pk=source.pk).update(
            proposal=proposal,
            imported_at=timezone.now(),
        )

        return ImportResult(plan=plan, proposal=proposal)


def _change_note(source, plan) -> str:

    summary = plan.summary

    noun = "objects" if summary.kind == "object" else "relationships"

    return (
        f"Imported {source.original_filename}: {summary.creates} {noun} created, "
        f"{summary.updates} updated, {summary.no_ops} unchanged."
    )
