from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from model.models.model import Model
from model.services.model_template.loader import (
    get_template,
    instantiate_template,
)


@login_required
def index(request):
    memberships = request.user.workspace_memberships.select_related(
        "workspace",
    ).prefetch_related(
        "workspace__models",
    )

    return render(
        request,
        "workspace/dashboard.html",
        {
            "memberships": memberships,
        },
    )


@login_required
def create_model(request):
    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:
        return redirect("workspace:index")

    workspace = membership.workspace

    if request.method == "POST":
        model = Model.objects.create(
            workspace=workspace,
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip(),
            purpose=request.POST.get("purpose", "").strip(),
            scope=request.POST.get("scope", "").strip(),
            exclusions=request.POST.get("exclusions", "").strip(),
        )

        return redirect(
            "workspace:model_starting_point",
            model_id=model.id,
        )

    return render(
        request,
        "workspace/create_model.html",
        {
            "workspace": workspace,
        },
    )


@login_required
def model_starting_point(request, model_id):
    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:
        return redirect("workspace:index")

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    starting_points = [
        {
            "key": "business_process",
            "name": "Business Process",
            "description": (
                "Model processes, systems and teams to understand "
                "how work flows through the organisation."
            ),
            "icon": "bi-diagram-3",
            "available": True,
        },
        {
            "key": "application_landscape",
            "name": "Application Landscape",
            "description": (
                "Map applications, capabilities and technology "
                "across your organisation."
            ),
            "icon": "bi-grid-3x3-gap",
            "available": False,
        },
    ]

    return render(
        request,
        "workspace/model_starting_point.html",
        {
            "model": model,
            "starting_points": starting_points,
        },
    )


@login_required
def model_template_review(request, model_id, template_key):
    membership = request.user.workspace_memberships.select_related(
        "workspace",
    ).first()

    if not membership:
        return redirect("workspace:index")

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    try:
        template = get_template(template_key)
    except ValueError:
        return redirect(
            "workspace:model_starting_point",
            model_id=model.id,
        )

    if request.method == "POST":
        instantiate_template(
            model=model,
            template_key=template_key,
        )

        return redirect(
            "/",
        )

    return render(
        request,
        "workspace/model_template_review.html",
        {
            "model": model,
            "template": template,
        },
    )
