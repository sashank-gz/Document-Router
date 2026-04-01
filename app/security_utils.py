"""
Centralized security utilities for detecting and unlocking encrypted files.
Supports PDFs, Microsoft Office files (Word, Excel), and ZIP archives.
"""

import logging
import zipfile
from pathlib import Path

import fitz
import msoffcrypto
import pyzipper

from .file_utils import FileCategory, get_file_category

logger = logging.getLogger(__name__)


def is_encrypted(file_path: Path | str) -> bool:
    """
    Check if a file requires a password to open.
    Routes to the correct checker based on the file category.
    """
    path = Path(file_path)
    if not path.exists():
        return False

    category = get_file_category(path)

    try:
        if category == FileCategory.PDF:
            return _is_pdf_encrypted(path)
        elif category in (FileCategory.DOCUMENT, FileCategory.SPREADSHEET):
            return _is_msoffice_encrypted(path)
        elif category == FileCategory.ARCHIVE:
            return _is_zip_encrypted(path)
    except Exception as e:
        logger.warning(f"Failed to check encryption status for {path.name}: {e}")

    return False


def unlock_document(file_path: Path | str, password: str) -> bool:
    """
    Attempt to decrypt a file using the given password.
    If successful, overwrites the original file with the decrypted version.
    """
    path = Path(file_path)
    if not path.exists():
        return False

    category = get_file_category(path)

    try:
        if category == FileCategory.PDF:
            return _unlock_pdf(path, password)
        elif category in (FileCategory.DOCUMENT, FileCategory.SPREADSHEET):
            return _unlock_msoffice(path, password)
        elif category == FileCategory.ARCHIVE:
            return _unlock_zip(path, password)
    except Exception as e:
        logger.error(f"Failed to unlock {path.name}: {e}")

    return False


# ── PDF Specific Handling ─────────────────────────────────────


def _is_pdf_encrypted(path: Path) -> bool:
    doc = fitz.open(str(path))
    needs_pass = doc.needs_pass
    doc.close()
    return needs_pass


def _unlock_pdf(file_path: Path, password: str) -> bool:
    doc = fitz.open(str(file_path))
    if doc.needs_pass:
        is_unlocked = doc.authenticate(password)
        if is_unlocked:
            temp_path = str(file_path) + ".unlocked.pdf"
            doc.save(temp_path)
            doc.close()
            Path(temp_path).replace(file_path)
            return True
    doc.close()
    return False


# ── MS Office Specific Handling ───────────────────────────────


def _is_msoffice_encrypted(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            office_file = msoffcrypto.OfficeFile(f)
            return office_file.is_encrypted()
    except Exception:
        # If msoffcrypto fails to parse it entirely, it isn't an encrypted office file.
        return False


def _unlock_msoffice(file_path: Path, password: str) -> bool:
    temp_path = str(file_path) + ".unlocked"
    try:
        with open(file_path, "rb") as f_in:
            office_file = msoffcrypto.OfficeFile(f_in)
            if office_file.is_encrypted():
                office_file.load_key(password=password)
                with open(temp_path, "wb") as f_out:
                    office_file.decrypt(f_out)

        Path(temp_path).replace(file_path)
        return True
    except msoffcrypto.exceptions.DecryptionError:
        return False  # Wrong password
    except Exception as e:
        logger.error(f"MS Office unlock attempt failed structurally: {e}")
        if Path(temp_path).exists():
            Path(temp_path).unlink()
        return False


# ── ZIP Archive Specific Handling ─────────────────────────────


def _is_zip_encrypted(path: Path) -> bool:
    try:
        # pyzipper supports both ZipCrypto (legacy) and AES (modern)
        with pyzipper.AESZipFile(path) as zf:
            for zinfo in zf.infolist():
                # Flag 0x1 denotes encryption in ZIP specification
                if zinfo.flag_bits & 0x1:
                    return True
        return False
    except pyzipper.zipfile.BadZipFile:
        return False


def _unlock_zip(file_path: Path, password: str) -> bool:
    """
    For a zip file, "unlocking" in-place means creating a new identical zip
    where all the contents have been extracted and re-compressed without a password.
    """
    temp_path = str(file_path) + ".unlocked.zip"
    try:
        with pyzipper.AESZipFile(file_path, "r") as zf_in:
            zf_in.setpassword(password.encode("utf-8"))

            # Verify password is correct by trying to read the first encrypted file
            encrypted_files = [z for z in zf_in.infolist() if z.flag_bits & 0x1]
            if encrypted_files:
                try:
                    zf_in.read(encrypted_files[0].filename)
                except RuntimeError:
                    return False

            # Password is correct. Repackage everything generically without encryption
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
                for item in zf_in.infolist():
                    data = zf_in.read(item.filename)
                    zf_out.writestr(item.filename, data)

        Path(temp_path).replace(file_path)
        return True
    except Exception as e:
        logger.error(f"ZIP unlock attempt failed structurally: {e}")
        if Path(temp_path).exists():
            Path(temp_path).unlink()
        return False
