from django.db import transaction
from django.utils import timezone

from model.models.proposal import Proposal, ProposalChange


class ProposalService:

    @staticmethod
    @transaction.atomic
    def get_or_create_working(model, user):

        proposal = (
            Proposal.objects.select_for_update()
            .filter(
                model=model,
                created_by=user,
                status=Proposal.Status.WORKING,
            )
            .first()
        )

        if proposal:
            return proposal

        return Proposal.objects.create(
            model=model,
            created_by=user,
            status=Proposal.Status.WORKING,
            base_revision=model.revision,
        )

    @staticmethod
    @transaction.atomic
    def record_change(
        *,
        proposal,
        operation,
        target_type,
        target_id,
        before,
        after,
        field=None,
    ):

        if proposal.status != Proposal.Status.WORKING:
            raise ValueError("Changes can only be recorded against a working proposal.")

        changes = proposal.changes.filter(
            target_type=target_type,
            target_id=target_id,
        )

        if field is not None:
            changes = changes.filter(
                after__field=field,
            )

        change = changes.first()

        if change:
            change.operation = operation
            change.before = before
            change.after = after

            change.save(
                update_fields=[
                    "operation",
                    "before",
                    "after",
                    "updated_at",
                ]
            )

            return change

        return ProposalChange.objects.create(
            proposal=proposal,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
        )

    @staticmethod
    @transaction.atomic
    def discard_change(
        *,
        proposal,
        target_type,
        target_id,
        field=None,
    ):

        if proposal.status != Proposal.Status.WORKING:
            raise ValueError("Changes can only be discarded from a working proposal.")

        changes = proposal.changes.filter(
            target_type=target_type,
            target_id=target_id,
        )

        if field is not None:
            changes = changes.filter(
                after__field=field,
            )

        return changes.delete()

    @staticmethod
    @transaction.atomic
    def abandon(proposal):

        if proposal.status != Proposal.Status.WORKING:
            raise ValueError("Only working proposals can be abandoned.")

        proposal.delete()

    @staticmethod
    @transaction.atomic
    def submit(proposal):

        if proposal.status != Proposal.Status.WORKING:
            raise ValueError("Only working proposals can be submitted.")

        proposal.status = Proposal.Status.PROPOSED
        proposal.submitted_at = timezone.now()

        proposal.save(
            update_fields=[
                "status",
                "submitted_at",
                "updated_at",
            ]
        )

        return proposal
