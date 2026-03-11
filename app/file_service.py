"""
File I/O utilities: save uploads, extract PDF text, move processed files.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from uuid import uuid4

import pdfplumber
from fastapi import UploadFile

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


def extract_first_page_text(file_path: Path) -> str:
    """Extract text from the first page only (used for Tier 2 keyword matching)."""
    return extract_pages_text(file_path, max_pages=1)


def extract_pages_text(file_path: Path, max_pages: int = 3) -> str:
    """
    Extract text from up to *max_pages* pages of a PDF.

    Used by Tier 3 (LLM classification) to give the model more context
    than a single page provides.
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            pages_to_read = min(len(pdf.pages), max_pages)
            texts: list[str] = []
            for i in range(pages_to_read):
                page_text = pdf.pages[i].extract_text() or ""
                if page_text.strip():
                    texts.append(page_text)
            return "\n\n".join(texts)
    except Exception as exc:
        logger.exception("Unable to extract text from file: %s", file_path)
        raise RuntimeError(f"Failed to read PDF file: {file_path.name}") from exc


def move_to_processed(file_path: Path, processed_dir: Path) -> Path:
    """Move a processed file to the processed folder."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    destination = processed_dir / file_path.name
    shutil.move(str(file_path), str(destination))
    return destination
