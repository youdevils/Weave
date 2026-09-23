"""
The resolved appearance contract: Weave-level visual identity, independent of
any viewer. Graph compilers turn these into viewer styles through
``viewer_adapter``; nothing here knows about vis-network.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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
    background_source: str = "type"
    background_attribute: str | None = None
    # value -> hex, populated only when background_source == "attribute".
    background_by_value: dict = field(default_factory=dict)
    border_source: str = "type"
    border_attribute: str | None = None
    border_by_value: dict = field(default_factory=dict)

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
    colour_source: str = "type"
    colour_attribute: str | None = None
    # value -> hex, populated only when colour_source == "attribute".
    colour_by_value: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
