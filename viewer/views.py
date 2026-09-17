from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from viewer.services.sample_payload import build_sample_payload


def harness(request: HttpRequest) -> HttpResponse:
    """Minimal dev/test harness for exercising the viewer against a static sample payload.

    Intentionally unavailable outside DEBUG — this is not a production page.
    """

    if not settings.DEBUG:
        raise Http404()

    payload = build_sample_payload()
    return render(request, "viewer/harness.html", {"payload": payload.to_dict()})
