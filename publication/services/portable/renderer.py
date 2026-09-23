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
# open a connection, so the file cannot call back to Weave (or anywhere else)
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
            "canvas_background": bundle["presentation"]["canvasBackground"],
            "csp": _CSP_TEMPLATE.format(scripts=scripts),
            "css": assets.css.replace("</style", "<\/style"),
            "vis_script": vis_script,
            "app_script": app_script,
            "data_block": json_script(bundle, DATA_BLOCK_ID),
            "show_platform_branding": show_platform_branding,
        },
    )
