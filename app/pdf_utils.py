import fitz
import logging
from pathlib import Path
from . import config

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
        logger.warning(f"Normalization skipped: {e}")
        
    return Path(file_path)


def analyze_pdf(file_path: Path | str) -> dict:
    """Analyze a PDF to determine its traits: Dense, Scanned, Rotated, etc."""
    result = {"is_encrypted": False, "traits": []}
    
    try:
        doc = fitz.open(str(file_path))
    except Exception as e:
        logger.error("Failed to open PDF for analysis: %e", e)
        return result
        
    if doc.needs_pass:
        result["is_encrypted"] = True
        result["traits"].append("Password Protected")
        doc.close()
        return result
        
    has_rotated = False
    total_images = 0
    total_text_len = 0
    num_pages = len(doc)
    
    for i, page in enumerate(doc):
        if page.rotation != 0:
            has_rotated = True
        total_text_len += len(page.get_text("text").strip())
        total_images += len(page.get_image_info())
            
    doc.close()
    
    traits = []
    
    avg_text = total_text_len / max(1, num_pages)
    avg_images = total_images / max(1, num_pages)
    
    is_scanned = avg_text < 50 and total_images > 0
    is_dense = avg_text > 2000

    # Handwriting heuristic: pages are image-heavy but contain very little
    # machine-extractable text — the hallmark of scanned handwritten docs.
    is_handwritten = avg_images > 2 and avg_text < 100
    
    if has_rotated:
        traits.append("Rotated")
    if is_scanned:
        traits.append("Scanned")
    if is_dense:
        traits.append("Densed")
    if is_handwritten:
        traits.append("Handwritten")
        
    # Hybrid check
    if len(traits) > 1:
        traits.append("Hybrid")
        
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
        logger.error("Unlock failed: %e", e)
    return False
