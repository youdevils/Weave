"""
The resolved appearance contract: Weave-level visual identity, independent of
any viewer. Graph compilers turn these into viewer styles through
``viewer_adapter``; nothing here knows about vis-network.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResolvedTheme:
    accent: str
    canvas_background: str
    font_family: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedObjectAppearance:
    shape: str
    background: str
    border: str
    border_width: float
    size: float
    font_family: str
    font_colour: str
    font_size: float
    font_weight: str
    icon: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedRelationshipAppearance:
    colour: str
    width: float
    line_style: str
    arrows: str
    font_family: str
    label_colour: str
    label_size: float
    # Colour drawn around edge labels so they stay legible where they cross a
    # line; always the canvas background, so it is invisible against it.
    label_halo: str

    def to_dict(self) -> dict:
        return asdict(self)
