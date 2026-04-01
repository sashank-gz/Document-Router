import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.classifier import _classify_by_keywords

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def test_expanded_keywords():
    print("--- Testing Expanded Keyword Classification ---")

    test_cases = [
        {
            "expected_type": "ACORD",
            "text": "Certificate of Liability Insurance. Producer, Insured, Contact Name. ACORD 25 form. Coverage limits and additional insured included. Commercial General Liability.",
        },
        {
            "expected_type": "BINDER",
            "text": "Insurance Binder. Temporary coverage subject to terms. Binder number 12345. Binding authority signature. Effective period 30 days.",
        },
        {
            "expected_type": "POLICY",
            "text": "Common Policy Declarations. Named Insured, Policy Period, and Premium Amount. Commercial Property Coverage Part. Insuring Agreement and Policy Exclusions.",
        },
        {
            "expected_type": "QUOTE",
            "text": "Insurance Quote. Indicative proposal valid for 30 days. Estimated cost and proposed premium. This is not a binder.",
        },
        {
            "expected_type": "SOI",
            "text": "Summary of Insurance. Coverage overview and policy highlights. Limit of liability detail. Statement of insurance.",
        },
        {
            "expected_type": "SOV",
            "text": "Statement of Values. Property schedule, replacement cost value (RCV), and actual cash value. Building limit and COPE data.",
        },
    ]

    all_passed = True

    for case in test_cases:
        expected = case["expected_type"]
        text = case["text"]

        result = _classify_by_keywords(text)
        top_class = result["top_class"]
        score = result["top_score"]

        print(f"\nTesting {expected} text:")
        print(f"  -> Top Class: {top_class} (Score: {score})")
        print(f"  -> Matched Keywords: {result['matched_keywords']}")

        if top_class == expected:
            print(f"  ✅ SUCCESS: Correctly classified as {expected}")
        else:
            print(f"  ❌ FAILURE: Expected {expected}, got {top_class}")
            all_passed = False

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print("\n⚠️ SOME TESTS FAILED!")


if __name__ == "__main__":
    test_expanded_keywords()
