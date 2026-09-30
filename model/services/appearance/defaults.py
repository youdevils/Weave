"""
OnyxJar's built-in visual defaults: the bottom layer of

    built-in default -> model customisation -> Object Type / Relationship Type override

These reproduce the look the ontology overview had before customisation
existed, so a model that has never been customised renders unchanged.
"""

from __future__ import annotations

THEME_DEFAULTS = {
    "accent": "#4C6EF5",
    "canvas_background": "#FFFFFF",
    "font_family": "Arial, Helvetica, sans-serif",
}

# ``border`` is deliberately absent: an object's border defaults to the
# resolved theme accent (see resolver), so re-theming the accent recolours
# every type that has not chosen its own border.
OBJECT_DEFAULTS = {
    "shape": "box",
    "background": "#EDF2FF",
    "background_source": "type",
    "background_attribute": None,
    "border_width": 1.5,
    "border_source": "type",
    "border_attribute": None,
    "size": 25,
    "font_colour": "#212529",
    "font_size": 14,
    "font_weight": "normal",
    "icon": None,
}

RELATIONSHIP_DEFAULTS = {
    "colour": "#495057",
    "colour_source": "type",
    "colour_attribute": None,
    "width": 1.5,
    "line_style": "solid",
    "arrows": "to",
    "label_colour": "#495057",
    "label_size": 11,
}

# Shrinks the drawn arrowhead so it covers less area where it can land on a
# node label (vis-network always paints arrowheads last, on top of labels).
ARROW_SCALE_FACTOR = 0.6

# The restrained treatment for elements that exist only in the active
# proposal. It is a proposal-state cue, not part of a type's visual identity,
# so it is not user-customisable and never stored.
PROPOSED_NODE_BACKGROUND = "#FFF3BF"
PROPOSED_NODE_BORDER = "#F08C00"
PROPOSED_EDGE_COLOUR = "#F08C00"
