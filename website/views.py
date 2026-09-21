"""
The public FacetFold website.

Views only assemble page content and metadata. Sign-up and log-in belong to the
existing ``account`` app (``account:signup`` / ``account:login``); this app
links to them and never reimplements them.
"""

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from .examples import EXAMPLES
from .forms import ContactForm

TAGLINE = "Build a living model of complex work."

# When the legal pages were last revised.
LEGAL_UPDATED = "21 September 2026"


@require_safe
def home(request):
    return render(
        request,
        "website/home.html",
        {
            "hero_header": True,
            "page_title": f"FacetFold — {TAGLINE}",
            "page_description": (
                "FacetFold turns the connected parts of complex work into a structured, living model "
                "you can explore, change with confidence, and share. Free during beta."
            ),
        },
    )


@require_safe
def examples(request):
    return render(
        request,
        "website/examples.html",
        {
            "nav_active": "examples",
            "examples": EXAMPLES,
            "page_title": "Examples — FacetFold",
            "page_description": (
                "Download a real FacetFold example and explore it in your browser. "
                "Each one is a self-contained, interactive model."
            ),
        },
    )


@require_safe
def privacy(request):
    return render(
        request,
        "website/privacy.html",
        {
            "page_title": "Privacy — FacetFold",
            "page_description": "How FacetFold handles your information.",
            "updated": LEGAL_UPDATED,
        },
    )


@require_safe
def terms(request):
    return render(
        request,
        "website/terms.html",
        {
            "page_title": "Terms — FacetFold",
            "page_description": "The terms for using FacetFold during beta.",
            "updated": LEGAL_UPDATED,
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contact(request):
    """
    A stub: a valid submission shows a success state and nothing else happens.
    The submitted content and personal details are deliberately never logged,
    stored or sent anywhere (redirect-after-POST keeps a reload from resubmitting).
    """

    if request.method == "POST":
        form = ContactForm(request.POST)

        if form.is_valid():
            return redirect(f"{reverse('website:contact')}?sent=1")
    else:
        form = ContactForm()

    return render(
        request,
        "website/contact.html",
        {
            "nav_active": "contact",
            "form": form,
            "sent": request.method != "POST" and request.GET.get("sent") == "1",
            "page_title": "Contact & feedback — FacetFold",
            "page_description": "Questions, ideas or feedback about FacetFold? Send us a note.",
        },
    )
