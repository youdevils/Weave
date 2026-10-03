import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST

from account.notifications import notify_unverified_email
from account.services.entitlement import user_can_run_assisted
from ai.services.intent import InvalidIntent
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

from assisted.models import AssistedTask
from assisted.services.activity import active_tasks_by_model_id, recent_tasks_for_workspace
from assisted.services.evidence import AssistedEvidenceInvalid
from assisted.services.lifecycle import (
    AssistedEntitlementDenied,
    AssistedTaskActive,
    BootstrapModelGone,
    start_assisted_create,
)
from assisted.uploads import LimitedUploadHandler

logger = logging.getLogger(__name__)

ASSISTED_CREATE_ROLES = (WorkspaceMember.Role.OWNER, WorkspaceMember.Role.EDITOR)
ASSISTED_ACTIVITY_WINDOW_DAYS = 30


@login_required
def index(request):
    if not request.user.email_verified:
        notify_unverified_email(request)

    memberships = request.user.workspace_memberships.select_related(
        "workspace",
    ).prefetch_related(
        "workspace__models",
    )

    since = timezone.now() - timedelta(days=ASSISTED_ACTIVITY_WINDOW_DAYS)
    assisted_activity = []

    for membership in memberships:
        workspace_tasks = list(recent_tasks_for_workspace(membership.workspace, since=since))
        assisted_activity.extend(workspace_tasks)

        active_by_model = active_tasks_by_model_id(workspace_tasks)
        for model in membership.workspace.models.all():
            model.active_assisted_task = active_by_model.get(model.id)

    assisted_activity.sort(key=lambda task: task.created_at, reverse=True)

    return render(
        request,
        "workspace/dashboard.html",
        {
            "memberships": memberships,
            "assisted_activity": assisted_activity,
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
        "business_operations": "bi-diagram-3",
        "process_context": "bi-arrow-repeat",
        "application_management": "bi-window-stack",
        "project_programme_delivery": "bi-kanban",
        "organisation_and_capability": "bi-building",
        "service_customer_journey": "bi-signpost-split",
        "research_and_evidence": "bi-search",
        "governance_and_risk": "bi-shield-check",
        "product_domain_model": "bi-boxes",
        "competition_tournament": "bi-trophy",
    }

    # Presentational only (shorter card copy) -- the canonical template
    # "description" is the longer, fuller text used elsewhere; these are
    # tightened summaries so the template grid stays compact and scannable.
    template_card_descriptions = {
        "business_operations": "Model how an organisation operates across capabilities, processes, people, systems, risks and outcomes.",
        "process_context": "Model a process in its real operating context — triggers, actors, systems, policies and the outcomes it serves.",
        "application_management": "Model your application estate and how it connects to capabilities, processes, data, vendors and risk.",
        "project_programme_delivery": "Model delivery work — programmes, projects, deliverables, risks and the outcomes they're meant to achieve.",
        "organisation_and_capability": "Model organisational structure and capabilities, and how ownership connects to services, processes and risk.",
        "service_customer_journey": "Model a service from the customer's perspective — needs, journey stages, touchpoints and outcomes.",
        "research_and_evidence": "Model research from question to evidence to findings, with assumptions and confidence made explicit.",
        "governance_and_risk": "Model governance, policies and controls alongside the risks, issues and decisions they manage.",
        "product_domain_model": "Model a product or problem domain — its core concepts, rules, events and surrounding actors and systems.",
        "competition_tournament": "Model a competition or tournament — entries, fixtures, officials, rules, results and rankings.",
    }

    starting_points = [
        {
            "key": key,
            "name": template["name"],
            "description": template_card_descriptions.get(key, template["description"]),
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
            "can_use_assisted": user_can_run_assisted(request.user),
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


@csrf_exempt
def model_assisted_create_setup(request, model_id):
    """
    The handler that enforces the per-file size limit has to be installed
    before anything reads the request body, and Django's CSRF middleware
    would do exactly that, so this thin outer view exempts itself, installs
    the handler and hands over to a csrf-protected view -- the same split
    ingestion.views.import_upload uses.
    """

    handler = LimitedUploadHandler(request, max_bytes=settings.ASSISTED_MAX_EVIDENCE_FILE_BYTES)
    request.upload_handlers = [handler]

    return _model_assisted_create_setup(request, model_id, handler=handler)


@csrf_protect
@login_required
def _model_assisted_create_setup(request, model_id, handler):
    # 404 for anyone outside the model's workspace; being a member is not
    # enough to start an assisted operation, that takes owner or editor,
    # mirroring ingestion.access's IMPORT_ROLES gate.
    membership = get_object_or_404(
        WorkspaceMember.objects.select_related("workspace"),
        user=request.user,
        workspace__models__id=model_id,
    )

    if membership.role not in ASSISTED_CREATE_ROLES:
        raise PermissionDenied("Only workspace owners and editors can use assisted creation.")

    model = get_object_or_404(
        Model,
        id=model_id,
        workspace=membership.workspace,
    )

    if request.method == "POST":
        files = request.FILES.getlist("evidence")

        if handler.too_large:
            messages.error(request, "One of the attached files is too large.")
            return render(request, "workspace/model_assisted_create_setup.html", {"model": model})

        if len(files) > settings.ASSISTED_MAX_EVIDENCE_FILES:
            messages.error(
                request,
                f"Attach at most {settings.ASSISTED_MAX_EVIDENCE_FILES} files.",
            )
            return render(request, "workspace/model_assisted_create_setup.html", {"model": model})

        try:
            start_assisted_create(
                workspace=membership.workspace,
                model=model,
                user=request.user,
                intent_text=request.POST.get("intent", ""),
                files=files,
            )
        except AssistedTaskActive as exc:
            messages.error(request, str(exc))
            return redirect("workspace:model_starting_point", model_id=model.id)
        except AssistedEntitlementDenied as exc:
            messages.error(request, str(exc))
            return redirect("workspace:model_starting_point", model_id=model.id)
        except BootstrapModelGone as exc:
            messages.error(request, str(exc))
            return redirect("workspace:index")
        except (InvalidIntent, AssistedEvidenceInvalid) as exc:
            messages.error(request, str(exc))
            return render(request, "workspace/model_assisted_create_setup.html", {"model": model})

        messages.success(
            request,
            "Assisted creation started. We’ll let you know when it’s ready for review.",
        )
        return redirect("workspace:index")

    return render(
        request,
        "workspace/model_assisted_create_setup.html",
        {
            "model": model,
            "max_intent_chars": settings.AI_MAX_INTENT_CHARS,
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
        with transaction.atomic():
            locked = Model.objects.select_for_update().get(pk=model.pk)

            if AssistedTask.objects.filter(model=locked, status__in=AssistedTask.ACTIVE_STATUSES).exists():
                raise AssistedTaskActive(
                    "This model has an assisted operation in progress and cannot be "
                    "deleted until it finishes."
                )

            delete_model(locked)
    except (ModelDeletionBlocked, AssistedTaskActive) as blocked:
        messages.error(request, str(blocked))
    else:
        messages.success(request, f"Model “{name}” was permanently deleted.")

    return redirect("workspace:index")
