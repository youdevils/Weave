"""
The static files that ship inside a published document.

Read straight from each app's ``static`` directory by app-relative path, never
through STATIC_ROOT, staticfiles finders or a URL, so generation works the same
in development, tests and production regardless of ``collectstatic``.

``SCRIPT_ENTRY`` is the only JavaScript entry point. What it pulls in is the
allowlist of shipped modules; the live Explorer's page wiring
(``explorer-boot.js``) and the Customise form module (``appearance-form.js``,
which can POST to the server) are deliberately not reachable from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps

from .bundler import bundle_modules

SCRIPT_ENTRY = ("publication", "js/portable/portable-boot.js")
VIS_SCRIPT = ("viewer", "vendor/vis-network/vis-network.min.js")
STYLESHEETS = (
    ("viewer", "vendor/vis-network/vis-network.min.css"),
    ("model", "css/explorer.css"),
    ("publication", "css/portable.css"),
)


class AssetMissing(Exception):
    """A file that must ship in every published document is not available."""


def static_path(app_label: str, relative: str) -> Path:
    path = Path(apps.get_app_config(app_label).path) / "static" / app_label / relative
    if not path.is_file():
        raise AssetMissing(f"Missing static asset: {app_label}/{relative}")
    return path


_SOURCE_MAP_COMMENT = re.compile(r"^\s*(?://[#@]|/\*[#@])\s*sourceMappingURL=.*$", re.MULTILINE)


def read_static(app_label: str, relative: str) -> str:
    """A shipped file's text, minus any source-map pointer (nothing may refer to a file that is not there)."""
    text = static_path(app_label, relative).read_text(encoding="utf-8")
    return _SOURCE_MAP_COMMENT.sub("", text)


@dataclass(frozen=True)
class PortableAssets:
    css: str
    vis_script: str
    app_script: str
    modules: tuple  # the JS modules inlined into ``app_script``


def load_assets() -> PortableAssets:
    bundled = bundle_modules(static_path(*SCRIPT_ENTRY))
    return PortableAssets(
        css="\n".join(read_static(*sheet) for sheet in STYLESHEETS),
        vis_script=read_static(*VIS_SCRIPT),
        app_script=bundled.code,
        modules=tuple(path.name for path in bundled.modules),
    )
