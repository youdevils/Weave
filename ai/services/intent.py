"""
User intent: a single mandatory natural-language statement. Deliberately not
a multi-field model -- the user-facing input to an AI operation is
fundamentally one statement of intent.
"""

from dataclasses import dataclass

from django.conf import settings


class InvalidIntent(ValueError):
    """The supplied intent text is not usable."""


@dataclass(frozen=True)
class Intent:
    text: str


def validate_intent(text: str) -> Intent:
    cleaned = (text or "").strip()

    if not cleaned:
        raise InvalidIntent("Intent text is required.")

    if len(cleaned) > settings.AI_MAX_INTENT_CHARS:
        raise InvalidIntent(
            f"Intent text can be at most {settings.AI_MAX_INTENT_CHARS} characters."
        )

    return Intent(text=cleaned)
