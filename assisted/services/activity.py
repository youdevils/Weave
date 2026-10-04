"""
Read-only queries for surfacing AssistedTask history in the workspace
dashboard: the "Assisted Activity" sidebar and the active-task indicator on
each model card. No new activity subsystem -- AssistedTask is the only
source of truth, this just shapes two read queries against it.
"""

from __future__ import annotations

from django.db.models import Count, Q

from assisted.models import AssistedTask


def recent_tasks_for_workspace(workspace, since):
    """
    Every AssistedTask for `workspace` created on or after `since`, plus any
    task that is still active regardless of age (so an in-flight task never
    drops out of view just because it's been running a while). Each task is
    annotated with `change_count`, the number of ProposalChanges on its
    linked Proposal (0 if it has none) -- computed here, in the one query,
    so rendering the list never issues a per-task `task.proposal.changes.
    count()` call.
    """

    return (
        workspace.assisted_tasks.filter(
            Q(created_at__gte=since) | Q(status__in=AssistedTask.ACTIVE_STATUSES)
        )
        .select_related("model", "proposal")
        .annotate(change_count=Count("proposal__changes"))
        .order_by("-created_at")
    )


def active_tasks_by_model_id(tasks):
    """
    Given an already-fetched iterable of AssistedTasks (e.g. the result of
    recent_tasks_for_workspace), return {model_id: task} for the active
    ones. Used to attach an "active Assisted task" indicator to each model
    card without a second query.
    """

    return {
        task.model_id: task
        for task in tasks
        if task.status in AssistedTask.ACTIVE_STATUSES and task.model_id is not None
    }


def active_task_for_model(model):
    """
    The one active AssistedTask for `model`, or None. A trivial existence
    lookup, not a new invariant -- relies on the same
    unique_active_assisted_task_per_model DB constraint AssistedTask already
    enforces. Used to drive the model sidebar's "Assisted Work" status line
    and the Assisted Work landing page's "Current work" card.
    """

    return model.assisted_tasks.filter(status__in=AssistedTask.ACTIVE_STATUSES).first()


def recent_tasks_for_model(model, exclude_active=True, limit=10):
    """
    Reverse-chronological AssistedTask history for one model's own Assisted
    Work page -- not a new activity subsystem, the same read-only shape as
    recent_tasks_for_workspace above, just scoped to one model instead of a
    workspace. Active tasks are excluded by default since they're already
    shown separately as "Current work"; the sidebar/landing page should never
    show the same task in both places.
    """

    qs = (
        model.assisted_tasks.select_related("proposal")
        .annotate(change_count=Count("proposal__changes"))
        .order_by("-created_at")
    )

    if exclude_active:
        qs = qs.exclude(status__in=AssistedTask.ACTIVE_STATUSES)

    return qs[:limit]
