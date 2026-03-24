"""
File I/O utilities: save uploads, extract PDF text, move processed files.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from .extractor import AdvancedDoclingExtractor

_extractor = None

logger = logging.getLogger(__name__)


async def save_upload_file(upload_file: UploadFile, uploads_dir: Path) -> Path:
    """Persist an uploaded file to local storage with a unique name."""
    uploads_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid4().hex}_{upload_file.filename}"
    destination = uploads_dir / unique_name

    logger.info("Saving uploaded file: %s", upload_file.filename)
    with destination.open("wb") as out_file:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            out_file.write(chunk)

    await upload_file.close()
    return destination


def extract_document_text(source: Path | str) -> str:
    """
    Extract text using the Advanced Hardened Docling pipeline.
    This is a reusable function for document conversion.
    """
    global _extractor
    if _extractor is None:
        _extractor = AdvancedDoclingExtractor()
    return _extractor.extract(source)


def extract_classification_text(file_path: Path) -> str:
    """Extract text for classification (Tier 2)."""
    # Note: Docling converts the entire document to markdown by default.
    from . import config
    return extract_document_text(file_path)


def extract_pages_text(file_path: Path, max_pages: int = 3) -> str:
    """
    Extract text from a document.

    Used by Tier 3 (LLM classification) to give the model more context.
    Note: max_pages is kept for backward compatibility, but Docling 
    processes the entire document by default.
    """
    return extract_document_text(file_path)


def move_to_processed(file_path: Path, processed_dir: Path) -> Path:
    """Move a processed file to the processed folder."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    destination = processed_dir / file_path.name
    shutil.move(str(file_path), str(destination))
    
    # Move any exported docling auxiliary files
    for ext in [".md", ".json", ".html"]:
        aux_file = file_path.parent / f"{file_path.stem}{ext}"
        if aux_file.exists():
            shutil.move(str(aux_file), str(processed_dir / f"{file_path.stem}{ext}"))
            
    return destination
