"""
Import templates: one CSV or XLSX file per object/relationship type, built
from the model's current structure so it can be filled in and then uploaded
through the existing Import wizard (see ingestion/README.md).

Templates are generated fresh on every request from canonical ObjectType /
RelationshipType / AttributeDefinition rows -- nothing here is persisted or
cached. Column order and header text exist only to guide a person filling the
file in: ingestion.services.mapping addresses columns by 0-based index, never
by header text, so nothing written here is interpreted by the import
pipeline.

Every file this module produces -- including each member of a zip bundle --
is exactly one worksheet / one target type, matching the importer's own
"one file = one type, one worksheet" rule (ingestion.services.parsing). The
importer is never extended to accept multiple sheets or multiple types in
one file; a "download everything" request is satisfied by bundling
independent, individually-importable files in a zip, not by inventing a
combined format.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass

from django.utils.text import slugify

from ingestion.services.coercion import format_cell, format_is_active_cell
from ingestion.services.targets import (
    OBJECT,
    RELATIONSHIP,
    object_type_specs,
    relationship_type_specs,
)

CSV = "csv"
XLSX = "xlsx"
FILE_FORMATS = (CSV, XLSX)

CONTENT_TYPES = {
    CSV: "text/csv",
    XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ZIP_CONTENT_TYPE = "application/zip"

IDENTITY_KEY_HEADER = "OnyxJar Key"
FIELD_NAME_HEADER = "Name"
FIELD_DESCRIPTION_HEADER = "Description"
FIELD_IS_ACTIVE_HEADER = "Active"
ENDPOINT_SUBJECT_HEADER = "Source object key"
ENDPOINT_OBJECT_HEADER = "Target object key"

DATE_TYPES = {"date", "datetime"}
BOOLEAN_TYPE = "boolean"
CHOICE_TYPE = "choice"

# Rows pre-wired with a dropdown in the generated xlsx. Not a hard limit on
# how many data rows a person can add -- just how far the convenience
# dropdown reaches before they'd need to copy the validation down themselves.
DROPDOWN_ROWS = 1000

# Excel's own limit on an inline list literal passed to DataValidation.
MAX_INLINE_LIST_CHARS = 255

_UNSAFE_SHEET_CHARS = re.compile(r"[:\\/?*\[\]]")


@dataclass(frozen=True)
class TemplateColumn:
    header: str
    required: bool = False
    choices: tuple = ()
    is_boolean: bool = False
    is_date: bool = False
    comment: str | None = None


def _endpoint_type_names(target, type_ids) -> str:
    names = sorted(target.endpoint_type_name(type_id) or "?" for type_id in type_ids)
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} or {names[1]}"
    return ", ".join(names[:-1]) + f", or {names[-1]}"


def template_columns(target) -> list[TemplateColumn]:
    """
    target: a targets.TargetSpec (from resolve_target / object_type_specs /
    relationship_type_specs). Column order:

      object:        OnyxJar Key | Name | Description | Active | <attrs>
      relationship:  Source object key | Target object key | Active | <attrs>

    The normal identity column for each kind is always optional: a value in
    it lets a filled-in file update an existing record instead of creating a
    new one, without forcing that choice on whoever fills the file in.
    Object's own Database ID (the internal UUID) is not part of this
    generated file -- it stays available as an advanced/optional column the
    import wizard can map manually, for files that already use it; the
    normal column here is always the key. Relationship has no key of its
    own (see ingestion/README.md); its identity is its type plus its
    endpoints, so there is no identity column for it at all here -- only
    the endpoint key columns below.

    Attribute columns follow target.attributes, already ordered
    (sort_order, name) by targets._attribute_specs.
    """

    if target.kind == OBJECT:
        columns = [
            TemplateColumn(
                IDENTITY_KEY_HEADER,
                comment="Leave blank to create a new object (OnyxJar assigns its key). "
                "Enter an existing object's key to update it.",
            ),
            TemplateColumn(
                FIELD_NAME_HEADER,
                required=True,
                comment="Required when creating a new record.",
            ),
            TemplateColumn(FIELD_DESCRIPTION_HEADER),
            TemplateColumn(FIELD_IS_ACTIVE_HEADER, is_boolean=True),
        ]
    else:
        columns = [
            TemplateColumn(
                ENDPOINT_SUBJECT_HEADER,
                required=True,
                comment=f"Required: the key of a {_endpoint_type_names(target, target.subject_type_ids)} object.",
            ),
            TemplateColumn(
                ENDPOINT_OBJECT_HEADER,
                required=True,
                comment=f"Required: the key of a {_endpoint_type_names(target, target.object_type_ids)} object.",
            ),
            TemplateColumn(FIELD_IS_ACTIVE_HEADER, is_boolean=True),
        ]

    for attribute in target.attributes:
        is_date = attribute.data_type in DATE_TYPES

        if attribute.required:
            comment = "Required."
        elif attribute.data_type == "date":
            comment = "Format: YYYY-MM-DD."
        elif attribute.data_type == "datetime":
            comment = "Format: YYYY-MM-DDTHH:MM:SS."
        else:
            comment = None

        columns.append(
            TemplateColumn(
                header=attribute.name,
                required=attribute.required,
                choices=attribute.choices if attribute.data_type == CHOICE_TYPE else (),
                is_boolean=attribute.data_type == BOOLEAN_TYPE,
                is_date=is_date,
                comment=comment,
            )
        )

    return columns


def data_rows(model, target) -> list[list]:
    """
    `model`'s current canonical rows for `target`, one row per object/
    relationship, in exactly template_columns(target) order -- the inverse
    of what the import wizard reads from a filled-in file. Used only for
    the optional "download with current data" template; the default,
    blank starting-point template never calls this (see
    ingestion/README.md's no_data_rows note).
    """

    if target.kind == OBJECT:
        return _object_data_rows(model, target)

    return _relationship_data_rows(model, target)


def _object_data_rows(model, target) -> list[list]:
    from model.models.object import Object

    rows = []

    for obj in Object.objects.filter(model=model, object_type_id=target.type_id).order_by("name", "id"):
        row = [obj.key, obj.name, obj.description, format_is_active_cell(obj.is_active)]

        for attribute in target.attributes:
            row.append(format_cell(attribute.data_type, (obj.attributes or {}).get(attribute.key)))

        rows.append(row)

    return rows


def _relationship_data_rows(model, target) -> list[list]:
    from model.models.relationship import Relationship

    rows = []

    query = (
        Relationship.objects.filter(model=model, relationship_type_id=target.type_id)
        .select_related("subject", "object")
        .order_by("id")
    )

    for relationship in query:
        row = [
            relationship.subject.key,
            relationship.object.key,
            format_is_active_cell(relationship.is_active),
        ]

        for attribute in target.attributes:
            row.append(format_cell(attribute.data_type, (relationship.attributes or {}).get(attribute.key)))

        rows.append(row)

    return rows


def build_csv_template(target, rows: list[list] | None = None) -> bytes:
    """
    Header row, plus `rows` (see data_rows) when given. Without `rows`,
    this is a starting point meant to be filled in before it is ever
    uploaded (see ingestion/README.md's no_data_rows note).
    """

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([column.header for column in template_columns(target)])

    for row in rows or ():
        writer.writerow(row)

    # utf-8-sig: Excel-friendly BOM; ingestion.services.parsing.csv_parser already tolerates it.
    return buffer.getvalue().encode("utf-8-sig")


def _inline_list_formula(choices) -> str | None:
    """
    A safe Excel inline-list DataValidation formula for `choices`, or None if
    the values can't be represented that way. Excel's inline list syntax has
    no escape for a comma (it is always the item separator), so any choice
    containing one makes the whole list unsafe -- there is no helper
    sheet/range fallback (that would add a second sheet, or extra cells on
    the one data sheet, either of which this module avoids entirely). A
    literal double quote is escaped by doubling, the one escape Excel's own
    quoted-string syntax defines.
    """

    if not choices:
        return None

    for choice in choices:
        if "," in choice or any(ord(ch) < 0x20 for ch in choice):
            return None

    escaped = [choice.replace('"', '""') for choice in choices]
    formula = '"' + ",".join(escaped) + '"'

    if len(formula) > MAX_INLINE_LIST_CHARS:
        return None

    return formula


def _sheet_title(target) -> str:
    title = _UNSAFE_SHEET_CHARS.sub("", target.name)[:31].strip()
    return title or "Template"


def build_xlsx_template(target, rows: list[list] | None = None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    columns = template_columns(target)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _sheet_title(target)

    bold = Font(bold=True)

    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=column.header)

        if column.required:
            cell.font = bold
        if column.comment:
            cell.comment = Comment(column.comment, "OnyxJar")

        letter = get_column_letter(index)
        data_range = f"{letter}2:{letter}{DROPDOWN_ROWS + 1}"

        formula = None
        if column.choices:
            formula = _inline_list_formula(column.choices)
        elif column.is_boolean:
            formula = '"true,false"'

        if formula is not None:
            validation = DataValidation(type="list", formula1=formula, allow_blank=True)
            validation.error = "Choose one of the listed values."
            sheet.add_data_validation(validation)
            validation.add(data_range)

    # Every data cell is written as its exact Python value (a str for text/
    # key/boolean columns, a number for NUMBER attributes) -- openpyxl always
    # stores a str value as Excel's own text type, so a numeric-looking key
    # (however unlikely) is never silently read back as a number.
    for row_index, row in enumerate(rows or (), start=2):
        for col_index, value in enumerate(row, start=1):
            sheet.cell(row=row_index, column=col_index, value=value)

    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


_BUILDERS = {CSV: build_csv_template, XLSX: build_xlsx_template}


def build_template(target, file_format: str, *, model=None, with_data: bool = False) -> bytes:
    """
    `model` is only read when `with_data` is true (to build its current
    rows via data_rows); the default, blank starting-point template never
    touches canonical data.
    """

    try:
        builder = _BUILDERS[file_format]
    except KeyError:
        raise ValueError(f"Unsupported template format: {file_format!r}")

    rows = data_rows(model, target) if with_data else None
    return builder(target, rows)


def _kind_word(target) -> str:
    return "object" if target.kind == OBJECT else "relationship"


def _member_filename(target, file_format: str) -> str:
    return f"{_kind_word(target)}-{target.key}.{file_format}"


def build_templates_zip(model, file_format: str) -> bytes:
    """One independently-importable file per active type of `model`; may be empty."""

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for spec in object_type_specs(model).values():
            archive.writestr(_member_filename(spec, file_format), build_template(spec, file_format))
        for spec in relationship_type_specs(model).values():
            archive.writestr(_member_filename(spec, file_format), build_template(spec, file_format))

    return buffer.getvalue()


def _model_slug(model) -> str:
    return slugify(model.name or "") or "model"


def template_filename(model, target, file_format: str, *, with_data: bool = False) -> str:
    data_part = "-with-data" if with_data else ""
    suffix = f"-{_kind_word(target)}-{target.key}-template{data_part}.{file_format}"
    slug = _model_slug(model)[: 150 - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"


def templates_zip_filename(model, file_format: str) -> str:
    suffix = f"-templates-{file_format}.zip"
    slug = _model_slug(model)[: 150 - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"
