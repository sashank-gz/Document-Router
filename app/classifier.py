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
    tier: str  # "keyword" | "llm" | "none" (filename is no longer a final tier)
    score: float = 0.0
    second_score: float = 0.0
    strength: str = "NONE"
    dominance: float = 0.0
    matched_keywords: list[str] | None = None


def _classify_by_filename(filename: str) -> str | None:
    """Tier 1 – match document type by filename keywords. (Supporting signal only)"""
    name_lower = (filename or "").lower()
    for type_name, hints in FILENAME_HINTS.items():
        if any(hint in name_lower for hint in hints):
            return type_name.upper()
    return None


def _classify_by_keywords(text: str) -> dict:
    """
    Tier 2 – compute keyword-based scoring for all document types.
    Returns: {top_class, top_score, second_score, matched_keywords}
    """

    def normalize(t: str) -> str:
        import re

        return re.sub(r"[^a-z0-9]", " ", (t or "").lower())

    text_norm = " ".join(normalize(text).split())
    scores = []

    for type_name, hints in KEYWORD_HINTS.items():
        if not hints:
            continue

        matched = []
        for hint in hints:
            hint_norm = " ".join(normalize(hint).split())
            if hint_norm and hint_norm in text_norm:
                matched.append(hint)

        score = len(matched) / len(hints)

        scores.append({"type": type_name, "score": round(score, 4), "matched": matched})

    # Sort by score descending
    scores.sort(key=lambda x: x["score"], reverse=True)

    top_result = scores[0] if scores else {"type": "UNKNOWN", "score": 0.0, "matched": []}
    second_score = scores[1]["score"] if len(scores) > 1 else 0.0

    return {
        "top_class": top_result["type"],
        "top_score": top_result["score"],
        "second_score": second_score,
        "matched_keywords": top_result["matched"],
    }


def classify_document(
    filename: str,
    keyword_text: str,
    llm_text: str | None = None,
) -> tuple[ClassificationResult, dict]:
    """
    Run the 3-tier classification pipeline.
    Tier 2 (Keywords) is primary. Tier 3 (LLM) is used for ambiguity/conflict.
    Tier 1 (Filename) is supporting/debug only.
    """
    from . import config

    debug: dict = {}
    if config.DEBUG_MODE:
        debug["tier_2_text_input"] = keyword_text[:1000] if keyword_text else ""
        debug["tier_3_text_input"] = llm_text[:2000] if llm_text else None

    # 1. Evaluate Tier 1 (Filename) - Supporting info only
    t1_type = _classify_by_filename(filename)
    debug["tier_1_type"] = t1_type

    # 2. Evaluate Tier 2 (Keywords) - Primary decision signal
    t2_data = _classify_by_keywords(keyword_text)

    top_class = t2_data["top_class"]
    top_score = t2_data["top_score"]
    second_score = t2_data["second_score"]

    # 3. Calculate Strength + Dominance
    if top_score >= config.TIER2_STRONG_THRESHOLD:
        strength = "STRONG"
    elif top_score >= config.TIER2_WEAK_THRESHOLD:
        strength = "WEAK"
    else:
        strength = "NONE"

    dominance = top_score / max(second_score, 0.01)

    debug.update(
        {
            "tier_2_top_class": top_class,
            "tier_2_top_score": top_score,
            "tier_2_second_score": second_score,
            "tier_2_strength": strength,
            "tier_2_dominance": round(dominance, 2),
            "tier_2_matched": t2_data["matched_keywords"],
        }
    )

    result: ClassificationResult | None = None

    # 4. Decision Logic
    is_safe_match = strength == "STRONG" and dominance >= config.TIER2_DOMINANCE_THRESHOLD
    is_forced_match = config.FORCE_TIER2_MATCH and top_score > 0

    if is_safe_match or is_forced_match:
        try:
            final_tier = "both" if (t1_type and t1_type == top_class) else "keyword"
            doc_type = DocumentType[top_class]
            result = ClassificationResult(
                document_type=doc_type,
                pipeline=get_pipeline(doc_type),
                tier=final_tier,
                score=top_score,
                second_score=second_score,
                strength=strength,
                dominance=dominance,
                matched_keywords=t2_data["matched_keywords"],
            )
            mode = "FORCED" if not is_safe_match else "SAFE"
            logger.info(
                "Tier 2 match ACCEPTED [%s]: %s (Score: %s, Dom: %s)",
                mode,
                top_class,
                top_score,
                round(dominance, 2),
            )
        except (KeyError, ValueError):
            logger.warning("Invalid document type from keywords: %s", top_class)

    if not result:
        reason = "ambiguous" if strength == "STRONG" else "weak_signal"
        logger.info("Tier 2 signal %s (%s). Triggering Tier 3 (LLM).", reason, strength)
        debug["tier_2_decision"] = f"CALL_TIER3_{reason.upper()}"

    # 5. Tier 3 (LLM) - Only if needed
    if not result:
        llm_text_normalized = " ".join((llm_text or "").split())
        llm_text_length = len(llm_text_normalized)
        llm_can_run = llm_text_length >= config.LLM_MIN_TEXT_CHARS

        if llm_text_normalized and llm_can_run:
            try:
                from .llm_classifier import classify_with_llm

                llm_res, llm_debug = classify_with_llm(llm_text_normalized)

                if config.DEBUG_MODE:
                    debug["tier_3_llm"] = llm_debug

                if llm_res:
                    logger.info("Tier 3 (LLM) resolution: %s", llm_res.document_type.value)
                    # Convert to our new ClassificationResult format
                    result = ClassificationResult(
                        document_type=llm_res.document_type,
                        pipeline=llm_res.pipeline,
                        tier="llm",
                        score=1.0,  # LLM result is considered high confidence if it returns
                        strength="STRONG",
                    )
            except Exception:
                logger.exception("Tier 3 (LLM) failed")
                if config.DEBUG_MODE:
                    debug["tier_3_error"] = "LLM failed"
        else:
            debug["tier_3_skipped"] = f"text_too_short:{llm_text_length}"

    # 6. Final Fallback
    if not result:
        logger.info("Classification failed or Tier 2 weak. No LLM fallback available.")
        result = ClassificationResult(
            document_type=DocumentType.UNKNOWN,
            pipeline=Pipeline.MANUAL,
            tier="none",
            score=top_score,
            strength=strength,
        )

    if config.DEBUG_MODE:
        debug["final_result"] = result.document_type.value
        debug["final_tier"] = result.tier

    return result, debug
