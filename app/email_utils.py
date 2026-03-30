"""
Email parsing and attachment extraction for .eml and .msg files.
"""

import logging
from email import message_from_binary_file
from email.policy import default
from pathlib import Path
from typing import Any

try:
    import extract_msg
except ImportError:
    extract_msg = None

logger = logging.getLogger(__name__)


def _build_email_metadata(
    subject: str | None, sender: str | None, body: str | None
) -> dict[str, Any]:
    """Uniformly structure email metadata with fallback defaults."""
    return {
        "subject": (subject or "(No Subject)").strip(),
        "from": (sender or "(Unknown Sender)").strip(),
        "body": body or "",
    }


def parse_eml(file_path: Path, output_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    """Parse .eml file and extract attachments to output_dir."""
    attachments = []
    with open(file_path, "rb") as f:
        msg = message_from_binary_file(f, policy=default)

    subject = msg.get("subject", "(No Subject)")
    sender = msg.get("from", "(Unknown Sender)")
    body = ""

    # Process bodies
    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition"))

        if "attachment" not in content_disposition and content_type == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                body += payload.decode(errors="replace")
        elif "attachment" in content_disposition:
            filename = part.get_filename()
            if filename:
                att_path = output_dir / filename
                with open(att_path, "wb") as att_f:
                    att_f.write(part.get_payload(decode=True))
                attachments.append(att_path)

    if not body and not msg.is_multipart():
        body = msg.get_payload(decode=True).decode(errors="replace")

    return _build_email_metadata(subject, sender, body), attachments


def parse_msg(file_path: Path, output_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    """Parse .msg file and extract attachments to output_dir using extract-msg."""
    if extract_msg is None:
        raise ImportError("extract-msg library is not installed.")

    msg = extract_msg.Message(str(file_path))
    subject = msg.subject or "(No Subject)"
    sender = msg.sender or "(Unknown Sender)"
    body = msg.body or ""

    attachments = []
    for attachment in msg.attachments:
        att_path = output_dir / attachment.getFilename()
        attachment.save(customPath=str(output_dir))
        attachments.append(att_path)

    return _build_email_metadata(subject, sender, body), attachments
