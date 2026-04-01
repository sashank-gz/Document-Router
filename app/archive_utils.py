"""
Utilities for handling archive files (ZIP).
"""

import logging
import os
import shutil
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_zip_to_directory(zip_path: Path, target_dir: Path) -> list[Path]:
    """
    Safely extract a ZIP file to a target directory.

    Returns:
        list[Path]: A list of paths to the successfully extracted files.
    """
    extracted_files: list[Path] = []

    if not zip_path.exists():
        logger.error("ZIP file not found: %s", zip_path)
        return extracted_files

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Create a unique sub-directory for this ZIP extraction
            # target_dir is usually the uploads folder
            extraction_sub_dir = (
                target_dir / f"extracted_{zip_path.stem}_{zip_path.stat().st_ctime_ns}"
            )
            extraction_sub_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Extracting %s to %s", zip_path.name, extraction_sub_dir)
            for member in zip_ref.infolist():
                target_path = (extraction_sub_dir / member.filename).resolve()
                if not str(target_path).startswith(str(extraction_sub_dir.resolve()) + os.sep):
                    raise ValueError(f"Path traversal detected in ZIP: {member.filename}")

                if member.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(member, "r") as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target, length=16384)

            # Walk the extracted directory to collect all files
            for file_path in extraction_sub_dir.rglob("*"):
                if file_path.is_file():
                    extracted_files.append(file_path)

    except ValueError as ve:
        logger.error("Security violation during ZIP extraction: %s", ve)
        if "extraction_sub_dir" in locals() and extraction_sub_dir.exists():
            shutil.rmtree(extraction_sub_dir, ignore_errors=True)
        raise ve
    except zipfile.BadZipFile:
        logger.error("Failed to extract %s: File is not a zip file or is corrupted.", zip_path.name)
    except Exception as e:
        logger.exception("Unexpected error extracting ZIP %s: %s", zip_path.name, str(e))

    return extracted_files
