"""
Three-tier document classifier.

Tier 1: Filename-based keyword matching (instant, free)
Tier 2: First-page text keyword matching (instant, free)
Tier 3: LLM-based classification using Groq / Gemini (slower, needs API key)

Each tier returns a ClassificationResult or None.
The first non-None result wins.  If all tiers fail → MANUAL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .document_types import (
    DocumentType, FILENAME_HINTS, KEYWORD_HINTS, Pipeline, get_pipeline,
)

logger = logging.getLogger(__name__)


# ── Classification result ────────────────────────────────────────────


@dataclass
class ClassificationResult:
    document_type: DocumentType
    pipeline: Pipeline
    tier: str  # which tier produced the result: "filename" | "keyword" | "llm"
    confidence: float = 1.0


# ── Tier 1: Filename hints ───────────────────────────────────────────


def _classify_by_filename(filename: str) -> Optional[ClassificationResult]:
    """Tier 1 – match document type by filename keywords."""
    name_lower = (filename or "").lower()
    for type_name, hints in FILENAME_HINTS.items():
        if any(hint in name_lower for hint in hints):
            doc_type = DocumentType[type_name]
            return ClassificationResult(
                document_type=doc_type,
                pipeline=get_pipeline(doc_type),
                tier="filename",
            )
    return None


# ── Tier 2: First-page text keyword hints ────────────────────────────


def _classify_by_keywords(text: str) -> Optional[ClassificationResult]:
    """Tier 2 – match document type by first-page text keywords."""
    text_lower = (text or "").lower()
    for type_name, hints in KEYWORD_HINTS.items():
        if any(hint in text_lower for hint in hints):
            doc_type = DocumentType[type_name]
            return ClassificationResult(
                document_type=doc_type,
                pipeline=get_pipeline(doc_type),
                tier="keyword",
            )
    return None


# ── Orchestrator ─────────────────────────────────────────────────────


def classify_document(
    filename: str,
    first_page_text: str,
    multi_page_text: Optional[str] = None,
) -> tuple[ClassificationResult, dict]:
    """
    Run the 3-tier classification pipeline and return the first match.

    Returns
    -------
    (ClassificationResult, debug_info)
        debug_info is populated only when DEBUG_MODE is enabled.
    """
    from . import config

    debug: dict = {}

    if config.DEBUG_MODE:
        debug["extracted_text_page_1"] = first_page_text[:2000] if first_page_text else ""
        debug["extracted_text_multi_page"] = multi_page_text[:4000] if multi_page_text else None

    # Tier 1 — filename
    result = _classify_by_filename(filename)
    if config.DEBUG_MODE:
        debug["tier_1_filename"] = {
            "checked": filename,
            "result": result.document_type.value if result else None,
        }
    if result:
        logger.info("Tier 1 (filename) matched: %s → %s", filename, result.document_type.value)
        if config.DEBUG_MODE:
            debug["tier_2_keyword"] = "skipped (matched at tier 1)"
            debug["tier_3_llm"] = "skipped (matched at tier 1)"
        return result, debug

    # Tier 2 — keyword
    result = _classify_by_keywords(first_page_text)
    if config.DEBUG_MODE:
        debug["tier_2_keyword"] = {
            "text_length": len(first_page_text) if first_page_text else 0,
            "result": result.document_type.value if result else None,
        }
    if result:
        logger.info("Tier 2 (keyword) matched: %s → %s", filename, result.document_type.value)
        if config.DEBUG_MODE:
            debug["tier_3_llm"] = "skipped (matched at tier 2)"
        return result, debug

    # Tier 3 — LLM (lazy import to avoid loading heavy deps unless needed)
    llm_text = multi_page_text or first_page_text
    if llm_text and llm_text.strip():
        try:
            from .llm_classifier import classify_with_llm

            result, llm_debug = classify_with_llm(llm_text)
            if config.DEBUG_MODE:
                debug["tier_3_llm"] = llm_debug
            if result:
                logger.info("Tier 3 (LLM) matched: %s → %s", filename, result.document_type.value)
                return result, debug
        except Exception:
            logger.exception("Tier 3 (LLM) classification failed for %s — falling back to MANUAL", filename)
            if config.DEBUG_MODE:
                debug["tier_3_llm"] = {"error": "LLM call failed — see server logs"}

    elif config.DEBUG_MODE:
        debug["tier_3_llm"] = "skipped (no text to send)"

    # No tier matched
    logger.info("No classification tier matched: %s → MANUAL", filename)
    return ClassificationResult(
        document_type=DocumentType.UNKNOWN,
        pipeline=Pipeline.MANUAL,
        tier="none",
        confidence=0.0,
    ), debug

