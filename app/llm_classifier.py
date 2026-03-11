"""
Tier 3 – LLM-based document classification.

Sends extracted text to a free LLM (Groq or Gemini, controlled by env flags)
and asks it to classify the document into one of the known types.

Provider priority:
    1. Groq  (if GROQ_ENABLED=true and GROQ_API_KEY is set)
    2. Gemini (if GEMINI_ENABLED=true and GEMINI_API_KEY is set)
    3. None   → returns None so the orchestrator falls through to MANUAL
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from . import config
from .document_types import DocumentType, Pipeline, SYSTEM_PROMPT_TEXT, get_pipeline, get_valid_types

logger = logging.getLogger(__name__)


# ── Load LLM settings ───────────────────────────────────────────────

_VALID_TYPES = get_valid_types()
_MAX_TEXT_CHARS = int(config.LLM_MAX_TEXT_CHARS)
_TEMPERATURE = float(config.LLM_TEMPERATURE)
_MAX_TOKENS = int(config.LLM_MAX_TOKENS)

# Build the full system prompt: user-editable part + auto-generated type list
SYSTEM_PROMPT = (
    f"{SYSTEM_PROMPT_TEXT}\n"
    f"Allowed types: {', '.join(_VALID_TYPES)}.\n"
    'Format: {"document_type": "<TYPE>", "confidence": <0.0-1.0>}'
)


def _build_user_prompt(text: str) -> str:
    """Build the user message containing the document text to classify."""
    truncated = text[:_MAX_TEXT_CHARS]
    return (
        "Classify the following document text into one of these types: "
        f"{', '.join(_VALID_TYPES)}.\n\n"
        "--- DOCUMENT TEXT START ---\n"
        f"{truncated}\n"
        "--- DOCUMENT TEXT END ---\n\n"
        'Respond ONLY with JSON: {"document_type": "<TYPE>", "confidence": <0.0-1.0>}'
    )


# ── Response parsing ─────────────────────────────────────────────────


def _parse_llm_response(raw: str) -> Optional[dict]:
    """
    Extract {"document_type": "...", "confidence": ...} from the LLM response.

    Handles cases where the LLM wraps JSON in markdown fences or extra text.
    """
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks or inline braces
    match = re.search(r"\{[^{}]*\"document_type\"[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM classification response: %s", raw[:200])
    return None


# ── Provider calls ───────────────────────────────────────────────────


def _call_groq(user_prompt: str) -> Optional[str]:
    """Call Groq chat completions API."""
    from groq import Groq

    client = Groq(api_key=config.GROQ_API_KEY)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS,
    )
    return response.choices[0].message.content


def _call_gemini(user_prompt: str) -> Optional[str]:
    """Call Google Gemini generateContent API."""
    import google.generativeai as genai

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)
    response = model.generate_content(
        f"{SYSTEM_PROMPT}\n\n{user_prompt}",
        generation_config={"temperature": _TEMPERATURE, "max_output_tokens": _MAX_TOKENS},
    )
    return response.text


# ── Public entry point ───────────────────────────────────────────────


def classify_with_llm(text: str) -> tuple[Optional["ClassificationResult"], dict]:
    """
    Classify document text using the configured LLM provider.

    Returns (ClassificationResult | None, debug_info).
    """
    from .classifier import ClassificationResult  # avoid circular import

    user_prompt = _build_user_prompt(text)
    raw_response: Optional[str] = None
    debug: dict = {}
    provider_used: Optional[str] = None

    # Try Groq first
    if config.GROQ_ENABLED and config.GROQ_API_KEY:
        try:
            logger.info("Tier 3: calling Groq (%s) for classification", config.GROQ_MODEL)
            raw_response = _call_groq(user_prompt)
            provider_used = f"groq ({config.GROQ_MODEL})"
        except Exception as exc:
            logger.exception("Groq classification call failed")
            debug["groq_error"] = str(exc)

    # Fallback to Gemini
    if raw_response is None and config.GEMINI_ENABLED and config.GEMINI_API_KEY:
        try:
            logger.info("Tier 3: calling Gemini (%s) for classification", config.GEMINI_MODEL)
            raw_response = _call_gemini(user_prompt)
            provider_used = f"gemini ({config.GEMINI_MODEL})"
        except Exception as exc:
            logger.exception("Gemini classification call failed")
            debug["gemini_error"] = str(exc)

    if config.DEBUG_MODE:
        debug["provider_used"] = provider_used
        debug["prompt_sent"] = user_prompt[:500] + "..." if len(user_prompt) > 500 else user_prompt
        debug["raw_llm_response"] = raw_response

    if raw_response is None:
        if not (config.GROQ_ENABLED or config.GEMINI_ENABLED):
            logger.info("Tier 3 skipped — no LLM provider enabled")
            debug["status"] = "skipped — no provider enabled"
        else:
            debug["status"] = "failed — no response from any provider"
        return None, debug

    parsed = _parse_llm_response(raw_response)
    if config.DEBUG_MODE:
        debug["parsed_response"] = parsed

    if not parsed:
        debug["status"] = "failed — could not parse LLM response"
        return None, debug

    doc_type_str = parsed.get("document_type", "").upper()
    confidence = float(parsed.get("confidence", 0.0))

    # Validate against our enum
    try:
        doc_type = DocumentType(doc_type_str)
    except ValueError:
        logger.warning("LLM returned unknown document type: %s", doc_type_str)
        debug["status"] = f"failed — unknown type: {doc_type_str}"
        return None, debug

    if doc_type == DocumentType.UNKNOWN:
        debug["status"] = "LLM returned UNKNOWN"
        return None, debug

    debug["status"] = "success"
    return ClassificationResult(
        document_type=doc_type,
        pipeline=get_pipeline(doc_type),
        tier="llm",
        confidence=confidence,
    ), debug

