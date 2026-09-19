"""
Field schema, validation and stored-document sanitising for Model appearance.

This module is private to the appearance service package: it defines the
*only* structure ``Model.appearance`` may take. Nothing outside
``model.services.appearance`` reads or writes those keys.

The same field specs drive validation and the shared UI partial, so the form
and the rules can never drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import icons

# ------------------------------------------------------------------------------------
# Scopes
# ------------------------------------------------------------------------------------

THEME = "theme"
OBJECT = "object"
RELATIONSHIP = "relationship"

SCOPES = (THEME, OBJECT, RELATIONSHIP)

OBJECT_TYPE = "object_type"
RELATIONSHIP_TYPE = "relationship_type"

TYPE_KINDS = (OBJECT_TYPE, RELATIONSHIP_TYPE)

# The scope whose fields a given kind of type may override.
KIND_SCOPE = {
    OBJECT_TYPE: OBJECT,
    RELATIONSHIP_TYPE: RELATIONSHIP,
}

# ------------------------------------------------------------------------------------
# Curated choices
# ------------------------------------------------------------------------------------

# Web-safe / system font stacks only. The stored value *is* the stack, so a
# resolved value is always a valid CSS font-family list with fallbacks and a
# generic family, and stays predictable in browsers and self-contained HTML.
FONT_STACKS = (
    ("Arial, Helvetica, sans-serif", "Arial"),
    ('"Trebuchet MS", Helvetica, sans-serif', "Trebuchet"),
    ("Verdana, Geneva, sans-serif", "Verdana"),
    ('system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', "System UI"),
    ("Georgia, 'Times New Roman', serif", "Georgia"),
    ("'Times New Roman', Times, serif", "Times New Roman"),
    ("'Courier New', Courier, monospace", "Courier New"),
)

SHAPES = (
    ("box", "Box"),
    ("ellipse", "Ellipse"),
    ("circle", "Circle"),
    ("database", "Database"),
    ("diamond", "Diamond"),
    ("dot", "Dot"),
    ("square", "Square"),
    ("triangle", "Triangle"),
    ("hexagon", "Hexagon"),
    ("star", "Star"),
)

# vis-network sizes these shapes to their label, ignoring an explicit size.
TEXT_INSIDE_SHAPES = ("box", "ellipse", "circle", "database")

FONT_WEIGHTS = (("normal", "Normal"), ("bold", "Bold"))

LINE_STYLES = (("solid", "Solid"), ("dashed", "Dashed"), ("dotted", "Dotted"))

ARROWS = (
    ("none", "None"),
    ("to", "To target"),
    ("from", "To source"),
    ("both", "Both ends"),
)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    control: str  # "color" | "select" | "number" | "icon"
    group: str
    choices: tuple = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    help: str = ""
    type_only: bool = False  # only meaningful on a single type, never model-wide

    def choice_values(self) -> tuple:
        return tuple(value for value, _label in self.choices)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "control": self.control,
            "group": self.group,
            "choices": [{"value": value, "label": label} for value, label in self.choices],
            "min": self.minimum,
            "max": self.maximum,
            "step": self.step,
            "help": self.help,
        }


THEME_FIELDS = (
    FieldSpec("accent", "Accent colour", "color", "Colour", help="Default border colour for object types."),
    FieldSpec("canvas_background", "Graph background", "color", "Colour"),
    FieldSpec("font_family", "Font", "select", "Typography", choices=FONT_STACKS),
)

OBJECT_FIELDS = (
    FieldSpec("shape", "Shape", "select", "Shape", choices=SHAPES),
    FieldSpec(
        "size",
        "Size",
        "number",
        "Shape",
        minimum=10,
        maximum=80,
        step=1,
        help="Applies to dot, square, diamond, triangle, hexagon, star and icons. "
        "Box, ellipse, circle and database fit their label.",
    ),
    FieldSpec(
        "icon",
        "Icon",
        "icon",
        "Shape",
        choices=tuple((name, label) for name, label in icons.CHOICES),
        help="Replaces the shape with a circular icon.",
        type_only=True,
    ),
    FieldSpec("background", "Fill colour", "color", "Colour"),
    FieldSpec("border", "Border colour", "color", "Colour"),
    FieldSpec("border_width", "Border width", "number", "Colour", minimum=0, maximum=8, step=0.5),
    FieldSpec("font_colour", "Label colour", "color", "Label"),
    FieldSpec("font_size", "Label size", "number", "Label", minimum=8, maximum=32, step=1),
    FieldSpec("font_weight", "Label weight", "select", "Label", choices=FONT_WEIGHTS),
)

RELATIONSHIP_FIELDS = (
    FieldSpec("colour", "Line colour", "color", "Line"),
    FieldSpec("width", "Line width", "number", "Line", minimum=0.5, maximum=10, step=0.5),
    FieldSpec("line_style", "Line style", "select", "Line", choices=LINE_STYLES),
    FieldSpec("arrows", "Arrows", "select", "Line", choices=ARROWS),
    FieldSpec("label_colour", "Label colour", "color", "Label"),
    FieldSpec("label_size", "Label size", "number", "Label", minimum=8, maximum=24, step=1),
)

_FIELDS_BY_SCOPE = {
    THEME: THEME_FIELDS,
    OBJECT: OBJECT_FIELDS,
    RELATIONSHIP: RELATIONSHIP_FIELDS,
}


class AppearanceValidationError(ValueError):
    """A submitted appearance value is not acceptable."""


def field_specs(scope: str, *, model_level: bool = False) -> tuple[FieldSpec, ...]:
    """Fields for a scope. ``model_level`` drops fields that only make sense per type."""
    specs = _FIELDS_BY_SCOPE[scope]
    if model_level:
        return tuple(spec for spec in specs if not spec.type_only)
    return specs


def get_field(scope: str, key: str, *, model_level: bool = False) -> FieldSpec:
    for spec in field_specs(scope, model_level=model_level):
        if spec.key == key:
            return spec
    raise AppearanceValidationError(f"Unknown appearance field: {key}")


# ------------------------------------------------------------------------------------
# Value cleaning
# ------------------------------------------------------------------------------------

_HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _clean_colour(spec: FieldSpec, value: Any) -> str:
    if not isinstance(value, str) or not _HEX_COLOUR.match(value.strip()):
        raise AppearanceValidationError(f"{spec.label} must be a hex colour such as #4C6EF5.")
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    return f"#{text.upper()}"


def _clean_number(spec: FieldSpec, value: Any) -> int | float:
    if isinstance(value, bool):
        raise AppearanceValidationError(f"{spec.label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AppearanceValidationError(f"{spec.label} must be a number.") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise AppearanceValidationError(f"{spec.label} must be a number.")
    if spec.minimum is not None and number < spec.minimum:
        raise AppearanceValidationError(f"{spec.label} must be at least {spec.minimum:g}.")
    if spec.maximum is not None and number > spec.maximum:
        raise AppearanceValidationError(f"{spec.label} must be at most {spec.maximum:g}.")
    return int(number) if number == int(number) else number


def _clean_choice(spec: FieldSpec, value: Any) -> str:
    if not isinstance(value, str) or value not in spec.choice_values():
        raise AppearanceValidationError(f"{spec.label} must be one of the available choices.")
    return value


def clean_value(scope: str, key: str, value: Any, *, model_level: bool = False) -> Any:
    """Validate and normalise one value, raising AppearanceValidationError."""
    spec = get_field(scope, key, model_level=model_level)
    if spec.control == "color":
        return _clean_colour(spec, value)
    if spec.control == "number":
        return _clean_number(spec, value)
    return _clean_choice(spec, value)


def sanitise_layer(scope: str, raw: Any, *, model_level: bool = False) -> dict:
    """Drop unknown keys and invalid values from a stored layer; never raises."""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for spec in field_specs(scope, model_level=model_level):
        if spec.key not in raw:
            continue
        try:
            cleaned[spec.key] = clean_value(scope, spec.key, raw[spec.key], model_level=model_level)
        except AppearanceValidationError:
            continue
    return cleaned


# ------------------------------------------------------------------------------------
# Stored document (private structure)
# ------------------------------------------------------------------------------------

DOCUMENT_VERSION = 1

_MODEL_LAYERS = {
    THEME: "theme",
    OBJECT: "objects",
    RELATIONSHIP: "relationships",
}

_TYPE_MAPS = {
    OBJECT_TYPE: "object_types",
    RELATIONSHIP_TYPE: "relationship_types",
}


def empty_document() -> dict:
    return {
        "version": DOCUMENT_VERSION,
        "theme": {},
        "objects": {},
        "relationships": {},
        "object_types": {},
        "relationship_types": {},
    }


def sanitise_document(raw: Any) -> dict:
    """Return a well-formed document, discarding anything unrecognised."""
    document = empty_document()
    if not isinstance(raw, dict):
        return document

    for scope, doc_key in _MODEL_LAYERS.items():
        document[doc_key] = sanitise_layer(scope, raw.get(doc_key), model_level=True)

    for kind, doc_key in _TYPE_MAPS.items():
        entries = raw.get(doc_key)
        if not isinstance(entries, dict):
            continue
        for type_id, layer in entries.items():
            cleaned = sanitise_layer(KIND_SCOPE[kind], layer)
            if cleaned and isinstance(type_id, str):
                document[doc_key][type_id] = cleaned

    return document


def model_layer(document: dict, scope: str) -> dict:
    return document[_MODEL_LAYERS[scope]]


def type_map(document: dict, kind: str) -> dict:
    return document[_TYPE_MAPS[kind]]
