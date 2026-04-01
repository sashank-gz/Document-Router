import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app import config
from app.classifier import classify_document

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def test_tier2_override():
    print("--- Testing FORCE_TIER2_MATCH ---")

    # 1. Enable Force
    config.FORCE_TIER2_MATCH = True
    print("\n[With FORCE_TIER2_MATCH = True]")

    # Text that generates a VERY WEAK signal (e.g. just the word "acord" once)
    weak_text = "I just have one word: acord."

    res_forced, debug_forced = classify_document("test.pdf", weak_text)
    print(f"Result: {res_forced.document_type.value}, Tier: {res_forced.tier}")
    print(f"Score: {res_forced.score}, Strength: {res_forced.strength}")

    if res_forced.tier == "keyword":
        print("✅ SUCCESS: Weak match was FORCED to be accepted!")
    else:
        print("❌ FAILURE: Expected forced acceptance.")

    # 2. Disable Force
    config.FORCE_TIER2_MATCH = False
    print("\n[With FORCE_TIER2_MATCH = False]")

    res_strict, debug_strict = classify_document("test.pdf", weak_text)
    print(f"Result: {res_strict.document_type.value}, Tier: {res_strict.tier}")

    if res_strict.tier != "keyword":
        print("✅ SUCCESS: Weak match was NOT accepted (Strict Mode working).")
    else:
        print("❌ FAILURE: Expected fallback to Tier 3/Manual.")


if __name__ == "__main__":
    test_tier2_override()
