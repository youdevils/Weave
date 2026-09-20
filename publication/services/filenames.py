"""
Suggested download filenames.

The name is only a *suggestion* sent in ``Content-Disposition``; the browser
decides where the file is saved. Everything here exists so a hostile or careless
value can never carry a path, control characters or a name Windows refuses.
"""

from __future__ import annotations

import re
import unicodedata

from django.utils.text import slugify

MAX_LENGTH = 120
EXTENSION = ".html"

_ILLEGAL = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_EXTENSIONS = re.compile(r"(\.html?)+$", re.IGNORECASE)
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}


def default_filename(model_name: str, revision: int) -> str:
    """``<model-slug>-r<revision>.html``."""
    suffix = f"-r{revision}{EXTENSION}"
    slug = slugify(model_name or "")[: MAX_LENGTH - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"


def normalise_filename(raw, fallback: str) -> str:
    """
    A safe ``.html`` filename from user input, or ``fallback`` when nothing usable
    remains. Path separators, control characters and characters Windows forbids
    are removed; reserved device names are refused; a single ``.html`` extension
    is forced; the result is at most ``MAX_LENGTH`` characters.
    """
    name = unicodedata.normalize("NFC", str(raw or ""))
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    stem = _EXTENSIONS.sub("", name).strip(" .")
    stem = stem[: MAX_LENGTH - len(EXTENSION)].rstrip(" .")

    if not stem or stem.split(".")[0].lower() in _RESERVED:
        return fallback
    return f"{stem}{EXTENSION}"
