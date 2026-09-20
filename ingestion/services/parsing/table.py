"""
The parsers' common output, and the row/column rules they share.

A parser turns bytes into a `ParsedTable`: one header row and the data rows
below it, every cell a plain Python value (str, int, float, bool, datetime,
date, or None for an empty cell). Parsers never evaluate anything and never
interpret a value for the model; that is the coercion layer's job.
"""

from dataclasses import dataclass, field

from ingestion.services import limits
from ingestion.services.errors import SourceFileError


@dataclass(frozen=True)
class ParsedTable:
    file_format: str
    headers: tuple
    rows: tuple  # tuple of tuples, each exactly len(headers) long
    row_numbers: tuple  # source row number of each data row (1-based, as in a spreadsheet)
    header_row_number: int = 1
    warnings: tuple = field(default_factory=tuple)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.headers)


def is_blank(value) -> bool:
    """An empty cell, or text that is only whitespace."""

    if value is None:
        return True

    return isinstance(value, str) and not value.strip()


def build_table(file_format, raw_rows, *, warnings=()):
    """
    Turn an iterable of (row_number, cells) into a ParsedTable, applying the
    rules every format shares:

      * blank rows are skipped;
      * the first non-blank row is the header (cells stringified and trimmed,
        a blank header becomes "Column N");
      * data rows are padded to the header width; a *non-blank* cell beyond
        the header is an error rather than silently dropped;
      * the row / column / header / cell limits are enforced.
    """

    max_rows = limits.max_rows()
    max_columns = limits.max_columns()
    max_header = limits.max_header_chars()
    max_cell = limits.max_cell_chars()

    headers = None
    header_row_number = 1
    rows = []
    row_numbers = []

    for row_number, cells in raw_rows:

        cells = _trim_trailing_blanks(list(cells))

        if not cells:
            continue

        if headers is None:

            if len(cells) > max_columns:
                raise SourceFileError(
                    f"The file has more than {max_columns} columns.",
                    code="too_many_columns",
                )

            headers = []

            for index, cell in enumerate(cells):
                text = "" if cell is None else str(cell).strip()

                if len(text) > max_header:
                    raise SourceFileError(
                        f"The header in column {index + 1} is longer than "
                        f"{max_header} characters.",
                        code="header_too_long",
                    )

                headers.append(text or f"Column {index + 1}")

            header_row_number = row_number
            continue

        if len(cells) > len(headers):
            raise SourceFileError(
                f"Row {row_number} has more columns than the header row.",
                code="ragged_rows",
            )

        if len(rows) >= max_rows:
            raise SourceFileError(
                f"The file has more than {max_rows} data rows.",
                code="too_many_rows",
            )

        for cell in cells:
            if isinstance(cell, str) and len(cell) > max_cell:
                raise SourceFileError(
                    f"Row {row_number} has a cell longer than {max_cell} characters.",
                    code="cell_too_long",
                )

        cells.extend([None] * (len(headers) - len(cells)))

        rows.append(tuple(cells))
        row_numbers.append(row_number)

    if headers is None:
        raise SourceFileError("The file is empty.", code="empty_file")

    if not rows:
        raise SourceFileError(
            "The file has a header row but no data rows.",
            code="no_data_rows",
        )

    return ParsedTable(
        file_format=file_format,
        headers=tuple(headers),
        rows=tuple(rows),
        row_numbers=tuple(row_numbers),
        header_row_number=header_row_number,
        warnings=tuple(warnings),
    )


def _trim_trailing_blanks(cells):
    """
    Drop trailing blank cells. An entirely blank row is left with nothing; a
    row with content keeps its interior blanks so column positions hold.
    """

    while cells and is_blank(cells[-1]):
        cells.pop()

    return cells
