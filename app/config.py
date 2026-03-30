"""
Centralized application configuration loaded from environment variables.

Provider flags control which LLM is used for Tier-3 classification:
    GROQ_ENABLED=true   + GROQ_API_KEY=...   → uses Groq
    GEMINI_ENABLED=true  + GEMINI_API_KEY=... → uses Gemini

If both are enabled, Groq is tried first; Gemini is the fallback.
If neither is enabled, Tier-3 (LLM classification) is skipped entirely.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)


def _env_bool(key: str, default: bool = False) -> bool:
    """Read an env var as a boolean (true/1/yes → True)."""
    value = os.getenv(key, "").strip().lower()
    if not value:
        return default
    return value in ("true", "1", "yes")


# ── LLM provider flags ──────────────────────────────────────────────
GROQ_ENABLED: bool = _env_bool("GROQ_ENABLED")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

GEMINI_ENABLED: bool = _env_bool("GEMINI_ENABLED")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Classification settings ─────────────────────────────────────────
from .document_types import SETTINGS


def _get_setting(key: str, default: str) -> str:
    """Get a value from settings.txt, fall back to default."""
    return SETTINGS.get(key.upper(), default)


# Number of pages to scan (Customizable in settings.txt)
KEYWORD_SCAN_MAX_PAGES: int = int(_get_setting("KEYWORD_SCAN_MAX_PAGES", "3"))
CLASSIFICATION_MAX_PAGES: int = int(_get_setting("LLM_SCAN_MAX_PAGES", "3"))

# Confidence scores (Customizable in settings.txt)
CONFIDENCE_FILENAME: float = float(_get_setting("CONFIDENCE_FILENAME", "0.7"))
CONFIDENCE_KEYWORD: float = float(_get_setting("CONFIDENCE_KEYWORD", "0.9"))

DEBUG_MODE: bool = _env_bool("DEBUG_MODE")

# ── LLM tuning parameters (Customizable in settings.txt) ────────────
LLM_MAX_TEXT_CHARS: int = int(_get_setting("LLM_MAX_TEXT_CHARS", "4000"))
LLM_TEMPERATURE: float = float(_get_setting("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS: int = int(_get_setting("LLM_MAX_TOKENS", "150"))

# ── Pipeline endpoints ───────────────────────────────────────────────
PIPELINE_DRY_RUN: bool = _env_bool("PIPELINE_DRY_RUN")
OCR_ENDPOINT: str = os.getenv("OCR_ENDPOINT", "http://ocr-service/process")
LLM_ENDPOINT: str = os.getenv("LLM_ENDPOINT", "http://llm-service/process")
OCR_UI_URL: str = os.getenv("OCR_UI_URL", "http://localhost:3001")
LLM_UI_URL: str = os.getenv("LLM_UI_URL", "http://localhost:8080")

# Custom timeout (Customizable in settings.txt)
PIPELINE_TIMEOUT: int = int(_get_setting("PIPELINE_TIMEOUT", "30"))


# ── Extraction Storage Formats ──────────────────────────────────────
def _setting_bool(key: str, default: str = "false") -> bool:
    """Read a boolean from settings.txt, overridable by env var."""
    settings_val = _get_setting(key, default)
    fallback = settings_val.strip().lower() in ("true", "1", "yes")
    return _env_bool(key, fallback)


ENABLE_PDF_TRAITS: bool = _setting_bool("ENABLE_PDF_TRAITS", "true")
DOCLING_SAVE_MD: bool = _setting_bool("DOCLING_SAVE_MD", "true")
DOCLING_SAVE_JSON: bool = _setting_bool("DOCLING_SAVE_JSON", "false")
DOCLING_SAVE_HTML: bool = _setting_bool("DOCLING_SAVE_HTML", "false")

# ── Extraction & Email Routing ──────────────────────────────────────
EXTRACTION_PREVIEW_LIMIT: int = int(_get_setting("EXTRACTION_PREVIEW_LIMIT", "200"))
DOCLING_DO_OCR: bool = _setting_bool("DOCLING_DO_OCR", "true")
DOCLING_DO_TABLES: bool = _setting_bool("DOCLING_DO_TABLES", "true")
EMAIL_MAX_RECURSION_DEPTH: int = int(_get_setting("EMAIL_MAX_RECURSION_DEPTH", "2"))
