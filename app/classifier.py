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

from .document_types import (
    FILENAME_HINTS,
    KEYWORD_HINTS,
    DocumentType,
    Pipeline,
    get_pipeline,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    document_type: DocumentType
    pipeline: Pipeline
    tier: str  # which tier produced the result: "filename" | "keyword" | "llm"
    confidence: float = 1.0


def _classify_by_filename(filename: str) -> ClassificationResult | None:
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


def _classify_by_keywords(text: str) -> ClassificationResult | None:
    """Tier 2 – match document type by text keywords. Normalizes whitespace."""
    text_lower = " ".join((text or "").lower().split())
    for type_name, hints in KEYWORD_HINTS.items():
        if any(hint in text_lower for hint in hints):
            doc_type = DocumentType[type_name]
            return ClassificationResult(
                document_type=doc_type,
                pipeline=get_pipeline(doc_type),
                tier="keyword",
            )
    return None


def _resolve_classification(
    t1_result: ClassificationResult | None,
    t2_result: ClassificationResult | None,
    debug: dict,
) -> tuple[ClassificationResult | None, bool]:
    """Resolve conflicts between Tier 1 (Filename) and Tier 2 (Keywords)."""
    # Case A: Both match
    if t1_result and t2_result:
        if t1_result.document_type == t2_result.document_type:
            logger.info("Tiers 1 & 2 agree: %s", t1_result.document_type.value)
            t2_result.tier = "both"
            return t2_result, False
        else:
            logger.warning(
                "CONFLICT: Filename says %s, Keywords say %s. Triggering Tie-breaker (Tier 3).",
                t1_result.document_type.value,
                t2_result.document_type.value,
            )
            debug["conflict_detected"] = {
                "tier_1": t1_result.document_type.value,
                "tier_2": t2_result.document_type.value,
            }
            return None, True

    # Case B: Only Tier 2 matches
    if t2_result:
        logger.info("Tier 2 match: %s", t2_result.document_type.value)
        return t2_result, False

    # Case C: Only Tier 1 matches
    # Final decision is deferred to classify_document(), which may use Tier 3 first
    # and then fall back to Tier 1 if no stronger signal is available.
    if t1_result:
        logger.info(
            "Tier 1 match (%s) but Tier 2 failed. Deferring to Tier 3.",
            t1_result.document_type.value,
        )

    return None, False


def classify_document(
    filename: str,
    keyword_text: str,
    llm_text: str | None = None,
) -> tuple[ClassificationResult, dict]:
    """
    Run the 3-tier classification pipeline with conflict resolution.
    """
    from . import config

    debug: dict = {}
    if config.DEBUG_MODE:
        debug["tier_2_text_input"] = keyword_text[:2000] if keyword_text else ""
        debug["tier_3_text_input"] = llm_text[:4000] if llm_text else None

    # 1. Evaluate Tier 1 (Filename)
    t1_result = _classify_by_filename(filename)
    if t1_result:
        t1_result.confidence = config.CONFIDENCE_FILENAME

    # 2. Evaluate Tier 2 (Keywords)
    t2_result = _classify_by_keywords(keyword_text)
    if t2_result:
        t2_result.confidence = config.CONFIDENCE_KEYWORD

    # 3. Decision Logic
    result, is_conflict = _resolve_classification(t1_result, t2_result, debug)

    llm_text_normalized = " ".join((llm_text or "").split())
    llm_text_length = len(llm_text_normalized)
    llm_can_run = llm_text_length >= config.LLM_MIN_TEXT_CHARS
    tier1_only_case = bool(t1_result and not t2_result and not is_conflict)

    # 4. Tier 3 (LLM) - Tie-breaker OR Fallback
    if (not result or is_conflict) and llm_text_normalized and llm_can_run and not tier1_only_case:
        try:
            from .llm_classifier import classify_with_llm

            llm_result, llm_debug = classify_with_llm(llm_text_normalized)
            if config.DEBUG_MODE:
                debug["tier_3_llm"] = llm_debug
            if llm_result:
                logger.info("Tier 3 (LLM) resolution: %s", llm_result.document_type.value)
                result = llm_result
        except Exception:
            logger.exception("Tier 3 (LLM) tie-breaker failed")
            if config.DEBUG_MODE:
                debug["tier_3_error"] = "LLM failed"
    elif (not result or is_conflict) and llm_text_normalized and config.DEBUG_MODE:
        if tier1_only_case:
            debug["tier_3_skipped_reason"] = "tier1_only_preferred"
        else:
            debug["tier_3_skipped_reason"] = (
                f"insufficient_text:{llm_text_length}<{config.LLM_MIN_TEXT_CHARS}"
            )

    # 5. Tier 1 safety fallback when Tier 2 is missing and Tier 3 is unavailable/inconclusive
    if not result and t1_result and not t2_result:
        logger.info(
            "Tier 3 unavailable or inconclusive; falling back to Tier 1: %s",
            t1_result.document_type.value,
        )
        result = t1_result

    # 6. Final Fallback
    if not result:
        logger.info("No classification tier matched: %s → MANUAL", filename)
        result = ClassificationResult(
            document_type=DocumentType.UNKNOWN,
            pipeline=Pipeline.MANUAL,
            tier="none",
            confidence=0.0,
        )

    # Populate final debug info
    if config.DEBUG_MODE:
        debug.update(
            {
                "tier_1_result": t1_result.document_type.value if t1_result else None,
                "tier_2_result": t2_result.document_type.value if t2_result else None,
                "final_result": result.document_type.value,
            }
        )

    return result, debug
