"""
Centralized file type management and category mapping.
"""

from enum import Enum
from pathlib import Path


class FileCategory(str, Enum):
    PDF = "PDF"
    DOCUMENT = "DOCUMENT"  # Word, etc.
    SPREADSHEET = "SPREADSHEET"  # Excel, etc.
    DATA = "DATA"  # CSV, JSON
    EMAIL = "EMAIL"  # EML, MSG
    UNSUPPORTED = "UNSUPPORTED"


# Map extensions to categories
# This is the single source of truth for file support
CATEGORY_MAPPING = {
    ".pdf": FileCategory.PDF,
    ".doc": FileCategory.DOCUMENT,
    ".docx": FileCategory.DOCUMENT,
    ".xlsx": FileCategory.SPREADSHEET,
    ".xls": FileCategory.SPREADSHEET,
    ".csv": FileCategory.DATA,
    ".json": FileCategory.DATA,
    ".eml": FileCategory.EMAIL,
    ".msg": FileCategory.EMAIL,
}


def get_file_category(file_path: Path | str) -> FileCategory:
    """Identify the FileCategory based on the file extension."""
    ext = Path(file_path).suffix.lower()
    return CATEGORY_MAPPING.get(ext, FileCategory.UNSUPPORTED)


def is_supported(file_path: Path | str) -> bool:
    """Check if the file format is supported by any handler."""
    return get_file_category(file_path) != FileCategory.UNSUPPORTED
