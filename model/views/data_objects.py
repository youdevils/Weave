from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import render

from model.models.object import Object
from model.models.proposal import Proposal
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context
from model.views.data_context import (
    build_object_attribute_definitions,
    build_proposed_only_objects,
    build_working_objects,
    discard_relationships_referencing_object,
    resolve_working_object_type,
)
from model.views.sidebar import with_updated_sidebar

PAGE_SIZE = 25

SORT_MAP = {
    "name": ["name"],
    "name_desc": ["-name"],
    "status": ["is_active", "name"],
    "status_desc": ["-is_active", "name"],
    "created": ["-created_at"],
    "created_desc": ["created_at"],
}


@login_required
def data_object_types(
    request,
    model_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    record_counts = {
        row["object_type_id"]: row["count"]
        for row in Object.objects.filter(
            model=model,
        )
        .values(
            "object_type_id",
        )
        .annotate(
            count=Count("id"),
        )
    }

    for object_type in context["object_types"]:
        object_type.record_count = record_counts.get(
            object_type.id,
            0,
        )

    return render(
        request,
        "model/data_object_types.html",
        context,
    )


@login_required
@with_updated_sidebar
def data_objects(
    request,
    model_id,
    object_type_id,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    object_type = resolve_working_object_type(context, object_type_id)

    if object_type is None:
        raise Http404("Object type not found.")

    # -------------------------------------------------------------
    # Discard a proposal-only (CREATE) record from the pending list
    # -------------------------------------------------------------

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_object_proposal"
    ):

        object_id = request.POST.get("object_id")

        if not object_id:
            return JsonResponse(
                {"success": False, "error": "Object ID is required."},
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
            target_type="Object",
            target_id=object_id,
        ).exists():
            return JsonResponse(
                {"success": False, "error": "No proposed changes were found for this record."},
                status=404,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="Object",
            target_id=object_id,
        )

        discard_relationships_referencing_object(proposal, object_id)

        return JsonResponse({"success": True})

    # -------------------------------------------------------------
    # Search
    # -------------------------------------------------------------

    search = request.GET.get(
        "q",
        "",
    ).strip()

    queryset = Object.objects.filter(
        model=model,
        object_type_id=object_type.id,
    )

    if search:

        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    # -------------------------------------------------------------
    # Sort
    # -------------------------------------------------------------

    sort = request.GET.get(
        "sort",
        "name",
    )

    queryset = queryset.order_by(
        *SORT_MAP.get(
            sort,
            SORT_MAP["name"],
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

    rows = build_working_objects(
        page.object_list,
        proposal,
    )

    pending_rows = build_proposed_only_objects(
        object_type,
        proposal,
    )

    if search:

        needle = search.lower()

        pending_rows = [
            row
            for row in pending_rows
            if needle in row.name.lower() or needle in row.description.lower()
        ]

    columns = build_object_attribute_definitions(
        object_type,
        proposal,
    )[:3]

    for row in rows:
        row.column_values = [row.attributes.get(column.key) for column in columns]

    for row in pending_rows:
        row.column_values = [row.attributes.get(column.key) for column in columns]

    context.update(
        {
            "object_type": object_type,
            "columns": columns,
            "rows": rows,
            "pending_rows": pending_rows,
            "page": page,
            "search": search,
            "sort": sort,
            "total_count": paginator.count,
        }
    )

    return render(
        request,
        "model/data_objects.html",
        context,
    )
