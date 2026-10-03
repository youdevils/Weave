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

IDENTITY_HEADERS = {OBJECT: "OnyxJar Object ID", RELATIONSHIP: "OnyxJar Relationship ID"}
FIELD_NAME_HEADER = "Name"
FIELD_DESCRIPTION_HEADER = "Description"
FIELD_IS_ACTIVE_HEADER = "Active"
ENDPOINT_SUBJECT_HEADER = "Source object"
ENDPOINT_OBJECT_HEADER = "Target object"

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


def template_columns(target) -> list[TemplateColumn]:
    """
    target: a targets.TargetSpec (from resolve_target / object_type_specs /
    relationship_type_specs). Column order:

      object:        OnyxJar Object ID | Name | Description | Active | <attrs>
      relationship:  OnyxJar Relationship ID | Source object | Target object | Active | <attrs>

    The identity-id column is always first and always optional: a value in it
    lets a filled-in file update an existing record instead of creating a new
    one, without forcing that choice on whoever fills the file in. It maps to
    the existing "identity.id" field, valid for both object and relationship
    imports (ingestion.services.mapping.OBJECT_FIELDS / RELATIONSHIP_FIELDS).

    Attribute columns follow target.attributes, already ordered
    (sort_order, name) by targets._attribute_specs.
    """

    columns = [TemplateColumn(IDENTITY_HEADERS[target.kind])]

    if target.kind == OBJECT:
        columns += [
            TemplateColumn(
                FIELD_NAME_HEADER,
                required=True,
                comment="Required when creating a new record.",
            ),
            TemplateColumn(FIELD_DESCRIPTION_HEADER),
            TemplateColumn(FIELD_IS_ACTIVE_HEADER, is_boolean=True),
        ]
    else:
        columns += [
            TemplateColumn(
                ENDPOINT_SUBJECT_HEADER,
                required=True,
                comment="Required: the OnyxJar ID of the source object, or a value "
                "that uniquely identifies it.",
            ),
            TemplateColumn(
                ENDPOINT_OBJECT_HEADER,
                required=True,
                comment="Required: the OnyxJar ID of the target object, or a value "
                "that uniquely identifies it.",
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


def build_csv_template(target) -> bytes:
    """Header row only -- no data rows (see ingestion/README.md's no_data_rows note:
    this is a starting point meant to be filled in before it is ever uploaded)."""

    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerow(
        [column.header for column in template_columns(target)]
    )
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


def build_xlsx_template(target) -> bytes:
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

    sheet.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


_BUILDERS = {CSV: build_csv_template, XLSX: build_xlsx_template}


def build_template(target, file_format: str) -> bytes:
    try:
        builder = _BUILDERS[file_format]
    except KeyError:
        raise ValueError(f"Unsupported template format: {file_format!r}")

    return builder(target)


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


def template_filename(model, target, file_format: str) -> str:
    suffix = f"-{_kind_word(target)}-{target.key}-template.{file_format}"
    slug = _model_slug(model)[: 150 - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"


def templates_zip_filename(model, file_format: str) -> str:
    suffix = f"-templates-{file_format}.zip"
    slug = _model_slug(model)[: 150 - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"
