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
CLASSIFICATION_MAX_PAGES: int = int(os.getenv("CLASSIFICATION_MAX_PAGES", "3"))
DEBUG_MODE: bool = _env_bool("DEBUG_MODE")

# ── LLM tuning parameters ───────────────────────────────────────────
LLM_MAX_TEXT_CHARS: int = int(os.getenv("LLM_MAX_TEXT_CHARS", "4000"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "150"))

# ── Pipeline endpoints ───────────────────────────────────────────────
PIPELINE_DRY_RUN: bool = _env_bool("PIPELINE_DRY_RUN")
OCR_ENDPOINT: str = os.getenv("OCR_ENDPOINT", "http://ocr-service/process")
LLM_ENDPOINT: str = os.getenv("LLM_ENDPOINT", "http://llm-service/process")
PIPELINE_TIMEOUT: int = int(os.getenv("PIPELINE_TIMEOUT", "30"))

