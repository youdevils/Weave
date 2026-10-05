"""
Views only translate HTTP <-> the Assisted Work services/templates; the real
logic lives in assisted/services/.

Reconcile, Change and Assess are all "entry UI, stubbed submission" in this
build: none of them call into assisted.services.lifecycle, none of them
create an AssistedTask or AssistedTaskEvidence row. Only CREATE (started from
workspace/views/views.py::model_assisted_create_setup) is wired to real
execution today.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from account.services.entitlement import user_can_run_assisted
from assisted.access import get_assisted_workable_model
from assisted.models import AssistedTask
from assisted.services.activity import recent_tasks_for_model
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


@login_required
def reconcile_entry(request, model_id):
    model = get_assisted_workable_model(request, model_id)

    if request.method == "POST":
        intent = request.POST.get("intent", "").strip()

        if not intent:
            context = get_model_context(request, model.id)
            context["error"] = "Describe what this information should update before starting."
            return render(request, "assisted/reconcile.html", context)

        return _stub_submit(request, model, operation_label="Reconciliation", redirect_model_id=model.id)

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
