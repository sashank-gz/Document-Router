"""
Utilities to extract embedded media from structured archives (like .docx, .xlsx, .pptx)
and inline images from emails, processing them through OCR to augment the textual payload.
"""

import logging
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Valid image extensions to try OCR on
VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp", ".gif"}


def extract_and_ocr_media(file_path: Path) -> str:
    """
    Given a path to a supported document archive (e.g., .xlsx, .docx, .pptx, .xlsm),
    extract any embedded images and run them through OCR.

    Returns:
        A combined markdown string of all transcripts.
    """

    # Simple check: If it's not a ZIP archive underneath, this will safely return "".
    # By Microsoft OOXML specification, docx, xlsx, pptx are zip files.
    if not zipfile.is_zipfile(file_path):
        return ""

    ocr_results = []

    try:
        from .file_service import extract_handwritten_text

        with zipfile.ZipFile(file_path, "r") as zf:
            # Search for typical media folders: word/media/, xl/media/, ppt/media/
            media_files = [
                name
                for name in zf.namelist()
                if ("media/" in name.lower()) and Path(name).suffix.lower() in VALID_IMAGE_EXTS
            ]

            if media_files:
                # We have media files! Let's extract and process them temporarily.
                with tempfile.TemporaryDirectory() as tmpdir:
                    for m_name in media_files:
                        extracted_path = Path(zf.extract(m_name, tmpdir))
                        try:
                            # Run OCR (EasyOCR backend is robust against screenshots/charts)
                            text = extract_handwritten_text(extracted_path)
                            if text and text.strip():
                                ocr_results.append(
                                    f"### Embedded Media: {Path(m_name).name}\n\n{text.strip()}"
                                )
                        except Exception as e:
                            logger.error("Failed to OCR embedded media %s: %s", m_name, e)
                        finally:
                            # Proactive memory cleanup inside the loop
                            import gc

                            gc.collect()

    except Exception as e:
        logger.warning("Media extraction skipped for %s: %s", file_path.name, e)

    if ocr_results:
        return "\n\n---\n## Embedded Media Content (OCR)\n\n" + "\n\n".join(ocr_results)

    return ""


def ocr_email_attachments(attachments: list[Path]) -> str:
    """
    Given a list of paths to email attachments, OCR any images inline.
    """
    ocr_results = []

    try:
        from .file_service import extract_handwritten_text

        for att in attachments:
            if att.suffix.lower() in VALID_IMAGE_EXTS:
                try:
                    text = extract_handwritten_text(att)
                    if text and text.strip():
                        ocr_results.append(f"### Image Attachment: {att.name}\n\n{text.strip()}")
                except Exception as e:
                    logger.error("Failed to OCR attachment %s: %s", att.name, e)
                finally:
                    import gc

                    gc.collect()
    except Exception as e:
        logger.warning("Attachment inline OCR failed: %s", e)

    if ocr_results:
        return "\n\n---\n## Image Attachments (OCR)\n\n" + "\n\n".join(ocr_results)
    return ""
