"""
Document type definitions and route mapping.

Loads all document types and pipeline routes from the config/ folder:
  - config/routes.txt          → document type → pipeline mapping
  - config/filename_hints/*.txt → loaded by classifier.py
  - config/keyword_hints/*.txt  → loaded by classifier.py
  - config/prompt.txt          → loaded by llm_classifier.py
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _read_lines(file_path: Path) -> list[str]:
    """Read a text file and return non-empty, non-comment lines."""
    lines: list[str] = []
    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                lines.append(line)
    return lines


def _load_routes() -> dict[str, str]:
    """Parse config/routes.txt → {TYPE_NAME: PIPELINE}."""
    routes: dict[str, str] = {}
    routes_file = CONFIG_DIR / "routes.txt"
    for line in _read_lines(routes_file):
        if "=" in line:
            type_name, pipeline = line.split("=", 1)
            routes[type_name.strip().upper()] = pipeline.strip().upper()
    return routes


def _load_hints(folder_name: str) -> dict[str, list[str]]:
    """Load all .txt files from a hints folder → {TYPE_NAME: [hints]}."""
    hints: dict[str, list[str]] = {}
    hints_dir = CONFIG_DIR / folder_name
    if not hints_dir.exists():
        return hints
    for txt_file in sorted(hints_dir.glob("*.txt")):
        type_name = txt_file.stem.upper()
        hints[type_name] = _read_lines(txt_file)
    return hints


def _load_prompt() -> str:
    """Load the LLM system prompt from config/prompt.txt."""
    prompt_file = CONFIG_DIR / "prompt.txt"
    return "\n".join(_read_lines(prompt_file))


def _load_settings() -> dict[str, str]:
    """Load key-value settings from config/settings.txt."""
    settings: dict[str, str] = {}
    settings_file = CONFIG_DIR / "settings.txt"
    if not settings_file.exists():
        return settings

    for line in _read_lines(settings_file):
        if "=" in line:
            key, val = line.split("=", 1)
            settings[key.strip().upper()] = val.strip()
    return settings


# ── Pipeline enum ────────────────────────────────────────────────────


class Pipeline(str, Enum):
    """Available extraction pipelines."""

    OCR = "OCR"
    LLM = "LLM"
    MANUAL = "MANUAL"


# ── Load everything from config/ at import time ─────────────────────

_routes = _load_routes()

# Build document types dynamically from routes.txt
_type_names = {name: name for name in _routes}
_type_names["UNKNOWN"] = "UNKNOWN"

DocumentType = Enum("DocumentType", {k: k for k in _type_names}, type=str)  # type: ignore[misc]

# Build route map
ROUTE_MAP: dict = {}
for name, pipeline_str in _routes.items():
    ROUTE_MAP[DocumentType[name]] = Pipeline(pipeline_str)
ROUTE_MAP[DocumentType["UNKNOWN"]] = Pipeline.MANUAL

# Pre-load hints, prompt, settings, and descriptions
FILENAME_HINTS: dict[str, list[str]] = _load_hints("filename_hints")
KEYWORD_HINTS: dict[str, list[str]] = _load_hints("keyword_hints")
TYPE_DESCRIPTIONS: dict[str, str] = {
    txt_file.stem.upper(): txt_file.read_text(encoding="utf-8").strip()
    for txt_file in (CONFIG_DIR / "descriptions").glob("*.txt")
}
SYSTEM_PROMPT_TEXT: str = _load_prompt()
SETTINGS: dict[str, str] = _load_settings()

logger.info(
    "Config loaded: %d types, %d filename hints, %d keyword hints, %d descriptions, %d settings",
    len(_routes), len(FILENAME_HINTS), len(KEYWORD_HINTS), len(TYPE_DESCRIPTIONS), len(SETTINGS)
)


# ── Public helpers ───────────────────────────────────────────────────


def get_pipeline(document_type) -> Pipeline:
    """Look up the pipeline for a given document type."""
    return ROUTE_MAP.get(document_type, Pipeline.MANUAL)


def get_valid_types() -> list[str]:
    """Return all valid document type names (excluding UNKNOWN)."""
    return [dt.value for dt in DocumentType if dt.value != "UNKNOWN"]
