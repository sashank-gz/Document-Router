"""
Utilities for handling archive files (ZIP).
"""

import logging
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
            zip_ref.extractall(extraction_sub_dir)

            # Walk the extracted directory to collect all files
            for file_path in extraction_sub_dir.rglob("*"):
                if file_path.is_file():
                    extracted_files.append(file_path)

    except zipfile.BadZipFile:
        logger.error("Failed to extract %s: File is not a zip file or is corrupted.", zip_path.name)
    except Exception as e:
        logger.exception("Unexpected error extracting ZIP %s: %s", zip_path.name, str(e))

    return extracted_files
