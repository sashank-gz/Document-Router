import sys
from pathlib import Path

# Add the app directory to sys.path so we can import modules
sys.path.append(str(Path(".").resolve()))

from app.media_utils import extract_and_ocr_media

print("Testing Media Utils:")
res = extract_and_ocr_media(
    Path(
        "uploads/91474db7d09f489da9f880e503409e3b_14.1 Protected_Loss_Run_Stacked_Headers_5yr_Full (1).docx"
    )
)
print(f"Result for .docx: {bool(res)} (length: {len(res)})")

res2 = extract_and_ocr_media(
    Path("uploads/72a050bbaf3a4c62a6e02f294169748d_13.2 protected_loss_run_data.xlsx")
)
print(f"Result for .xlsx: {bool(res2)} (length: {len(res2)})")
