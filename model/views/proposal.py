from collections import defaultdict
from model.services.proposal.review import ProposalReviewService
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context


@login_required
def proposal(request, model_id):

    # -------------------------------------------------------------
    # Common model context
    # -------------------------------------------------------------

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    proposal_source = request.GET.get(
        "proposal_source",
        "user",
    )

    if proposal_source == "ai":
        working_proposal = context["ai_working_proposal"]
        proposal_label = "AI suggestions"
    else:
        proposal_source = "user"
        working_proposal = context["my_working_proposal"]
        proposal_label = "My changes"

    # -------------------------------------------------------------
    # POST actions
    # -------------------------------------------------------------

    if request.method == "POST":

        if not working_proposal:
            return JsonResponse(
                {"error": "No working proposal exists."},
                status=400,
            )

        action = request.POST.get("action")

        # ---------------------------------------------------------
        # Discard a single change
        # ---------------------------------------------------------

        if action == "discard":

            change_id = request.POST.get("change_id")

            change = working_proposal.changes.filter(
                id=change_id,
            ).first()

            if not change:
                return JsonResponse(
                    {"error": "Change not found."},
                    status=404,
                )

            field_name = change.after.get("field") if change.after else None

            ProposalService.discard_change(
                proposal=working_proposal,
                target_type=change.target_type,
                target_id=change.target_id,
                field=field_name,
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

            change = working_proposal.changes.filter(
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

            change = working_proposal.changes.filter(
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

            working_proposal.changes.filter(
                review_status=(ProposalChange.ReviewStatus.UNREVIEWED),
            ).update(
                review_status=(ProposalChange.ReviewStatus.REVIEWED),
            )

            return JsonResponse({"success": True})

        # ---------------------------------------------------------
        # Bulk unreview
        # ---------------------------------------------------------

        if action == "unreview_all":

            working_proposal.changes.filter(
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
    # No working proposal / no changes
    # -------------------------------------------------------------

    if not working_proposal:

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

    # -------------------------------------------------------------
    # Base queryset
    # -------------------------------------------------------------

    changes = working_proposal.changes.all().order_by("created_at")

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

    proposal_changes = working_proposal.changes.all()

    total_count = proposal_changes.count()

    reviewed_count = proposal_changes.filter(
        review_status=(ProposalChange.ReviewStatus.REVIEWED)
    ).count()

    unreviewed_count = total_count - reviewed_count

    # -------------------------------------------------------------
    # Available filter values
    # -------------------------------------------------------------

    target_types = (
        working_proposal.changes.values_list(
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
            "proposal": working_proposal,
            "proposal_source": proposal_source,
            "proposal_label": proposal_label,
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
