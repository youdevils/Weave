"""
Outbound account email (verification, password reset), sent via Resend.

Every call funnels through ``send_email``, which swallows and logs failures
so a Resend outage never turns into a broken signup/login/reset flow.
"""

import logging

import resend
from django.conf import settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
from django.urls import reverse

from account.tokens import email_verification_token

logger = logging.getLogger(__name__)


def send_email(*, to, subject, html):
    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send(
            {
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
    except Exception:
        logger.exception("Failed to send email to %s", to)


def send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    path = reverse("account:verify_email", kwargs={"uidb64": uid, "token": token})
    verify_url = request.build_absolute_uri(path)

    html = render_to_string(
        "account/email/verify_email.html",
        {"verify_url": verify_url, "user": user},
    )

    # send_email(to=user.email, subject="Verify your OnyxJar email", html=html)
    send_email(
        to="leon@youdevils.com", subject="Verify your OnyxJar email", html=html
    )
