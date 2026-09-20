from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from model.models.evidence_reference import EvidenceReference
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.evidence import EvidenceService
from model.services.proposal.proposal import ProposalService
from model.services.proposal.review import ProposalReviewService
from model.views.active_proposal import (
    clear_active_proposal_id,
    get_or_create_active_proposal,
    set_active_proposal_id,
)
from model.views.common_context import get_model_context
from model.views.sidebar import with_updated_sidebar

EDITABLE_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.FAILED,
)


@login_required
@with_updated_sidebar
def proposal_create(request, model_id):
    """
    POST-only. Creates a brand-new WORKING proposal and makes it
    active immediately ("+ New proposal" in the sidebar). Subject to
    the same live-proposal cap as the implicit auto-create path.
    """

    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Method not allowed."},
            status=405,
        )

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    # Force creation of a NEW proposal even if one is already active:
    # clear the session pointer first so get_or_create_active_proposal
    # can't just resolve the existing one.
    clear_active_proposal_id(request, model.id)

    new_proposal, error_response = get_or_create_active_proposal(
        request,
        model,
        request.user,
    )

    if error_response is not None:
        return error_response

    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse(
                "model:proposal",
                args=[model.id, new_proposal.id],
            ),
        }
    )


@login_required
def proposal(request, model_id, proposal_id=None):

    # -------------------------------------------------------------
    # Common model context
    # -------------------------------------------------------------

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    # -------------------------------------------------------------
    # No proposal specified: resolve to the active one, else the
    # most recently touched live proposal, else render the empty
    # workspace state directly.
    # -------------------------------------------------------------

    if proposal_id is None:

        active = context["active_proposal"]

        if active is not None:
            return redirect(
                "model:proposal",
                model_id=model.id,
                proposal_id=active.id,
            )

        proposals = context["proposals"]

        if proposals:
            return redirect(
                "model:proposal",
                model_id=model.id,
                proposal_id=proposals[0].id,
            )

        context.update(
            {
                "proposal": None,
                "changes": [],
                "change_groups": [],
                "reviewed_count": 0,
                "unreviewed_count": 0,
                "total_count": 0,
            }
        )

        return render(
            request,
            "model/proposal.html",
            context,
        )

    target_proposal = get_object_or_404(
        Proposal,
        id=proposal_id,
        model=model,
        created_by=request.user,
    )

    is_editable = target_proposal.status in EDITABLE_STATUSES

    # -------------------------------------------------------------
    # Selecting an editable proposal makes it active. There is no
    # separate "set active" workflow -- viewing IS selecting for a
    # WORKING/FAILED proposal. Read-only statuses never become the
    # active editing target.
    # -------------------------------------------------------------

    if is_editable:
        set_active_proposal_id(request, model.id, target_proposal.id)

    # -------------------------------------------------------------
    # POST actions
    # -------------------------------------------------------------

    if request.method == "POST":

        action = request.POST.get("action")

        # -----------------------------------------------------------
        # Rename -- allowed in any status, including read-only ones
        # (the review page's naming control is not gated on
        # editability).
        # -----------------------------------------------------------

        if action == "rename":

            title = request.POST.get("title", "").strip()[:200]

            target_proposal.title = title

            target_proposal.save(
                update_fields=[
                    "title",
                    "updated_at",
                ]
            )

            return JsonResponse(
                {
                    "success": True,
                    "title": target_proposal.title,
                }
            )

        # -----------------------------------------------------------
        # Acknowledge -- only valid once COMPLETED
        # -----------------------------------------------------------

        if action == "acknowledge":

            if target_proposal.status != Proposal.Status.COMPLETED:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Only a completed proposal can be acknowledged.",
                    },
                    status=400,
                )

            if target_proposal.acknowledged_at is None:

                target_proposal.acknowledged_at = timezone.now()

                target_proposal.save(
                    update_fields=[
                        "acknowledged_at",
                        "updated_at",
                    ]
                )

            clear_active_proposal_id(request, model.id)

            return JsonResponse(
                {
                    "success": True,
                    "redirect_url": reverse(
                        "model:proposal_list",
                        args=[model.id],
                    ),
                }
            )

        # -----------------------------------------------------------
        # Abandon -- only valid on an editable proposal
        # -----------------------------------------------------------

        if action == "abandon":

            if not is_editable:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Only an editable proposal can be deleted.",
                    },
                    status=400,
                )

            try:
                ProposalService.abandon(target_proposal)
            except ValueError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)},
                    status=400,
                )

            clear_active_proposal_id(request, model.id)

            return JsonResponse(
                {
                    "success": True,
                    "redirect_url": reverse(
                        "model:proposal_list",
                        args=[model.id],
                    ),
                }
            )

        # -----------------------------------------------------------
        # Submit ("Validate & Commit") -- only valid on an editable
        # proposal. Queues the proposal for the Celery pipeline and
        # returns immediately -- the page does not wait for
        # processing to finish.
        # -----------------------------------------------------------

        if action == "submit":

            if not is_editable:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "This proposal is locked and cannot be submitted.",
                    },
                    status=400,
                )

            try:
                ProposalService.submit(target_proposal)
            except ValueError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)},
                    status=400,
                )

            return JsonResponse({"success": True})

        # -----------------------------------------------------------
        # Everything else (discard/review/unreview/review_all/
        # unreview_all) requires an editable proposal, same as today.
        # -----------------------------------------------------------

        if not is_editable:
            return JsonResponse(
                {"error": "This proposal is locked and cannot be modified."},
                status=400,
            )

        # ---------------------------------------------------------
        # Change note (proposal-level, optional) and evidence
        # references (per change, optional). Neither affects review
        # status, validation or submission.
        # ---------------------------------------------------------

        if action == "set_change_note":

            try:
                EvidenceService.set_change_note(
                    target_proposal,
                    request.POST.get("change_note", ""),
                )
            except ValueError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)},
                    status=400,
                )

            return JsonResponse(
                {
                    "success": True,
                    "change_note": target_proposal.summary,
                }
            )

        if action in ("add_evidence", "update_evidence", "remove_evidence"):

            try:

                if action == "add_evidence":

                    evidence = EvidenceService.add(
                        target_proposal,
                        request.POST.get("change_id"),
                        request.POST.get("source"),
                        request.POST.get("locator"),
                        request.POST.get("note"),
                    )

                    change = evidence.change

                elif action == "update_evidence":

                    evidence = EvidenceService.update(
                        target_proposal,
                        request.POST.get("evidence_id"),
                        request.POST.get("source"),
                        request.POST.get("locator"),
                        request.POST.get("note"),
                    )

                    change = evidence.change

                else:

                    change = EvidenceService.remove(
                        target_proposal,
                        request.POST.get("evidence_id"),
                    )

            except (ProposalChange.DoesNotExist, EvidenceReference.DoesNotExist):
                return JsonResponse(
                    {"success": False, "error": "Not found."},
                    status=404,
                )

            except ValueError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)},
                    status=400,
                )

            return JsonResponse(
                {
                    "success": True,
                    "change_id": str(change.id),
                    "html": render_to_string(
                        "model/_proposal_evidence.html",
                        {"change": change},
                        request=request,
                    ),
                }
            )

        # ---------------------------------------------------------
        # Discard a single change
        # ---------------------------------------------------------

        if action == "discard":

            change_id = request.POST.get("change_id")

            change = target_proposal.changes.filter(
                id=change_id,
            ).first()

            if not change:
                return JsonResponse(
                    {"error": "Change not found."},
                    status=404,
                )

            field_name = change.after.get("field") if change.after else None

            try:
                ProposalService.discard_change(
                    proposal=target_proposal,
                    target_type=change.target_type,
                    target_id=change.target_id,
                    field=field_name,
                )
            except ValueError as exc:
                return JsonResponse(
                    {"error": str(exc)},
                    status=400,
                )

            return JsonResponse(
                {
                    "success": True,
                    "change_id": str(change.id),
                }
            )

        # ---------------------------------------------------------
        # Mark a single change reviewed
        # ---------------------------------------------------------

        if action == "review":

            change_id = request.POST.get("change_id")

            change = target_proposal.changes.filter(
                id=change_id,
            ).first()

            if not change:
                return JsonResponse(
                    {"error": "Change not found."},
                    status=404,
                )

            change.review_status = ProposalChange.ReviewStatus.REVIEWED

            change.save(
                update_fields=[
                    "review_status",
                    "updated_at",
                ]
            )

            return JsonResponse(
                {
                    "success": True,
                    "change_id": str(change.id),
                    "review_status": (change.review_status),
                }
            )

        # ---------------------------------------------------------
        # Mark a single change unreviewed
        # ---------------------------------------------------------

        if action == "unreview":

            change_id = request.POST.get("change_id")

            change = target_proposal.changes.filter(
                id=change_id,
            ).first()

            if not change:
                return JsonResponse(
                    {"error": "Change not found."},
                    status=404,
                )

            change.review_status = ProposalChange.ReviewStatus.UNREVIEWED

            change.save(
                update_fields=[
                    "review_status",
                    "updated_at",
                ]
            )

            return JsonResponse(
                {
                    "success": True,
                    "change_id": str(change.id),
                    "review_status": (change.review_status),
                }
            )

        # ---------------------------------------------------------
        # Bulk review
        # ---------------------------------------------------------

        if action == "review_all":

            target_proposal.changes.filter(
                review_status=(ProposalChange.ReviewStatus.UNREVIEWED),
            ).update(
                review_status=(ProposalChange.ReviewStatus.REVIEWED),
            )

            return JsonResponse({"success": True})

        # ---------------------------------------------------------
        # Bulk unreview
        # ---------------------------------------------------------

        if action == "unreview_all":

            target_proposal.changes.filter(
                review_status=(ProposalChange.ReviewStatus.REVIEWED),
            ).update(
                review_status=(ProposalChange.ReviewStatus.UNREVIEWED),
            )

            return JsonResponse({"success": True})

        return JsonResponse(
            {"error": "Invalid action."},
            status=400,
        )

    # -------------------------------------------------------------
    # GET: fetch the latest submission result (if any) up front, so
    # both the read-only branches and the WORKING/FAILED branch below
    # can use it.
    # -------------------------------------------------------------

    submission_result = getattr(target_proposal, "submission_result", None)

    validation_errors_by_change = {}
    unlinked_validation_errors = []

    if submission_result is not None:

        for err in submission_result.errors.select_related("change").all():

            if err.change_id:
                validation_errors_by_change.setdefault(err.change_id, []).append(err)
            else:
                unlinked_validation_errors.append(err)

    # -------------------------------------------------------------
    # QUEUED / PROCESSING: fixed read-only summary states, no
    # search/filter/sort/group machinery.
    # -------------------------------------------------------------

    if target_proposal.status in (
        Proposal.Status.QUEUED,
        Proposal.Status.PROCESSING,
    ):

        context.update(
            {
                "proposal": target_proposal,
                "changes": [],
                "change_groups": [],
                "total_count": target_proposal.changes.count(),
            }
        )

        return render(
            request,
            "model/proposal.html",
            context,
        )

    # -------------------------------------------------------------
    # COMPLETED: fixed read-only success state.
    # -------------------------------------------------------------

    if target_proposal.status == Proposal.Status.COMPLETED:

        context.update(
            {
                "proposal": target_proposal,
                "submission_result": submission_result,
                "changes": [],
                "change_groups": [],
                "total_count": target_proposal.changes.count(),
            }
        )

        return render(
            request,
            "model/proposal.html",
            context,
        )

    # -------------------------------------------------------------
    # WORKING / FAILED: the full review-table experience.
    # -------------------------------------------------------------

    # -------------------------------------------------------------
    # Base queryset
    # -------------------------------------------------------------

    changes = (
        target_proposal.changes.all()
        .prefetch_related("evidence")
        .order_by("created_at")
    )

    # -------------------------------------------------------------
    # Search
    # -------------------------------------------------------------

    search = request.GET.get(
        "q",
        "",
    ).strip()

    if search:

        changes = changes.filter(
            Q(target_type__icontains=search)
            | Q(parent_type__icontains=search)
            | Q(after__icontains=search)
            | Q(before__icontains=search)
        )

    # -------------------------------------------------------------
    # Filters
    # -------------------------------------------------------------

    review_filter = request.GET.get(
        "review",
        "all",
    )

    operation_filter = request.GET.get(
        "operation",
        "all",
    )

    if review_filter == "reviewed":

        changes = changes.filter(review_status=(ProposalChange.ReviewStatus.REVIEWED))

    elif review_filter == "unreviewed":

        changes = changes.filter(review_status=(ProposalChange.ReviewStatus.UNREVIEWED))

    if operation_filter in {
        ProposalChange.Operation.CREATE,
        ProposalChange.Operation.UPDATE,
        ProposalChange.Operation.DELETE,
    }:

        changes = changes.filter(
            operation=operation_filter,
        )

    # -------------------------------------------------------------
    # Target type filter
    # -------------------------------------------------------------

    target_filter = request.GET.get(
        "target",
        "all",
    )

    valid_target_types = {
        "Model",
        "ObjectType",
        "RelationshipType",
        "AttributeDefinition",
        "RelationshipTypeRule",
        "Object",
        "Relationship",
    }

    if target_filter in valid_target_types:

        changes = changes.filter(
            target_type=target_filter,
        )

    # -------------------------------------------------------------
    # Sorting
    # -------------------------------------------------------------

    sort = request.GET.get(
        "sort",
        "created",
    )

    sort_map = {
        "created": "created_at",
        "created_desc": "-created_at",
        "operation": "operation",
        "operation_desc": "-operation",
        "target": "target_type",
        "target_desc": "-target_type",
        "review": "review_status",
        "review_desc": "-review_status",
    }

    sort_field = sort_map.get(
        sort,
        "created_at",
    )

    changes = changes.order_by(
        sort_field,
        "created_at",
    )

    # -------------------------------------------------------------
    # Counts
    #
    # These deliberately come from the complete proposal rather
    # than the filtered queryset.
    # -------------------------------------------------------------

    proposal_changes = target_proposal.changes.all()

    total_count = proposal_changes.count()

    reviewed_count = proposal_changes.filter(
        review_status=(ProposalChange.ReviewStatus.REVIEWED)
    ).count()

    unreviewed_count = total_count - reviewed_count

    # -------------------------------------------------------------
    # Available filter values
    # -------------------------------------------------------------

    target_types = (
        target_proposal.changes.values_list(
            "target_type",
            flat=True,
        )
        .distinct()
        .order_by("target_type")
    )

    # -------------------------------------------------------------
    # Grouping
    # -------------------------------------------------------------

    # Materialise the filtered queryset once. This lets us attach
    # presentation metadata to each change without querying the
    # database from the template.
    change_list = list(changes)

    # Resolve all parent and target objects in one presentation-layer
    # operation, plus a fallback lookup for proposal-only CREATEs that
    # don't exist in the canonical database yet.
    parents = ProposalReviewService.resolve_parents(
        change_list,
    )

    targets = ProposalReviewService.resolve_targets(
        change_list,
    )

    create_lookup = ProposalReviewService.build_create_lookup(
        change_list,
    )

    object_type_names = ProposalReviewService.resolve_object_type_names(
        change_list,
        create_lookup,
    )

    object_names = ProposalReviewService.resolve_object_names(
        change_list,
        create_lookup,
    )

    # Attach presentation metadata to each change.
    for change in change_list:

        change.review_label = ProposalReviewService.change_label(
            change,
        )

        change.review_target = ProposalReviewService.change_target(
            change,
            targets,
            create_lookup,
            object_type_names,
            object_names,
        )

        change.review_parent = ProposalReviewService.change_parent_context(
            change,
            parents,
            create_lookup,
        )

        change.review_validation_errors = validation_errors_by_change.get(
            change.id,
            [],
        )

    group_by = request.GET.get(
        "group",
        "target",
    )

    valid_groupings = {
        "none",
        "target",
        "parent",
        "operation",
    }

    if group_by not in valid_groupings:
        group_by = "target"

    change_groups = []

    if group_by == "none":

        change_groups.append(
            {
                "key": "all",
                "label": "Changes",
                "count": len(change_list),
                "changes": change_list,
            }
        )

    else:

        groups = defaultdict(list)

        for change in change_list:

            if group_by == "target":

                key = change.target_type

            elif group_by == "parent":

                if change.parent_type and change.parent_id:

                    key = (
                        change.parent_type,
                        str(change.parent_id),
                    )

                else:

                    key = (
                        "unparented",
                        "",
                    )

            elif group_by == "operation":

                key = change.operation

            else:

                key = change.target_type

            groups[key].append(change)

        for key, grouped_changes in groups.items():

            if group_by == "target":

                label = grouped_changes[0].target_type

            elif group_by == "parent":

                first_change = grouped_changes[0]

                if first_change.review_parent:

                    parent = first_change.review_parent

                    if parent["label"]:

                        label = parent["label"]

                    else:

                        label = parent["type"]

                else:

                    label = "Unparented changes"

            elif group_by == "operation":

                label = grouped_changes[0].get_operation_display()

            else:

                label = str(key)

            change_groups.append(
                {
                    "key": key,
                    "label": label,
                    "count": len(grouped_changes),
                    "changes": grouped_changes,
                }
            )

    # Keep groups predictable and easy to scan.
    change_groups.sort(
        key=lambda group: (
            group["label"].lower()
            if isinstance(group["label"], str)
            else str(group["label"]).lower()
        )
    )

    # -------------------------------------------------------------
    # Template context
    # -------------------------------------------------------------

    context.update(
        {
            "proposal": target_proposal,
            "submission_result": submission_result,
            "unlinked_validation_errors": unlinked_validation_errors,
            "changes": change_list,
            "change_groups": change_groups,
            "search": search,
            "review_filter": review_filter,
            "operation_filter": operation_filter,
            "target_filter": target_filter,
            "group_by": group_by,
            "sort": sort,
            "target_types": target_types,
            "reviewed_count": reviewed_count,
            "unreviewed_count": unreviewed_count,
            "total_count": total_count,
            "filtered_count": len(change_list),
        }
    )

    return render(
        request,
        "model/proposal.html",
        context,
    )
