"""
Checks a generated document really is self-contained, offline and read-only.

Run on every published document before the publication is committed (a failure
rolls the publication back) and again in tests over real output. It inspects the
*final string*, not the inputs, so it also catches mistakes made anywhere in
generation.

What it enforces:
  * no stylesheet, script, image, frame, form or link references anything by URL;
  * no ``@import`` and no ``url()`` other than ``data:`` in the CSS;
  * no legacy ``xlink:`` attribute (inline SVG must use unprefixed ``href``,
    which never depends on a namespace declaration or the document's base URI);
  * exactly one data block, and it parses as JSON;
  * a Content-Security-Policy that forbids every network connection;
  * none of the shipped *code* (scripts, not the data) contains a way to reach a
    server or edit a model: fetch/XHR/beacon/WebSocket, CSRF handling, OnyxJar
    routes, or proposal/appearance-form code.
"""

from __future__ import annotations

import json
import re

DATA_BLOCK_ID = "onyxjar-published-data"

# Ways code can talk to a server, and OnyxJar-specific edit paths, that must not ship.
FORBIDDEN_CODE = (
    "fetch(",
    "XMLHttpRequest",
    "sendBeacon",
    "WebSocket",
    "EventSource",
    "importScripts",
    "csrf",
    "X-CSRFToken",
    "/model/",
    "explore/graph",
    "appearance-form",
    "postAppearance",
    "proposal_",
    "/proposal",
    "ProposalChange",
)

_SCRIPT_BLOCK = re.compile(r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.DOTALL | re.IGNORECASE)
_EXTERNAL_TAGS = re.compile(r"<(link|img|iframe|frame|embed|object|source|video|audio|form|base)\b", re.IGNORECASE)
_SRC_ATTRIBUTE = re.compile(r"<script\b[^>]*\ssrc\s*=", re.IGNORECASE)
_XLINK_ATTRIBUTE = re.compile(r"\bxlink:", re.IGNORECASE)
_CSP_META = re.compile(
    r"<meta\s+http-equiv=\"Content-Security-Policy\"\s+content=\"[^\"]*default-src 'none'[^\"]*connect-src 'none'[^\"]*\"",
    re.IGNORECASE,
)
_URL_FUNCTION = re.compile(r"url\(\s*(?P<quote>[\"']?)(?P<target>[^)\"']*)", re.IGNORECASE)


class PortableValidationError(Exception):
    """The generated document is not safe to publish."""


def _fail(message: str):
    raise PortableValidationError(message)


def split_document(html: str) -> dict:
    """The document's parts: ``data`` (the JSON block), ``code`` (executable scripts), ``styles``."""
    data = []
    code = []
    for match in _SCRIPT_BLOCK.finditer(html):
        attrs = match.group("attrs")
        if f'id="{DATA_BLOCK_ID}"' in attrs:
            data.append(match.group("body"))
        elif "application/json" in attrs:
            _fail("Unexpected JSON block in the document.")
        else:
            code.append(match.group("body"))
    styles = [m.group("body") for m in _STYLE_BLOCK.finditer(html)]
    return {"data": data, "code": code, "styles": styles}


def validate_document(html: str) -> dict:
    """Raise ``PortableValidationError`` unless ``html`` is safe; returns the split parts on success."""
    parts = split_document(html)

    if len(parts["data"]) != 1:
        _fail(f"Expected exactly one data block, found {len(parts['data'])}.")
    try:
        json.loads(parts["data"][0])
    except ValueError:
        _fail("The embedded data block is not valid JSON.")

    # The document's markup with every script/style body emptied: tag-level checks
    # must not be fooled by (or trip over) text that only appears inside code.
    shell = _SCRIPT_BLOCK.sub(lambda m: f"<script{m.group('attrs')}></script>", html)
    shell = _STYLE_BLOCK.sub("<style></style>", shell)
    if _SRC_ATTRIBUTE.search(shell):
        _fail("A script is loaded from a URL.")
    if _EXTERNAL_TAGS.search(shell):
        _fail("The document references an external resource.")
    if _XLINK_ATTRIBUTE.search(shell):
        _fail("The document uses a legacy xlink: reference.")
    if not _CSP_META.search(shell):
        _fail("The Content-Security-Policy that blocks network access is missing.")

    for style in parts["styles"]:
        if re.search(r"@import", style, re.IGNORECASE):
            _fail("A stylesheet imports another stylesheet.")
        for match in _URL_FUNCTION.finditer(style):
            if not match.group("target").strip().lower().startswith("data:"):
                _fail("A stylesheet references a resource by URL.")

    for script in parts["code"]:
        for needle in FORBIDDEN_CODE:
            if needle in script:
                _fail(f"Shipped code contains {needle!r}.")

    return parts
