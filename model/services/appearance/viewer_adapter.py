"""
Turns resolved OnyxJar appearance into viewer-contract styles.

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
    # vis-network only defaults `enabled` to true for the plain string
    # shorthand ("to"/"from"/"to, from"); the object form needed to carry a
    # scaleFactor must set `enabled: True` itself, or it silently inherits
    # the library's `enabled: False` default and draws no arrow at all.
    "to": {"to": {"enabled": True, "scaleFactor": defaults.ARROW_SCALE_FACTOR}},
    "from": {"from": {"enabled": True, "scaleFactor": defaults.ARROW_SCALE_FACTOR}},
    "both": {
        "to": {"enabled": True, "scaleFactor": defaults.ARROW_SCALE_FACTOR},
        "from": {"enabled": True, "scaleFactor": defaults.ARROW_SCALE_FACTOR},
    },
}


def normalise_attribute_value(raw) -> str:
    """
    The key an instance's attribute value is looked up under in a colour map:
    Boolean collapses to "true"/"false"; every other value is its exact
    string form (choice values are matched as typed, not case-folded -- this
    is deliberately distinct from ``facets.py``'s case-insensitive counting).
    """
    if raw is True:
        return "true"
    if raw is False:
        return "false"
    return str(raw)


def _resolve_colour(source: str, attribute_key, by_value: dict, fallback: str, instance_attributes) -> str:
    """
    The colour for one visual property of one instance: the configured
    attribute's value, mapped through its colour, or the type's fixed colour
    when the source is "type", the attribute is unset, the instance has no
    value for it, or that value has no configured colour -- including when
    ``attribute_key`` itself no longer names an eligible attribute (a stale
    reference), since it then simply never matches an instance value either.
    """
    if source != "attribute" or not attribute_key or not instance_attributes:
        return fallback
    raw = instance_attributes.get(attribute_key)
    if raw is None:
        return fallback
    return by_value.get(normalise_attribute_value(raw), fallback)


def node_style(
    appearance: ResolvedObjectAppearance,
    *,
    is_proposed: bool = False,
    instance_attributes: dict | None = None,
) -> NodeStyle:
    background = _resolve_colour(
        appearance.background_source,
        appearance.background_attribute,
        appearance.background_by_value,
        appearance.background,
        instance_attributes,
    )
    border = _resolve_colour(
        appearance.border_source,
        appearance.border_attribute,
        appearance.border_by_value,
        appearance.border,
        instance_attributes,
    )
    if is_proposed:
        background = defaults.PROPOSED_NODE_BACKGROUND
        border = defaults.PROPOSED_NODE_BORDER

    font = {
        "color": appearance.font_colour,
        "size": appearance.font_size,
        "face": appearance.font_family,
        # A canvas-coloured stroke around the label, so it stays readable
        # where an edge crosses behind it without drawing a background box.
        "strokeColor": appearance.label_halo,
        "strokeWidth": 4,
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


def edge_style(
    appearance: ResolvedRelationshipAppearance,
    *,
    is_proposed: bool = False,
    instance_attributes: dict | None = None,
) -> EdgeStyle:
    colour = _resolve_colour(
        appearance.colour_source,
        appearance.colour_attribute,
        appearance.colour_by_value,
        appearance.colour,
        instance_attributes,
    )
    if is_proposed:
        colour = defaults.PROPOSED_EDGE_COLOUR
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
            "strokeWidth": 3,
        },
    )
