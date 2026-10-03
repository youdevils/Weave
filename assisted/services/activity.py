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
