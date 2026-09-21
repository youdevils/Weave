"""
Public account pages.

Log-in and sign-up are **stubs** for now: they render real pages at their real
URLs (``/login/``, ``/signup/``) so that links and ``settings.LOGIN_URL`` are
already in place, but they never create a user, authenticate anyone, or touch
account or session state. Only GET/HEAD is accepted. The real flow (with email
verification) replaces these view bodies later; nothing that links here changes.
"""

from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def login(request):
    return render(
        request,
        "account/login.html",
        {
            "page_title": "Log in — FacetFold",
            "page_description": "Log in to FacetFold.",
        },
    )


@require_safe
def signup(request):
    return render(
        request,
        "account/signup.html",
        {
            "page_title": "Try FacetFold free",
            "page_description": "Create your FacetFold account. Free during beta.",
        },
    )
