from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


def notify_unverified_email(request):
    html = render_to_string("account/_verify_email_notice.html", request=request)
    messages.info(request, mark_safe(html))
