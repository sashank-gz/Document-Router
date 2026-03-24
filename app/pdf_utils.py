import fitz
import logging
from pathlib import Path
from . import config

logger = logging.getLogger(__name__)

def _detect_handwriting_with_vision(page: fitz.Page) -> bool:
    """Uses configured LLM Vision models to detect handwriting on a page."""
    try:
        pix = page.get_pixmap(dpi=72)
        img_bytes = pix.tobytes("png")
        
        prompt = "Analyze this document image. Does it contain any handwritten text or signature? Reply with ONLY the word YES or NO."
        
        if config.GEMINI_ENABLED and config.GEMINI_API_KEY:
            import google.generativeai as genai
            genai.configure(api_key=config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            image_part = {"mime_type": "image/png", "data": img_bytes}
            
            response = model.generate_content([prompt, image_part])
            text = response.text.strip().upper()
            return "YES" in text
            
        elif config.GROQ_ENABLED and config.GROQ_API_KEY:
            from groq import Groq
            import base64
            
            encoded = base64.b64encode(img_bytes).decode('utf-8')
            data_url = f"data:image/png;base64,{encoded}"
            
            client = Groq(api_key=config.GROQ_API_KEY)
            response = client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}}
                        ]
                    }
                ],
                temperature=0.0,
                max_tokens=10
            ) # Note: Vision model limit
            text = response.choices[0].message.content.strip().upper()
            return "YES" in text
            
    except Exception as e:
        logger.warning(f"Vision handwriting detection failed: {e}")
        
    return False

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
    
    is_handwritten = False
    
    for i, page in enumerate(doc):
        if page.rotation != 0:
            has_rotated = True
        total_text_len += len(page.get_text("text").strip())
        total_images += len(page.get_image_info())
        
        # Only check the first page for handwriting to save time/tokens
        if i == 0 and not is_handwritten:
            is_handwritten = _detect_handwriting_with_vision(page)
            
    doc.close()
    
    traits = []
    
    avg_text = total_text_len / max(1, num_pages)
    
    is_scanned = avg_text < 50 and total_images > 0
    is_dense = avg_text > 2000
    
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
