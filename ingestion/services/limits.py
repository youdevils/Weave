"""
Import limits, read from settings at call time (see IMPORT_* in settings.py)
so they can be tuned, and overridden in tests, without touching import code.
"""

from django.conf import settings


def max_file_bytes() -> int:
    return settings.IMPORT_MAX_FILE_BYTES


def max_rows() -> int:
    return settings.IMPORT_MAX_ROWS


def max_columns() -> int:
    return settings.IMPORT_MAX_COLUMNS


def max_header_chars() -> int:
    return settings.IMPORT_MAX_HEADER_CHARS


def max_cell_chars() -> int:
    return settings.IMPORT_MAX_CELL_CHARS


def max_changes() -> int:
    return settings.IMPORT_MAX_CHANGES


def xlsx_max_uncompressed_bytes() -> int:
    return settings.IMPORT_XLSX_MAX_UNCOMPRESSED_BYTES


def xlsx_max_compression_ratio() -> int:
    return settings.IMPORT_XLSX_MAX_COMPRESSION_RATIO


def staged_source_ttl():
    return settings.IMPORT_STAGED_SOURCE_TTL


def problems_shown() -> int:
    return settings.IMPORT_PROBLEMS_SHOWN


# Physical rows examined in a worksheet before giving up. A sheet can carry
# hundreds of thousands of formatted-but-empty rows below its data; this stops
# such a sheet costing unbounded time without rejecting ordinary ones.
MAX_SCANNED_ROWS = 200_000
