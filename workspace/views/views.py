import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from account.notifications import notify_unverified_email
from model.models.model import Model
from model.services.model_deletion import ModelDeletionBlocked, delete_model
from model.services.model_template.builder import TemplateDefinitionError
from model.services.model_template.loader import (
    TEMPLATES,
    TemplateInstantiationFailure,
    get_template,
    instantiate_template_via_proposal,
    template_has_data,
)
from workspace.models import WorkspaceMember

logger = logging.getLogger(__name__)


@login_required
def index(request):
    if not request.user.email_verified:
        notify_unverified_email(request)

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

    # Presentational only (icon glyph per card) -- not template metadata.
    template_icons = {
        "business_process": "bi-diagram-3",
        "delivery_project": "bi-shop",
    }

    starting_points = [
        {
            "key": key,
            "name": template["name"],
            "description": template["description"],
            "icon": template_icons.get(key, "bi-diagram-3"),
            "has_data": template_has_data(template),
            "available": True,
        }
        for key, template in TEMPLATES.items()
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
        try:
            instantiate_template_via_proposal(
                model=model,
                template_key=template_key,
                user=request.user,
            )
        except (TemplateInstantiationFailure, TemplateDefinitionError) as failure:
            logger.warning(
                "Template instantiation failed for model %s, template %s: %s",
                model.id,
                template_key,
                failure,
            )

            try:
                delete_model(model)
            except ModelDeletionBlocked:
                logger.error(
                    "Could not roll back model %s after failed template "
                    "instantiation (template %s).",
                    model.id,
                    template_key,
                )

            messages.error(
                request,
                "The model could not be created from this template because "
                "the template failed validation. No model was created.",
            )
            return redirect("workspace:index")

        return redirect("workspace:index")

    return render(
        request,
        "workspace/model_template_review.html",
        {
            "model": model,
            "template": template,
        },
    )


@login_required
@require_POST
def delete_model_view(request, model_id):
    # 404 for anyone outside the model's workspace, as elsewhere; being a
    # member is not enough to destroy it, that takes the owner role.
    membership = get_object_or_404(
        WorkspaceMember.objects.select_related("workspace"),
        user=request.user,
        workspace__models__id=model_id,
    )

    if membership.role != WorkspaceMember.Role.OWNER:
        raise PermissionDenied

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    name = model.name

    try:
        delete_model(model)
    except ModelDeletionBlocked as blocked:
        messages.error(request, str(blocked))
    else:
        messages.success(request, f"Model “{name}” was permanently deleted.")

    return redirect("workspace:index")
