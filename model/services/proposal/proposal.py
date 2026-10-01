from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.appearance import AppearanceService

EDITABLE_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.FAILED,
)

LIVE_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.FAILED,
    Proposal.Status.QUEUED,
    Proposal.Status.PROCESSING,
)


class ProposalLimitReached(Exception):
    """The user already has the maximum number of live proposals for the model."""


class ProposalService:

    # -----------------------------------------------------------------
    # Live proposals
    # -----------------------------------------------------------------

    @staticmethod
    def live_queryset(model, user):
        """
        Every proposal that belongs in the active workspace: WORKING /
        FAILED / QUEUED / PROCESSING, plus COMPLETED proposals not yet
        acknowledged. Used by both the sidebar list and the live-proposal
        cap check. Scoped to one user on one model.
        """

        return Proposal.objects.filter(
            model=model,
            created_by=user,
        ).filter(
            Q(status__in=LIVE_STATUSES)
            | Q(
                status=Proposal.Status.COMPLETED,
                acknowledged_at__isnull=True,
            )
        )

    @staticmethod
    def assert_capacity(model, user):
        """
        Raise ProposalLimitReached if `user` may not start another proposal.

        The count is only trustworthy while the caller holds the Model row
        lock (see create_working); on its own it is a cheap early check.
        """

        if (
            ProposalService.live_queryset(model, user).count()
            >= settings.PROPOSAL_MAX_LIVE_PER_MODEL
        ):
            raise ProposalLimitReached(
                f"You have reached the maximum of "
                f"{settings.PROPOSAL_MAX_LIVE_PER_MODEL} active proposals "
                "for this model. Submit, resolve, or delete one before "
                "starting another."
            )

    @staticmethod
    @transaction.atomic
    def create_working(model, user, *, title="", summary="", source=Proposal.Source.USER):
        """
        Always create a new WORKING proposal (never reuses an existing one),
        subject to the live-proposal cap.

        The Model row is locked (the same lock proposal claiming and
        processing take) so the cap check and the insert are one serialised
        step: two concurrent callers cannot both observe a free slot.
        """

        locked = Model.objects.select_for_update().get(pk=model.pk)

        ProposalService.assert_capacity(locked, user)

        return Proposal.objects.create(
            model=locked,
            created_by=user,
            source=source,
            status=Proposal.Status.WORKING,
            base_revision=locked.revision,
            title=(title or "")[:200],
            summary=summary or "",
        )

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
                status__in=(
                    Proposal.Status.WORKING,
                    Proposal.Status.FAILED,
                ),
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

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            raise ValueError("Changes can only be recorded against an editable proposal.")

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
    def record_changes_bulk(*, proposal, specs):
        """
        Insert many new changes in one go. Each spec is a dict with
        operation, target_type, target_id, before, after and optionally
        parent_type / parent_id / field.

        This is `record_change` for the case where the caller has already
        collapsed its input to exactly one change per (target, field): there
        is nothing to upsert, so the per-change lookup is skipped. The
        editable-status guard and the change source are derived exactly as
        record_change does, and validation is reset once.
        """

        if proposal.status not in EDITABLE_STATUSES:
            raise ValueError("Changes can only be recorded against an editable proposal.")

        source = (
            ProposalChange.Source.AI
            if proposal.source == Proposal.Source.AI
            else ProposalChange.Source.USER
        )

        changes = [
            ProposalChange(
                proposal=proposal,
                source=source,
                operation=spec["operation"],
                target_type=spec["target_type"],
                target_id=spec["target_id"],
                parent_type=spec.get("parent_type", ""),
                parent_id=spec.get("parent_id"),
                before=spec["before"],
                after=spec["after"],
            )
            for spec in specs
        ]

        created = ProposalChange.objects.bulk_create(changes, batch_size=1000)

        ProposalService.reset_validation(proposal)

        return created

    @staticmethod
    @transaction.atomic
    def discard_change(
        *,
        proposal,
        target_type,
        target_id,
        field=None,
    ):

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            raise ValueError("Changes can only be discarded from an editable proposal.")

        changes = proposal.changes.filter(
            target_type=target_type,
            target_id=target_id,
        )

        if field is not None:
            changes = changes.filter(
                after__field=field,
            )

        discarded_type_create = changes.filter(
            operation=ProposalChange.Operation.CREATE,
            target_type__in=("ObjectType", "RelationshipType"),
        ).exists()

        result = changes.delete()

        if result[0] > 0:
            ProposalService.reset_validation(proposal)

        if discarded_type_create:
            # A proposed-only type is gone: drop any style saved against it.
            AppearanceService.prune(proposal.model)

        return result

    @staticmethod
    @transaction.atomic
    def discard_children(
        *,
        proposal,
        parent_type,
        parent_id,
        child_target_types,
    ):
        """
        Discard every change addressed to a child of (parent_type,
        parent_id), restricted to child_target_types. Used when a
        proposal-only parent (e.g. an ObjectType/RelationshipType
        CREATE) is discarded, so its downstream proposal-only children
        don't become dangling references in the working proposal.

        Returns {target_type: {target_id, ...}} so a caller can chain
        a further, non-parent/child-shaped cascade (e.g. discarding a
        Relationship that references a just-discarded Object, which
        isn't addressed via parent_type/parent_id).
        """

        child_changes = proposal.changes.filter(
            parent_type=parent_type,
            parent_id=parent_id,
            target_type__in=child_target_types,
        )

        target_ids_by_type = {}

        for change in child_changes:
            target_ids_by_type.setdefault(change.target_type, set()).add(change.target_id)

        for target_type, target_ids in target_ids_by_type.items():
            for target_id in target_ids:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type=target_type,
                    target_id=target_id,
                )

        return target_ids_by_type

    # -----------------------------------------------------------------
    # Proposal lifecycle
    # -----------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def abandon(proposal):

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            raise ValueError("Only editable proposals can be abandoned.")

        model = proposal.model
        proposal.delete()

        # Styles saved against types only this proposal introduced are now orphaned.
        AppearanceService.prune(model)

    @staticmethod
    @transaction.atomic
    def submit(proposal):

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            raise ValueError("Only editable proposals can be submitted.")

        if not proposal.changes.exists():
            raise ValueError("A proposal must contain at least one change.")

        proposal.status = Proposal.Status.QUEUED
        proposal.submitted_at = timezone.now()

        proposal.save(
            update_fields=[
                "status",
                "submitted_at",
                "updated_at",
            ]
        )

        def _dispatch():
            from model.tasks.proposal_tasks import process_next_for_model

            process_next_for_model.delay(str(proposal.model_id))

        transaction.on_commit(_dispatch)

        return proposal
