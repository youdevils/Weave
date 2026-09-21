from django.conf import settings


def site(request):
    """Values the public footer and legal pages need, on every page that uses the public base."""

    return {
        "legal_entity": settings.WEBSITE_LEGAL_ENTITY,
        "contact_email": settings.WEBSITE_CONTACT_EMAIL,
    }
