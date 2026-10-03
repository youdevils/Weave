"""
Status badge for an AssistedTask, shared between the workspace dashboard's
Assisted Activity sidebar and the active-task indicator on each model card
-- one status-to-label/class mapping, used in both places.
"""

from django import template
from django.utils.html import format_html

from assisted.models import AssistedTask

register = template.Library()

_BADGES = {
    AssistedTask.Status.QUEUED: ("In progress", "onyxjar-status-pill-progress"),
    AssistedTask.Status.RUNNING: ("In progress", "onyxjar-status-pill-progress"),
    AssistedTask.Status.READY_FOR_REVIEW: ("Ready for review", "onyxjar-status-pill-review"),
    AssistedTask.Status.COMPLETED: ("Completed", "onyxjar-status-pill-completed"),
    AssistedTask.Status.FAILED: ("Failed", "onyxjar-status-pill-failed"),
}


@register.simple_tag
def assisted_status_badge(task):
    if task is None:
        return ""

    label, modifier = _BADGES.get(task.status, (task.get_status_display(), ""))

    return format_html(
        '<span class="onyxjar-status-pill {}">{}</span>',
        modifier,
        label,
    )
