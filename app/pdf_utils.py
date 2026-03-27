"""
PDF utilities: rotation normalization, trait analysis, and password unlock.

Uses PyMuPDF (fitz) for low-level PDF inspection.
"""

import logging
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)


def normalize_pdf(file_path: Path | str) -> Path:
    """Detects rotation and prepares a sanitized PDF if needed."""
    try:
        doc = fitz.open(str(file_path))
        if doc.needs_pass:
            doc.close()
            return Path(file_path)

        needs_rewrite = False
        for page in doc:
            if page.rotation != 0:
                needs_rewrite = True

        if needs_rewrite:
            # To thoroughly bake rotation would require re-generating pages via images
            # or low-level affine transformations which break simple text layers.
            # For 100% free mode, we trust RapidOCR which is somewhat tolerant of rotation metadata.
            logger.info("Rotated pages detected. RapidOCR will attempt structure extraction.")

        doc.close()
    except Exception as e:
        logger.warning("Normalization skipped: %s", e)

    return Path(file_path)


def _classify_page(page) -> set[str]:
    """Classify a single PDF page into trait categories.

    Uses image-area coverage ratio and extractable text length to
    distinguish Digital / Scanned / Handwritten / Dense / Rotated.
    """
    traits: set[str] = set()
    text_len = len(page.get_text("text").strip())
    page_area = page.rect.get_area()

    # ── Image coverage ratio ────────────────────────────────────
    blocks = page.get_text("dict")["blocks"]
    img_blocks = [b for b in blocks if b["type"] == 1]
    img_area = sum(fitz.Rect(b["bbox"]).get_area() for b in img_blocks)
    img_coverage = img_area / page_area if page_area else 0
    img_count = len(img_blocks)

    # ── Rotation ────────────────────────────────────────────────
    if page.rotation != 0:
        traits.add("Rotated")

    # ── Handwritten (special-case of scanned) ───────────────────
    # Handwritten pages are typically a single large scan image
    # covering most of the page with virtually no extractable text.
    if text_len < 20 and img_coverage > 0.7 and img_count <= 2:
        traits.add("Handwritten")
    # ── Scanned (typed) ─────────────────────────────────────────
    elif text_len < 50 and img_coverage > 0.5:
        traits.add("Scanned")
    # ── Dense ───────────────────────────────────────────────────
    elif text_len > 2000:
        traits.add("Dense")
        traits.add("Digital")
    # ── Normal digital ──────────────────────────────────────────
    else:
        traits.add("Digital")

    return traits


def analyze_pdf(file_path: Path | str) -> dict:
    """Analyze a PDF to determine its traits using per-page classification.

    Each page is independently classified as Digital / Scanned /
    Handwritten / Dense / Rotated via image-coverage heuristics.
    If multiple base types coexist, a ``Hybrid (X + Y)`` trait is added.
    """
    result: dict = {"is_encrypted": False, "traits": []}

    try:
        doc = fitz.open(str(file_path))
    except Exception as e:
        logger.error("Failed to open PDF for analysis: %s", e)
        return result

    if doc.needs_pass:
        result["is_encrypted"] = True
        result["traits"].append("Password Protected")
        doc.close()
        return result

    # ── Per-page classification ─────────────────────────────────
    all_traits: set[str] = set()
    base_types: set[str] = set()
    BASE_CATEGORY = {"Digital", "Scanned", "Handwritten"}

    for page in doc:
        page_traits = _classify_page(page)
        all_traits |= page_traits
        base_types |= page_traits & BASE_CATEGORY

    doc.close()

    # ── Build final trait list ──────────────────────────────────
    traits = sorted(all_traits)

    # Hybrid: document contains pages of more than one base type
    if len(base_types) > 1:
        combo = " + ".join(sorted(base_types))
        traits.append(f"Hybrid ({combo})")

    result["traits"] = traits
    return result


def unlock_pdf(file_path: Path | str, password: str) -> bool:
    """Attempt to decrypt a PDF and save it unlocked."""
    try:
        doc = fitz.open(str(file_path))
        if doc.needs_pass:
            is_unlocked = doc.authenticate(password)
            if is_unlocked:
                # Save decrypted file over itself
                temp_path = str(file_path) + ".unlocked.pdf"
                doc.save(temp_path)
                doc.close()
                Path(temp_path).replace(Path(file_path))
                return True
        doc.close()
    except Exception as e:
        logger.error("Unlock failed: %s", e)
    return False
