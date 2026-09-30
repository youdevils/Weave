"""
Renders a bundle into the single self-contained HTML document.

The document is built entirely in memory: nothing is written to disk, cached or
logged, and the caller keeps only the returned string long enough to send it.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime

from django.template.loader import render_to_string
from django.utils.html import json_script

from .assets import load_assets
from .validator import DATA_BLOCK_ID

# What the document is allowed to do. Scripts are pinned by hash; nothing may
# open a connection, so the file cannot call back to OnyxJar (or anywhere else)
# even if a bug or a hostile value tried to.
_CSP_TEMPLATE = (
    "default-src 'none'; script-src {scripts}; style-src 'unsafe-inline'; img-src data:; font-src data:; "
    "connect-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'none'; object-src 'none'"
)


def _escape_script(code: str) -> str:
    """Make script text safe to place between <script> tags without changing what it does."""
    code = code.replace("\r\n", "\n").replace("\r", "\n")  # browsers normalise newlines before hashing
    return re.sub(r"<!--", r"<\!--", re.sub(r"</(script)", r"<\/\1", code, flags=re.IGNORECASE))


def _sha256_source(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def _ink_for(colour: str) -> str:
    """Black or white, whichever reads better on ``colour`` (a #RRGGBB hex)."""
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255
    return "#212529" if luminance > 0.6 else "#ffffff"


def _relative_luminance(red: int, green: int, blue: int) -> float:
    """WCAG relative luminance, sRGB channels gamma-expanded first."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in (red, green, blue))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(l1: float, l2: float) -> float:
    lighter, darker = (l1, l2) if l1 >= l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


def _interactive_for(colour: str, *, minimum_ratio: float = 4.5) -> str:
    """``colour`` darkened just enough to read reliably as link/reference text on a white panel.

    Model owners can pick any theme colour, including pale ones with no useful contrast
    against a white background. Rather than falling back to a fixed brand blue (which would
    clash with the model's own colour), this keeps the same hue and darkens it in RGB space
    until it clears WCAG AA (4.5:1) against white, or bottoms out near black.
    """
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    white_luminance = 1.0
    ratio = _contrast_ratio(white_luminance, _relative_luminance(red, green, blue))
    if ratio >= minimum_ratio:
        return colour

    r, g, b = float(red), float(green), float(blue)
    for _ in range(24):
        r, g, b = r * 0.92, g * 0.92, b * 0.92
        ratio = _contrast_ratio(white_luminance, _relative_luminance(r, g, b))
        if ratio >= minimum_ratio:
            break
    return f"#{round(r):02x}{round(g):02x}{round(b):02x}"


def _display_date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d %b %Y").lstrip("0")


def render_document(bundle: dict, *, hash_scripts: bool = True, show_platform_branding: bool = True) -> str:
    """The published document for ``bundle`` (which must carry its publication identity).

    ``show_platform_branding`` defaults to always shown; it exists as the one hook point
    for a future commercial entitlement to hide the OnyxJar mark, without this task
    implementing any actual plan/entitlement gating logic.
    """
    assets = load_assets()
    vis_script = _escape_script(assets.vis_script)
    app_script = _escape_script(assets.app_script)

    publication = bundle["publication"]
    scripts = " ".join(_sha256_source(code) for code in (vis_script, app_script)) if hash_scripts else "'unsafe-inline'"

    return render_to_string(
        "publication/portable/document.html",
        {
            "title": publication["title"],
            "description": publication.get("description", ""),
            "revision": publication["revision"],
            "published_iso": publication["publishedAt"],
            "published_display": _display_date(publication["publishedAt"]),
            "theme_colour": bundle["presentation"]["themeColour"],
            "theme_ink": _ink_for(bundle["presentation"]["themeColour"]),
            "theme_interactive": _interactive_for(bundle["presentation"]["themeColour"]),
            "canvas_background": bundle["presentation"]["canvasBackground"],
            "csp": _CSP_TEMPLATE.format(scripts=scripts),
            "css": assets.css.replace("</style", "<\/style"),
            "vis_script": vis_script,
            "app_script": app_script,
            "data_block": json_script(bundle, DATA_BLOCK_ID),
            "show_platform_branding": show_platform_branding,
            "brand_mark": assets.brand_mark,
        },
    )
