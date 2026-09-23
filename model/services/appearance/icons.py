"""
A small curated catalogue of built-in icon glyphs for Object Types.

Glyphs are 24x24 stroke icons rendered as inline SVG data URIs, so they need
no asset storage. Arbitrary image upload is deliberately deferred until the
Assets area exists.
"""

from __future__ import annotations

from urllib.parse import quote

_GLYPHS = {
    "person": ("Person", '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>'),
    "organisation": (
        "Organisation",
        '<path d="M4 21V4h10v17M14 9h6v12M8 8h2M8 12h2M8 16h2M4 21h16"/>',
    ),
    "document": ("Document", '<path d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6"/>'),
    "database": (
        "Database",
        '<ellipse cx="12" cy="6" rx="7" ry="3"/>'
        '<path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    ),
    "process": (
        "Process",
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    ),
    "server": (
        "Server",
        '<rect x="3" y="4" width="18" height="6" rx="1"/><rect x="3" y="14" width="18" height="6" rx="1"/>'
        '<path d="M7 7h.01M7 17h.01"/>',
    ),
    "globe": (
        "Globe",
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    ),
    "folder": ("Folder", '<path d="M3 6h6l2 2h10v11H3z"/>'),
    "flag": ("Flag", '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>'),
    "shield": ("Shield", '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>'),
    "cube": ("Cube", '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5"/>'),
    "event": (
        "Event",
        '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
    ),
    # Business / organisational
    "team": (
        "Team",
        '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.9 2.7-6.5 6-6.5s6 2.6 6 6.5"/>'
        '<path d="M16 4.5c1.7.3 3 1.9 3 3.7s-1.3 3.4-3 3.7M21 20c-.3-2.7-1.7-4.7-3.8-5.4"/>',
    ),
    "building": (
        "Building",
        '<rect x="5" y="8" width="14" height="13"/><path d="M9 21v-5h6v5M9 12h.01M15 12h.01M12 12h.01"/>',
    ),
    "store": (
        "Store",
        '<path d="M3 9l1.2-5h15.6L21 9"/>'
        '<path d="M4 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3"/>'
        '<path d="M4 9v11h16V9M9 20v-6h6v6"/>',
    ),
    "product": (
        "Product",
        '<rect x="4" y="8" width="16" height="12" rx="1"/><path d="M4 8l8-4 8 4M12 4v16"/>',
    ),
    "task": (
        "Task",
        '<rect x="3" y="3" width="6" height="6" rx="1"/><path d="M4.5 6l1.2 1.2L7.5 4.5"/>'
        '<path d="M12 6h9M3 13h6M12 13h9M3 20h6M12 20h9"/>',
    ),
    "decision": (
        "Decision",
        '<path d="M12 2l10 10-10 10L2 12z"/><path d="M12 7v3M9.5 16l2.5-4 2.5 4"/>',
    ),
    "target": (
        "Target",
        '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    ),
    "money": (
        "Money",
        '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M6 9h.01M18 15h.01"/>',
    ),
    "calendar": (
        "Calendar",
        '<rect x="3" y="5" width="18" height="15" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>'
        '<path d="M7 13h.01M11 13h.01M15 13h.01M7 17h.01M11 17h.01M15 17h.01"/>',
    ),
    "warning": (
        "Warning",
        '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    ),
    "lock": (
        "Lock",
        '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/><path d="M12 15v3"/>',
    ),
    "key": (
        "Key",
        '<circle cx="7" cy="15" r="4"/><path d="M10 12l10-10M17 5l2 2M14 8l2 2"/>',
    ),
    # Technology / information
    "application": (
        "Application",
        '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M10 9l5 3-5 3z"/>',
    ),
    "website": (
        "Website",
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 8h18M6 6h.01M9 6h.01"/>',
    ),
    "mobile_device": (
        "Mobile device",
        '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    ),
    "api": (
        "API",
        '<path d="M8 3v4M16 3v4M6 7h12v4a6 6 0 01-12 0z"/><path d="M12 17v4"/>',
    ),
    "network": (
        "Network",
        '<circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/>'
        '<path d="M6.8 7.6L11 16M17.2 7.6L13 16M7.2 6h9.6"/>',
    ),
    "cloud": (
        "Cloud",
        '<path d="M7 18a4 4 0 01-1-7.9 5 5 0 019.6-2A4.5 4.5 0 0118 18H7z"/>',
    ),
    "spreadsheet": (
        "Spreadsheet",
        '<rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 9h18M3 14h18M9 4v16M15 4v16"/>',
    ),
    "chart": (
        "Chart",
        '<path d="M4 20V10M10 20V4M16 20v-7M4 20h16"/>',
    ),
    "search": (
        "Search",
        '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.8-4.8"/>',
    ),
    # Farming / agricultural
    "farm": (
        "Farm",
        '<circle cx="18" cy="6" r="2.5"/><path d="M2 18c3-4 6-4 9 0s6 4 9 0"/><path d="M2 21h20"/>',
    ),
    "field": (
        "Field",
        '<path d="M3 6c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/><path d="M3 12c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>'
        '<path d="M3 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>',
    ),
    "tractor": (
        "Tractor",
        '<circle cx="6" cy="18" r="3"/><circle cx="17" cy="18" r="2"/>'
        '<path d="M9 18h5.5M19 18h1v-4.5h-3l-2-3.5H9v8M9 10H6l-2 4"/><path d="M16 6v4"/>',
    ),
    "livestock": (
        "Livestock",
        '<path d="M7 10c0-2 1-4 5-4s5 2 5 4"/><path d="M5 10h14l-1 6a4 6 0 01-4 4h-4a4 6 0 01-4-4z"/>'
        '<circle cx="9.5" cy="14" r=".5"/><circle cx="14.5" cy="14" r=".5"/>',
    ),
    "crop": (
        "Crop",
        '<path d="M12 21V9"/><path d="M12 9c0-4-3-6-7-6 0 4 3 7 7 7zM12 9c0-4 3-6 7-6 0 4-3 7-7 7z"/>',
    ),
    "barn": (
        "Barn",
        '<path d="M2 10l4-6h12l4 6"/><path d="M4 10v11h16V10"/><path d="M9 21v-5a3 3 0 016 0v5"/>',
    ),
    "fence": (
        "Fence",
        '<path d="M5 3v18M12 3v18M19 3v18"/><path d="M2 9h20M2 15h20"/>',
    ),
    "water": (
        "Water",
        '<path d="M12 2c4 5 7 8.5 7 12a7 7 0 01-14 0c0-3.5 3-7 7-12z"/>',
    ),
    "weather": (
        "Weather",
        '<circle cx="8" cy="8" r="3.5"/><path d="M8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.8 3.8l1 1M11.2 3.8l-1 1"/>'
        '<path d="M9 15a4.5 4.5 0 014.4 3.6A3.6 3.6 0 0113 22H7a3.5 3.5 0 01-.6-6.9A4.5 4.5 0 019 15z"/>',
    ),
}

CHOICES = tuple((name, label) for name, (label, _body) in _GLYPHS.items())

NAMES = tuple(_GLYPHS)


def icon_svg(name: str, colour: str) -> str:
    """The SVG markup for a named icon, stroked in ``colour`` (a #RRGGBB string)."""
    _label, body = _GLYPHS[name]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{colour}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def icon_data_uri(name: str, colour: str) -> str:
    return "data:image/svg+xml;charset=utf-8," + quote(icon_svg(name, colour), safe="")
