"""
The public OnyxJar website.

Views only assemble page content and metadata. Sign-up and log-in belong to the
existing ``account`` app (``account:signup`` / ``account:login``); this app
links to them and never reimplements them.
"""

from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from .examples import EXAMPLES
from .forms import ContactForm
from .services.emails import send_contact_notification

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
            "page_title": f"OnyxJar — {TAGLINE}",
            "page_description": (
                "OnyxJar turns the connected parts of complex work into a structured, living model "
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
            "page_title": "Examples — OnyxJar",
            "page_description": (
                "Download a real OnyxJar example and explore it in your browser. "
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
            "page_title": "Privacy — OnyxJar",
            "page_description": "How OnyxJar handles your information.",
            "updated": LEGAL_UPDATED,
        },
    )


@require_safe
def terms(request):
    return render(
        request,
        "website/terms.html",
        {
            "page_title": "Terms — OnyxJar",
            "page_description": "The terms for using OnyxJar during beta.",
            "updated": LEGAL_UPDATED,
        },
    )


@require_http_methods(["GET", "HEAD", "POST"])
def contact(request):
    """
    A valid submission is emailed to WEBSITE_CONTACT_FORM_RECIPIENT via the
    existing Resend integration (redirect-after-POST keeps a reload from
    resubmitting). If the send fails, the form is re-shown with the visitor's
    input intact and a generic error, rather than a false success state.
    """

    send_error = False

    if request.method == "POST":
        form = ContactForm(request.POST)

        if form.is_valid():
            if send_contact_notification(**form.cleaned_data):
                return redirect(f"{reverse('website:contact')}?sent=1")
            send_error = True
    else:
        form = ContactForm()

    return render(
        request,
        "website/contact.html",
        {
            "nav_active": "contact",
            "form": form,
            "sent": request.method != "POST" and request.GET.get("sent") == "1",
            "send_error": send_error,
            "page_title": "Contact & feedback — OnyxJar",
            "page_description": "Questions, ideas or feedback about OnyxJar? Send us a note.",
        },
    )
