"""
Keeps the model sidebar's proposal state in sync with proposal-editing
AJAX calls.

Field/attribute edits, lifecycle toggles, and proposal-discard actions
across the model views are all handled via in-place AJAX POSTs that
never reload the page, so the server-rendered sidebar fragment (proposal
list, change counts, active-section state) would otherwise go stale
until the next full navigation. `with_updated_sidebar` re-renders the
sidebar from the same `get_model_context` source of truth used for a
full page load and attaches it to any successful JSON POST response, so
the client can swap it in without maintaining any separate proposal
state of its own.
"""

import json
from functools import wraps

from django.http import JsonResponse
from django.template.loader import render_to_string

from model.views.common_context import get_model_context


def with_updated_sidebar(view_func):
    @wraps(view_func)
    def wrapper(request, model_id, *args, **kwargs):

        response = view_func(
            request,
            model_id,
            *args,
            **kwargs,
        )

        if request.method != "POST":
            return response

        content_type = response.get(
            "Content-Type",
            "",
        )

        if "application/json" not in content_type:
            return response

        try:
            payload = json.loads(response.content)
        except ValueError:
            return response

        if not isinstance(payload, dict) or not payload.get("success"):
            return response

        context = get_model_context(
            request,
            model_id,
        )

        payload["sidebar_html"] = render_to_string(
            "model/_sidebar.html",
            context,
            request=request,
        )

        return JsonResponse(
            payload,
            status=response.status_code,
        )

    return wrapper
