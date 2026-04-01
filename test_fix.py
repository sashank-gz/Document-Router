import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.classifier import ClassificationResult, classify_document
from app.document_types import DocumentType, Pipeline

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")


def test_llm_fallback_fix():
    print("--- Testing LLM Fallback Fix ---")

    # 1. Setup a weak signal that triggers Tier 3
    text_weak = "reserve amount"  # matches 1/12 for LOSS_RUN -> 0.0833
    long_llm_text = (
        " This is a very long text that should pass the minimum character count of 180 characters. "
        * 3
    )
    print(f"LLM text length: {len(long_llm_text)}")

    # 2. Mock classify_with_llm to return a valid result with the new format
    import app.llm_classifier

    # New format result
    mock_llm_res = ClassificationResult(
        document_type=DocumentType.LOSS_RUN, pipeline=Pipeline.OCR, tier="llm", score=0.95
    )

    # Use patch-like mocking
    original_classify = app.llm_classifier.classify_with_llm
    app.llm_classifier.classify_with_llm = MagicMock(
        return_value=(mock_llm_res, {"status": "success"})
    )

    try:
        from app import config

        old_min = config.LLM_MIN_TEXT_CHARS
        config.LLM_MIN_TEXT_CHARS = 10  # Temporarily override config

        res, debug = classify_document("report.pdf", text_weak, llm_text=long_llm_text)
        print(f"Result: {res.document_type.value}, Tier: {res.tier}, Score: {res.score}")

        if res.tier != "llm":
            print(f"FAILED: Tier is {res.tier}, expected 'llm'")
            print(f"Debug info: {debug}")
            sys.exit(1)

        print("✅ LLM Fallback fixed and working!")
    finally:
        config.LLM_MIN_TEXT_CHARS = old_min
        app.llm_classifier.classify_with_llm = original_classify


if __name__ == "__main__":
    test_llm_fallback_fix()
