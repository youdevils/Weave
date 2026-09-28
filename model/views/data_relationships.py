from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import render

from model.models.proposal import Proposal
from model.models.relationship import Relationship
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context
from model.views.data_context import (
    build_proposed_only_relationships,
    build_relationship_attribute_definitions,
    build_working_relationships,
    resolve_working_relationship_type,
)
from model.views.sidebar import with_updated_sidebar

PAGE_SIZE = 25

SORT_MAP = {
    "subject": ["subject__name"],
    "subject_desc": ["-subject__name"],
    "object": ["object__name"],
    "object_desc": ["-object__name"],
    "status": ["is_active", "subject__name"],
    "status_desc": ["-is_active", "subject__name"],
    "created": ["-created_at"],
    "created_desc": ["created_at"],
}


@login_required
def data_relationship_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    record_counts = {
        row["relationship_type_id"]: row["count"]
        for row in Relationship.objects.filter(
            model=model,
        )
        .values(
            "relationship_type_id",
        )
        .annotate(
            count=Count("id"),
        )
    }

    for relationship_type in context["relationship_types"]:
        relationship_type.record_count = record_counts.get(
            relationship_type.id,
            0,
        )

    return render(
        request,
        "model/data_relationship_types.html",
        context,
    )


@login_required
@with_updated_sidebar
def data_relationships(
    request,
    model_id,
    relationship_type_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    relationship_type = resolve_working_relationship_type(context, relationship_type_id)

    if relationship_type is None:
        raise Http404("Relationship type not found.")

    # -------------------------------------------------------------
    # Discard a proposal-only (CREATE) relationship
    # -------------------------------------------------------------

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_relationship_proposal"
    ):

        relationship_id = request.POST.get("relationship_id")

        if not relationship_id:
            return JsonResponse(
                {"success": False, "error": "Relationship ID is required."},
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {"success": False, "error": "There is no working proposal to discard."},
                status=400,
            )

        if proposal.status not in (
            Proposal.Status.WORKING,
            Proposal.Status.FAILED,
        ):
            return JsonResponse(
                {"success": False, "error": "This proposal is locked and cannot be modified."},
                status=400,
            )

        if not proposal.changes.filter(
            target_type="Relationship",
            target_id=relationship_id,
        ).exists():
            return JsonResponse(
                {"success": False, "error": "No proposed changes were found for this relationship."},
                status=404,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="Relationship",
            target_id=relationship_id,
        )

        return JsonResponse({"success": True})

    # -------------------------------------------------------------
    # Search
    # -------------------------------------------------------------

    search = request.GET.get(
        "q",
        "",
    ).strip()

    # Active | All. Active means canonically active; a proposed change
    # never moves a record in or out of the Active view.
    show = "all" if request.GET.get("show") == "all" else "active"

    type_queryset = Relationship.objects.filter(
        model=model,
        relationship_type_id=relationship_type.id,
    )

    queryset = type_queryset.select_related(
        "subject",
        "object",
    )

    if search:

        queryset = queryset.filter(
            Q(subject__name__icontains=search) | Q(object__name__icontains=search)
        )

    search_queryset = queryset

    if show == "active":
        queryset = queryset.filter(is_active=True)

    # -------------------------------------------------------------
    # Sort
    # -------------------------------------------------------------

    sort = request.GET.get(
        "sort",
        "subject",
    )

    queryset = queryset.order_by(
        *SORT_MAP.get(
            sort,
            SORT_MAP["subject"],
        )
    )

    # -------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------

    paginator = Paginator(
        queryset,
        PAGE_SIZE,
    )

    page = paginator.get_page(
        request.GET.get("page"),
    )

    rows = build_working_relationships(
        page.object_list,
        proposal,
    )

    pending_rows = build_proposed_only_relationships(
        relationship_type,
        proposal,
    )

    has_records = bool(pending_rows) or type_queryset.exists()

    if search:

        needle = search.lower()

        pending_rows = [
            row
            for row in pending_rows
            if needle in row.subject_name.lower() or needle in row.object_name.lower()
        ]

    if show == "active":
        pending_rows = [row for row in pending_rows if row.is_active]

    has_inactive_matches = (
        show == "active"
        and not rows
        and not pending_rows
        and search_queryset.filter(is_active=False).exists()
    )

    columns = build_relationship_attribute_definitions(
        relationship_type,
        proposal,
    )[:3]

    for row in rows:
        row.column_values = [row.attributes.get(column.key) for column in columns]

    for row in pending_rows:
        row.column_values = [row.attributes.get(column.key) for column in columns]

    context.update(
        {
            "relationship_type": relationship_type,
            "columns": columns,
            "rows": rows,
            "pending_rows": pending_rows,
            "page": page,
            "search": search,
            "sort": sort,
            "show": show,
            "has_records": has_records,
            "has_inactive_matches": has_inactive_matches,
            "total_count": paginator.count,
        }
    )

    return render(
        request,
        "model/data_relationships.html",
        context,
    )
