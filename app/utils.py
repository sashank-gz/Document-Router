"""
Shared utility functions for UI rendering and file path safety.
"""

import re
from pathlib import Path

from fastapi import HTTPException

# Constants for file validation
SAFE_PROCESSED_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._()\- ]*$")
ALLOWED_PROCESSED_EXTENSIONS = {
    ".pdf",
    ".md",
    ".json",
    ".html",
    ".txt",
    ".doc",
    ".docx",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".csv",
    ".eml",
    ".msg",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".bmp",
    ".webp",
    ".zip",
}


def highlight_json(escaped_html: str) -> str:
    """Apply syntax-coloring to HTML-escaped JSON text."""
    # Keys (purple)
    escaped_html = re.sub(
        r"(&quot;[^&]*?&quot;)\s*:",
        r'<span style="color:#C084FC">\1</span>:',
        escaped_html,
    )
    # String values (green)
    escaped_html = re.sub(
        r":\s*(&quot;[^&]*?&quot;)",
        r': <span style="color:#6EE7B7">\1</span>',
        escaped_html,
    )
    # Numbers (orange)
    escaped_html = re.sub(
        r"(?<=: )(-?\d+\.?\d*)",
        r'<span style="color:#FDBA74">\1</span>',
        escaped_html,
    )
    # Booleans / null (blue)
    escaped_html = re.sub(
        r"(?<=: )(true|false|null)",
        r'<span style="color:#93C5FD">\1</span>',
        escaped_html,
    )
    return escaped_html


def strip_uuid_prefix(filename: str) -> str:
    """Remove the 32-hex-char UUID prefix from a filename, if present."""
    m = re.match(r"^[0-9a-f]{32}_(.+)$", filename, re.IGNORECASE)
    return m.group(1) if m else filename


def sanitize_processed_filename(filename: str) -> str:
    """Validate and sanitize a processed filename coming from a route parameter."""
    raw = filename or ""
    candidate = Path(raw).name

    if not raw or candidate in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if "/" in raw or "\\" in raw:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not SAFE_PROCESSED_FILENAME_RE.fullmatch(candidate):
        raise HTTPException(status_code=400, detail="Invalid filename")

    if Path(candidate).suffix.lower() not in ALLOWED_PROCESSED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    return candidate


def resolve_processed_file(processed_dir: Path, filename: str) -> Path:
    """Safely resolve a processed file path within the processed directory."""
    safe_name = sanitize_processed_filename(filename)
    processed_root = processed_dir.resolve()
    file_path = (processed_root / safe_name).resolve()

    if processed_root not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return file_path
