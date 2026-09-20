import io

from ingestion.services import limits
from ingestion.services.errors import SourceFileError
from ingestion.services.parsing.table import build_table

_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def parse_xls(data: bytes):
    """
    A legacy .xls workbook with exactly one worksheet, read with xlrd.
    Nothing is executed and formulas are never evaluated: a formula cell
    contributes the value stored with it.
    """

    if not data.startswith(_OLE_MAGIC):
        raise SourceFileError(
            "This is not a valid .xls file.",
            code="bad_signature",
        )

    import xlrd

    try:
        book = xlrd.open_workbook(
            file_contents=data,
            logfile=io.StringIO(),
            formatting_info=False,
            on_demand=False,
        )
    except Exception as exc:  # xlrd raises XLRDError and assorted struct/index errors
        raise SourceFileError(
            "This .xls file could not be read (it may be corrupt or password protected).",
            code="malformed_workbook",
        ) from exc

    try:

        if book.nsheets != 1:
            raise SourceFileError(
                f"The workbook has {book.nsheets} worksheets. "
                "Data Import supports exactly one worksheet per file.",
                code="multiple_sheets",
            )

        sheet = book.sheet_by_index(0)

        if sheet.nrows > limits.MAX_SCANNED_ROWS:
            raise SourceFileError(
                "The worksheet has too many rows. Delete unused rows and try again.",
                code="too_many_rows",
            )

        def rows():
            for index in range(sheet.nrows):
                yield index + 1, [
                    _value(sheet, index, column, book.datemode) for column in range(sheet.ncols)
                ]

        return build_table("xls", rows())

    finally:
        book.release_resources()


def _value(sheet, row, column, datemode):
    import xlrd

    cell = sheet.cell(row, column)
    kind = cell.ctype

    if kind in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return None

    if kind == xlrd.XL_CELL_ERROR:
        raise SourceFileError(
            f"Row {row + 1}, column {column + 1} contains an Excel error value.",
            code="error_cell",
        )

    if kind == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)

    if kind == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate.xldate_as_datetime(cell.value, datemode)
        except (ValueError, OverflowError, xlrd.xldate.XLDateError):
            raise SourceFileError(
                f"Row {row + 1}, column {column + 1} contains an invalid date.",
                code="bad_date",
            )

    if kind == xlrd.XL_CELL_NUMBER:
        return cell.value

    return cell.value if isinstance(cell.value, str) else str(cell.value)
