"""
Turns resolved Weave appearance into viewer-contract styles.

This is the only appearance module that knows about ``viewer.contracts``. The
resolver stays viewer-independent; every graph compiler (the ontology overview
today, data and publishing views later) shares this one translation so a type
looks identical wherever it is drawn.

It also applies the proposal-overlay cue: elements that exist only in the
active proposal keep their shape, size, font and icon but swap to a restrained
amber palette (dashed for edges), so they stay recognisable yet distinct.
"""

from __future__ import annotations

from viewer.contracts import EdgeStyle, NodeStyle

from . import defaults, icons
from .resolved import ResolvedObjectAppearance, ResolvedRelationshipAppearance

_DASHES = {
    "solid": None,
    "dashed": [8, 6],
    "dotted": [2, 4],
}

_ARROWS = {
    "none": None,
    "to": "to",
    "from": "from",
    "both": "to, from",
}


def node_style(appearance: ResolvedObjectAppearance, *, is_proposed: bool = False) -> NodeStyle:
    background = appearance.background
    border = appearance.border
    if is_proposed:
        background = defaults.PROPOSED_NODE_BACKGROUND
        border = defaults.PROPOSED_NODE_BORDER

    font = {
        "color": appearance.font_colour,
        "size": appearance.font_size,
        "face": appearance.font_family,
    }
    if appearance.font_weight == "bold":
        font["weight"] = "bold"

    shape = appearance.shape
    image = None
    if appearance.icon:
        shape = "circularImage"
        image = icons.icon_data_uri(appearance.icon, border)

    return NodeStyle(
        shape=shape,
        background=background,
        border=border,
        border_width=appearance.border_width,
        font=font,
        size=appearance.size,
        image=image,
    )


def edge_style(appearance: ResolvedRelationshipAppearance, *, is_proposed: bool = False) -> EdgeStyle:
    colour = defaults.PROPOSED_EDGE_COLOUR if is_proposed else appearance.colour
    dashes = True if is_proposed else _DASHES[appearance.line_style]

    return EdgeStyle(
        colour=colour,
        width=appearance.width,
        dashes=dashes,
        arrows=_ARROWS[appearance.arrows],
        font={
            "color": appearance.label_colour,
            "size": appearance.label_size,
            "face": appearance.font_family,
            "strokeColor": appearance.label_halo,
        },
    )
