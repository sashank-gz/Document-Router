import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.classifier import classify_document
from app.document_types import KEYWORD_HINTS, DocumentType

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def test_loss_run_matching():
    print("--- Testing Loss Run Matching with new Thresholds ---")

    # Simulating what we saw in the screenshot
    text_from_screenshot = """
    Loss Run - With Claimant
    Run As Of: 09/01/3024
    Insured Name: Gpt 40 mini
    Policy Number: ABC123
    Effective Date: 10/31/3020
    Claim Number   Policy Number   Loss Date   Claimant   Claim Description   Paid Loss   Total Paid
    01000225       ABC1223         04/20/3020  Ajith Kumar  claim description    $56.00      $56.00
    Totals:        $56.00
    """

    res, debug = classify_document("test.pdf", text_from_screenshot)

    print(
        f"Top: {debug['tier_2_top_class']}, Score: {debug['tier_2_top_score']}, Strength: {debug['tier_2_strength']}"
    )
    print(f"Final: {res.document_type.value}, Tier: {res.tier}")
    print(f"Matched: {len(debug['tier_2_matched'])} / {len(KEYWORD_HINTS['LOSS_RUN'])}")

    if res.tier == "keyword" and res.document_type == DocumentType.LOSS_RUN:
        print("✅ SUCCESS: Loss Run identified at Tier 2!")
    else:
        print(f"❌ FAILURE: Tier is {res.tier}, DocType is {res.document_type}")


if __name__ == "__main__":
    test_loss_run_matching()
