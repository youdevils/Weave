from django.conf import settings
from django.template.loader import render_to_string

from account.services.emails import send_email


def send_contact_notification(*, name, email, message):
    html = render_to_string(
        "website/email/contact_notification.html",
        {"name": name, "email": email, "message": message},
    )
    return send_email(
        to=settings.WEBSITE_CONTACT_FORM_RECIPIENT,
        subject=f"OnyxJar contact form — {name}",
        html=html,
        reply_to=email,
    )
