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
    output_dir.mkdir(parents=True, exist_ok=True)
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
            if payload is None:
                continue
            if isinstance(payload, bytes):
                body += payload.decode(errors="replace")
            elif isinstance(payload, str):
                body += payload
            else:
                body += str(payload)
        elif "attachment" in content_disposition:
            filename = part.get_filename()
            safe_name = Path(filename).name if filename else ""
            if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
                logger.warning("Skipping unsafe attachment filename in %s", file_path.name)
                continue

            output_root = output_dir.resolve()
            att_path = (output_dir / safe_name).resolve()
            if output_root not in att_path.parents:
                logger.warning("Skipping attachment with traversal attempt: %s", safe_name)
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                logger.warning("Skipping empty attachment payload for %s", safe_name)
                continue

            with open(att_path, "wb") as att_f:
                att_f.write(payload)
            attachments.append(att_path)

    if not body and not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload is None:
            body = ""
        elif isinstance(payload, bytes):
            body = payload.decode(errors="replace")
        elif isinstance(payload, str):
            body = payload
        else:
            body = str(payload)

    return _build_email_metadata(subject, sender, body), attachments


def parse_msg(file_path: Path, output_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    """Parse .msg file and extract attachments to output_dir using extract-msg."""
    if extract_msg is None:
        raise ImportError("extract-msg library is not installed.")

    output_dir.mkdir(parents=True, exist_ok=True)
    msg = extract_msg.Message(str(file_path))
    try:
        subject = msg.subject or "(No Subject)"
        sender = msg.sender or "(Unknown Sender)"
        body = msg.body or ""

        output_root = output_dir.resolve()
        attachments = []
        for attachment in msg.attachments:
            filename = attachment.getFilename() or ""
            safe_name = Path(filename).name
            if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
                logger.warning("Skipping unsafe attachment filename in %s", file_path.name)
                continue

            candidate_path = (output_dir / safe_name).resolve()
            if output_root not in candidate_path.parents:
                logger.warning("Skipping attachment with traversal attempt: %s", safe_name)
                continue

            saved_path = attachment.save(customPath=str(output_dir))
            att_path = Path(saved_path) if saved_path else candidate_path
            if not att_path.is_absolute():
                att_path = (output_dir / att_path).resolve()

            if output_root not in att_path.parents:
                logger.warning("Skipping saved attachment outside output dir: %s", att_path)
                continue

            attachments.append(att_path)

        return _build_email_metadata(subject, sender, body), attachments
    finally:
        try:
            msg.close()
        except Exception:
            pass
