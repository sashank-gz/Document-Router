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
    """Tier 2 – match document type by text keywords. Normalizes whitespace so phrases match across line breaks."""
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


# ── Orchestrator ─────────────────────────────────────────────────────


def classify_document(
    filename: str,
    keyword_text: str,
    llm_text: Optional[str] = None,
) -> tuple[ClassificationResult, dict]:
    """
    Run the 3-tier classification pipeline with conflict resolution.

    - Tier 1 (Filename) and Tier 2 (Keywords) are evaluated together.
    - If they disagree, Tier 3 (LLM) acts as the tie-breaker.
    - Confidence scores are weighted based on config/settings.txt.
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
    result: Optional[ClassificationResult] = None
    is_conflict = False

    # Case A: Both match
    if t1_result and t2_result:
        if t1_result.document_type == t2_result.document_type:
            logger.info("Tiers 1 & 2 agree: %s", t1_result.document_type.value)
            result = t2_result  # Higher confidence/Keyword match wins
            result.tier = "both"
        else:
            logger.warning(
                "CONFLICT: Filename says %s, Keywords say %s. Triggering Tie-breaker (Tier 3).",
                t1_result.document_type.value,
                t2_result.document_type.value
            )
            is_conflict = True
            debug["conflict_detected"] = {
                "tier_1": t1_result.document_type.value,
                "tier_2": t2_result.document_type.value,
            }

    # Case B: Only Tier 2 matches
    elif t2_result:
        result = t2_result
        logger.info("Tier 2 match: %s", result.document_type.value)

    # Case C: Only Tier 1 matches (Now ignored as a standalone classifier)
    elif t1_result:
        logger.info(
            "Tier 1 match (%s) but Tier 2 failed. Ignoring T1 and falling back to Tier 3.",
            t1_result.document_type.value
        )

    # 4. Tier 3 (LLM) - Tie-breaker OR Fallback
    # Triggered if: a) No match yet  b) Conflict detected between T1 and T2
    if (not result or is_conflict) and llm_text and llm_text.strip():
        try:
            from .llm_classifier import classify_with_llm
            llm_result, llm_debug = classify_with_llm(llm_text)
            
            if config.DEBUG_MODE:
                debug["tier_3_llm"] = llm_debug
            
            if llm_result:
                logger.info("Tier 3 (LLM) resolution: %s", llm_result.document_type.value)
                result = llm_result
        except Exception:
            logger.exception("Tier 3 (LLM) tie-breaker failed")
            if config.DEBUG_MODE:
                debug["tier_3_error"] = "LLM failed"

    # 5. Final Fallback
    if not result:
        logger.info("No classification tier matched: %s → MANUAL", filename)
        result = ClassificationResult(
            document_type=DocumentType.UNKNOWN,
            pipeline=Pipeline.MANUAL,
            tier="none",
            confidence=0.0,
        )

    # Populate debug info
    if config.DEBUG_MODE:
        debug["tier_1_result"] = t1_result.document_type.value if t1_result else None
        debug["tier_2_result"] = t2_result.document_type.value if t2_result else None
        debug["final_result"] = result.document_type.value

    return result, debug

