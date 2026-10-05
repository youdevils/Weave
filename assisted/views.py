"""
Views only translate HTTP <-> the Assisted Work services/templates; the real
logic lives in assisted/services/.

Change and Assess remain "entry UI, stubbed submission": neither calls into
assisted.services.lifecycle, neither creates an AssistedTask or
AssistedTaskEvidence row. CREATE (started from
workspace/views/views.py::model_assisted_create_setup) and RECONCILE
(reconcile_entry below) are wired to real execution.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_GET

from account.services.entitlement import user_can_run_assisted
from ai.services.intent import InvalidIntent

from assisted.access import get_assisted_workable_model
from assisted.models import AssistedTask
from assisted.services.activity import recent_tasks_for_model
from assisted.services.evidence import AssistedEvidenceInvalid
from assisted.services.lifecycle import (
    AssistedEntitlementDenied,
    AssistedTaskActive,
    BootstrapModelGone,
    EmptyModelNotReconcilable,
    EvidenceRequired,
    start_assisted_reconcile,
)
from assisted.uploads import LimitedUploadHandler
from model.views.common_context import get_model_context

NOT_AVAILABLE_MESSAGE = "{operation} isn't available yet in this build."


@login_required
@require_GET
def landing(request, model_id):
    context = get_model_context(request, model_id)
    context["recent_tasks"] = recent_tasks_for_model(context["model"])
    # UI-only: tells the template whether to offer the Reconcile/Change/Assess
    # entry cards at all, so a user on a plan without Assisted Work never
    # reaches a 403 through the normal landing-page flow. The real gate stays
    # assisted.access.get_assisted_workable_model, unchanged, on each entry view.
    context["can_use_assisted"] = user_can_run_assisted(request.user)

    return render(request, "assisted/landing.html", context)


def _stub_submit(request, model, *, operation_label, redirect_model_id):
    messages.info(request, NOT_AVAILABLE_MESSAGE.format(operation=operation_label))
    return redirect("assisted:landing", model_id=redirect_model_id)


@csrf_exempt
def reconcile_entry(request, model_id):
    """
    The handler that enforces the per-file size limit has to be installed
    before anything reads the request body, and Django's CSRF middleware
    would do exactly that, so this thin outer view exempts itself, installs
    the handler and hands over to a csrf-protected view -- the same split
    workspace.views.views.model_assisted_create_setup (and, before it,
    ingestion.views.import_upload) already uses.
    """

    handler = LimitedUploadHandler(request, max_bytes=settings.ASSISTED_MAX_EVIDENCE_FILE_BYTES)
    request.upload_handlers = [handler]

    return _reconcile_entry(request, model_id, handler=handler)


@csrf_protect
@login_required
def _reconcile_entry(request, model_id, handler):
    model = get_assisted_workable_model(request, model_id)

    if request.method == "POST":
        intent = request.POST.get("intent", "").strip()

        if not intent:
            context = get_model_context(request, model.id)
            context["error"] = "Describe what this information should update before starting."
            return render(request, "assisted/reconcile.html", context)

        files = request.FILES.getlist("evidence")

        if handler.too_large:
            messages.error(request, "One of the attached files is too large.")
            return render(request, "assisted/reconcile.html", get_model_context(request, model.id))

        if len(files) > settings.ASSISTED_MAX_EVIDENCE_FILES:
            messages.error(request, f"Attach at most {settings.ASSISTED_MAX_EVIDENCE_FILES} files.")
            return render(request, "assisted/reconcile.html", get_model_context(request, model.id))

        try:
            task = start_assisted_reconcile(
                workspace=model.workspace,
                model=model,
                user=request.user,
                intent_text=intent,
                files=files,
            )
        except (AssistedTaskActive, AssistedEntitlementDenied, EmptyModelNotReconcilable, BootstrapModelGone) as exc:
            messages.error(request, str(exc))
            return redirect("assisted:landing", model_id=model.id)
        except (EvidenceRequired, InvalidIntent, AssistedEvidenceInvalid) as exc:
            context = get_model_context(request, model.id)
            context["error"] = str(exc)
            return render(request, "assisted/reconcile.html", context)

        messages.success(request, "Reconciliation started. We'll let you know when it's ready for review.")
        # Not assisted:task_detail -- that view 404s while a task is still
        # ACTIVE (QUEUED/RUNNING/READY_FOR_REVIEW), by design (an in-flight
        # job's internals are never inspectable, see assisted.views.task_detail).
        # The landing page's "Current work" card is the right place to land
        # right after submission, same as Create's redirect to workspace:index.
        return redirect("assisted:landing", model_id=model.id)

    context = get_model_context(request, model.id)
    return render(request, "assisted/reconcile.html", context)


@login_required
def change_entry(request, model_id):
    model = get_assisted_workable_model(request, model_id)

    if request.method == "POST":
        intent = request.POST.get("intent", "").strip()

        if not intent:
            context = get_model_context(request, model.id)
            context.update(_change_copy())
            context["error"] = "Describe the change you want before starting."
            return render(request, "assisted/stub_entry.html", context)

        return _stub_submit(request, model, operation_label="Change", redirect_model_id=model.id)

    context = get_model_context(request, model.id)
    context.update(_change_copy())
    return render(request, "assisted/stub_entry.html", context)


@login_required
def assess_entry(request, model_id):
    model = get_assisted_workable_model(request, model_id)

    if request.method == "POST":
        intent = request.POST.get("intent", "").strip()

        if not intent:
            context = get_model_context(request, model.id)
            context.update(_assess_copy())
            context["error"] = "Describe what you'd like assessed before starting."
            return render(request, "assisted/stub_entry.html", context)

        return _stub_submit(request, model, operation_label="Assessment", redirect_model_id=model.id)

    context = get_model_context(request, model.id)
    context.update(_assess_copy())
    return render(request, "assisted/stub_entry.html", context)


def _change_copy():
    return {
        "page_title": "Change",
        "page_description": "Propose a structured change to this model.",
        "intent_label": "What change do you want?",
        "intent_placeholder": "Describe the change you want OnyxJar to propose.",
        "submit_label": "Start change",
    }


def _assess_copy():
    return {
        "page_title": "Assess",
        "page_description": "Assess this model against a question or area of concern.",
        "intent_label": "What would you like assessed?",
        "intent_placeholder": "What would you like OnyxJar to assess?",
        "submit_label": "Start assessment",
    }


@login_required
@require_GET
def task_detail(request, model_id, task_id):
    context = get_model_context(request, model_id)

    task = get_object_or_404(AssistedTask, id=task_id, model_id=model_id)

    if task.status in AssistedTask.ACTIVE_STATUSES:
        # Mirrors the UX rule, not just the lack of a link to this page: an
        # active job's internals are never inspectable, even by a guessed URL.
        raise Http404

    context["task"] = task
    context["change_count"] = task.proposal.changes.count() if task.proposal_id else None

    return render(request, "assisted/task_detail.html", context)
