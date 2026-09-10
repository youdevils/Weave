from django.db import transaction
from django.utils import timezone

from model.models.proposal import Proposal, ProposalChange


class ProposalService:

    # -----------------------------------------------------------------
    # Proposal creation
    # -----------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def get_or_create_working(model, user):

        proposal = (
            Proposal.objects.select_for_update()
            .filter(
                model=model,
                created_by=user,
                source=Proposal.Source.USER,
                status=Proposal.Status.WORKING,
            )
            .first()
        )

        if proposal:
            return proposal

        return Proposal.objects.create(
            model=model,
            created_by=user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
            base_revision=model.revision,
        )

    @staticmethod
    @transaction.atomic
    def get_or_create_ai_proposal(model, user):

        proposal = (
            Proposal.objects.select_for_update()
            .filter(
                model=model,
                created_by=user,
                source=Proposal.Source.AI,
                status=Proposal.Status.WORKING,
            )
            .first()
        )

        if proposal:
            return proposal

        return Proposal.objects.create(
            model=model,
            created_by=user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
            base_revision=model.revision,
        )

    # -----------------------------------------------------------------
    # Validation state
    # -----------------------------------------------------------------

    @staticmethod
    def reset_validation(proposal):

        if proposal.validation_status == (Proposal.ValidationStatus.NOT_VALIDATED):
            return

        proposal.validation_status = Proposal.ValidationStatus.NOT_VALIDATED

        proposal.save(
            update_fields=[
                "validation_status",
                "updated_at",
            ]
        )

    # -----------------------------------------------------------------
    # Changes
    # -----------------------------------------------------------------

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
        parent_type="",
        parent_id=None,
    ):

        if proposal.status != Proposal.Status.WORKING:
            raise ValueError("Changes can only be recorded against a working proposal.")

        source = (
            ProposalChange.Source.AI
            if proposal.source == Proposal.Source.AI
            else ProposalChange.Source.USER
        )

        changes = proposal.changes.filter(
            target_type=target_type,
            target_id=target_id,
        )

        # -------------------------------------------------------------
        # Field-level changes
        #
        # Multiple fields on the same target are separate changes.
        # -------------------------------------------------------------

        if field is not None:
            changes = changes.filter(
                after__field=field,
            )

        change = changes.first()

        if change:

            change.operation = operation
            change.source = source
            change.parent_type = parent_type
            change.parent_id = parent_id
            change.before = before
            change.after = after

            # Editing a previously reviewed change makes it
            # unreviewed again.
            change.review_status = ProposalChange.ReviewStatus.UNREVIEWED

            change.save(
                update_fields=[
                    "operation",
                    "source",
                    "parent_type",
                    "parent_id",
                    "before",
                    "after",
                    "review_status",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(proposal)

            return change

        change = ProposalChange.objects.create(
            proposal=proposal,
            source=source,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            parent_type=parent_type,
            parent_id=parent_id,
            before=before,
            after=after,
        )

        ProposalService.reset_validation(proposal)

        return change

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

        result = changes.delete()

        if result[0] > 0:
            ProposalService.reset_validation(proposal)

        return result

    # -----------------------------------------------------------------
    # Proposal lifecycle
    # -----------------------------------------------------------------

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

        if not proposal.changes.exists():
            raise ValueError("A proposal must contain at least one change.")

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
