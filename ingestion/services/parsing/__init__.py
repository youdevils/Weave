from ingestion.services.errors import SourceFileError
from ingestion.services.parsing.csv_parser import parse_csv
from ingestion.services.parsing.table import ParsedTable, is_blank
from ingestion.services.parsing.xls_parser import parse_xls
from ingestion.services.parsing.xlsx_parser import parse_xlsx

PARSERS = {
    "csv": parse_csv,
    "xlsx": parse_xlsx,
    "xls": parse_xls,
}


def parse_table(file_format: str, data: bytes) -> ParsedTable:
    """Parse `data` as `file_format` (csv / xlsx / xls) into a single table."""

    parser = PARSERS.get(file_format)

    if parser is None:
        raise SourceFileError("Unsupported file format.", code="unsupported_format")

    return parser(data)


__all__ = ["ParsedTable", "is_blank", "parse_table"]
