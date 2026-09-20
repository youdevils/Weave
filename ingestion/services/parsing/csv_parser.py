import csv
import io

from ingestion.services.errors import SourceFileError
from ingestion.services.parsing.table import build_table


def parse_csv(data: bytes):
    """
    UTF-8 (with or without a BOM), comma-delimited, RFC 4180 quoting. Any
    other encoding is rejected rather than guessed at: mis-decoding silently
    would corrupt identities and values.
    """

    if b"\x00" in data:
        raise SourceFileError(
            "This does not look like a CSV file (it contains binary data).",
            code="not_csv",
        )

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SourceFileError(
            'The file is not valid UTF-8. Save it as "CSV UTF-8" and try again.',
            code="bad_encoding",
        )

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)

    def records():
        # One record per spreadsheet row, so row numbers match what a user
        # sees in Excel (a quoted field may span several physical lines).
        try:
            for row_number, record in enumerate(reader, start=1):
                yield row_number, [cell if cell != "" else None for cell in record]
        except csv.Error as exc:
            raise SourceFileError(
                f"The CSV could not be read: {exc}.",
                code="malformed_csv",
            )

    return build_table("csv", records())
