"""
Turning a parsed cell into the value a ProposalChange carries.

This is representation only. A cell from a spreadsheet (a float 3.0, a date, a
"yes") becomes the JSON shape the target field stores. Whether the result is
*allowed* (choices, ranges, required, ...) is never decided here; that is the
Proposal validator's job. A value that cannot be read as the target type is
passed through unchanged, so the validator rejects it with its usual message.
"""

import datetime
from dataclasses import dataclass

from model.models.attribute_definition import AttributeDefinition
from model.services.coercion import coerce_attribute_value

DataType = AttributeDefinition.DataType


@dataclass(frozen=True)
class Coerced:
    value: object
    # False when the cell could not be read as the target type and `value` is
    # the raw text passed through. (Informational; never blocks by itself.)
    converted: bool = True


def is_blank(value) -> bool:
    if value is None:
        return True

    return isinstance(value, str) and not value.strip()


def cell_text(value) -> str:
    """A cell as text, the way a person would type it into a text field."""

    if isinstance(value, str):
        return value

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)

    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()

    return str(value)


def coerce_attribute_cell(data_type, value) -> Coerced:
    """Blank -> None (no value); otherwise the JSON value for `data_type`."""

    if is_blank(value):
        return Coerced(None)

    if data_type in (DataType.TEXT, DataType.URL, DataType.CHOICE):
        return Coerced(cell_text(value).strip())

    if data_type == DataType.NUMBER:
        return _number(value)

    if data_type == DataType.BOOLEAN:
        return _boolean(value)

    if data_type == DataType.DATE:
        return _date(value)

    if data_type == DataType.DATETIME:
        return _datetime(value)

    return Coerced(cell_text(value).strip())


def format_cell(data_type, value):
    """
    The inverse of coerce_attribute_cell: a stored attribute value -> the
    cell value a filled-in template would have held for it, so that
    ``coerce_attribute_cell(data_type, format_cell(data_type, value)).value
    == value`` for every value coerce_attribute_cell actually produces. Used
    only to build the optional "with current data" template download -- the
    blank starting-point template never carries data rows.

    None (unset) becomes "" (an empty cell). TEXT/URL/CHOICE/DATE/DATETIME
    are already stored as the exact string coerce_attribute_cell produced,
    so they are written back unchanged, with no reformatting to drift from
    it. NUMBER is written as the number itself (both csv and xlsx render it
    the same way back to text). BOOLEAN is written as lowercase "true"/
    "false" text, matching the template's own dropdown values.
    """

    if value is None:
        return ""

    if data_type == DataType.BOOLEAN:
        return "true" if value else "false"

    return value


def format_is_active_cell(value) -> str:
    """is_active is a plain boolean; blank means "take the default", never written here."""

    return "true" if value else "false"


def coerce_name_cell(value) -> str:
    """Name/description: text, with blank as the empty string."""

    return "" if is_blank(value) else cell_text(value).strip()


def coerce_is_active_cell(value) -> Coerced:
    """A boolean; blank has no boolean meaning and becomes None (unset)."""

    if is_blank(value):
        return Coerced(None)

    return _boolean(value)


def _number(value):

    if isinstance(value, bool):
        # A boolean is not a number; leave it for the validator to reject.
        return Coerced(value, converted=False)

    if isinstance(value, int):
        return Coerced(value)

    if isinstance(value, float):
        return Coerced(int(value) if value.is_integer() else value)

    text = cell_text(value).strip()

    try:
        parsed = coerce_attribute_value(DataType.NUMBER, text)
    except ValueError:
        return Coerced(text, converted=False)

    if isinstance(parsed, float) and parsed.is_integer() and "." not in text:
        parsed = int(parsed)

    return Coerced(parsed)


def _boolean(value):

    if isinstance(value, bool):
        return Coerced(value)

    text = cell_text(value).strip()

    try:
        return Coerced(coerce_attribute_value(DataType.BOOLEAN, text))
    except ValueError:
        return Coerced(text, converted=False)


def _date(value):

    if isinstance(value, datetime.datetime):
        if value.time() == datetime.time(0, 0):
            return Coerced(value.date().isoformat())
        return Coerced(value.isoformat(), converted=False)

    if isinstance(value, datetime.date):
        return Coerced(value.isoformat())

    return Coerced(cell_text(value).strip())


def _datetime(value):

    if isinstance(value, (datetime.datetime, datetime.date)):
        return Coerced(value.isoformat())

    return Coerced(cell_text(value).strip())
