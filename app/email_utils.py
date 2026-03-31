"""
Email parsing and attachment extraction for .eml and .msg files.
"""

import html
import logging
import re
from email import message_from_binary_file
from email.policy import default
from pathlib import Path
from typing import Any

try:
    import extract_msg
except ImportError:
    extract_msg = None

logger = logging.getLogger(__name__)


def _clean_text(text: object | None) -> str:
    """Strip NULs and surrounding whitespace from extracted text."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("\x00", "").strip()


def _decode_payload(payload: bytes | str | None, charset: str | None = None) -> str:
    """Decode bytes payload with charset fallback."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return _clean_text(payload)

    encodings = [charset, "utf-8", "latin-1"]
    for enc in encodings:
        if not enc:
            continue
        try:
            return _clean_text(payload.decode(enc, errors="replace"))
        except LookupError:
            continue
    return _clean_text(payload.decode("utf-8", errors="replace"))


def _html_to_text(raw_html: str) -> str:
    """Convert simple HTML email body to readable plain text."""
    if not raw_html:
        return ""

    text = raw_html
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)

    lines = [line.strip() for line in text.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return _clean_text(compact)


def _rtf_to_text(raw_rtf: str) -> str:
    """Best-effort conversion of RTF to plain text without external deps."""
    if not raw_rtf:
        return ""
    text = raw_rtf
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+[0-9]* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+", " ", text)
    return _clean_text(text)


def _build_email_metadata(
    subject: str | None,
    sender: str | None,
    body: str | None,
    to: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Uniformly structure email metadata with fallback defaults."""
    return {
        "subject": _clean_text(subject or "(No Subject)") or "(No Subject)",
        "from": _clean_text(sender or "(Unknown Sender)") or "(Unknown Sender)",
        "to": _clean_text(to or ""),
        "date": _clean_text(date or ""),
        "body": _clean_text(body),
    }


def parse_eml(file_path: Path, output_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    """Parse .eml file and extract attachments to output_dir."""
    attachments = []
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(file_path, "rb") as f:
        msg = message_from_binary_file(f, policy=default)

    subject = msg.get("subject", "(No Subject)")
    sender = msg.get("from", "(Unknown Sender)")
    recipient = msg.get("to", "")
    date = msg.get("date", "")

    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = part.get_content_disposition()

        if disposition == "attachment":
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
            continue

        if content_type in {"text/plain", "text/html"}:
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = part.get_payload()
            text_part = _decode_payload(payload, part.get_content_charset())
            if not text_part:
                continue
            if content_type == "text/plain":
                plain_parts.append(text_part)
            else:
                html_parts.append(text_part)

    body = ""
    if plain_parts:
        body = _clean_text("\n".join(plain_parts))
    elif html_parts:
        body = _html_to_text("\n".join(html_parts))
    elif not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload is None:
            payload = msg.get_payload()
        body = _decode_payload(payload, msg.get_content_charset())
        if msg.get_content_type() == "text/html":
            body = _html_to_text(body)

    if not body:
        preferred = msg.get_body(preferencelist=("plain", "html"))
        if preferred:
            preferred_text = preferred.get_content()
            if preferred.get_content_type() == "text/html":
                body = _html_to_text(_decode_payload(preferred_text))
            else:
                body = _decode_payload(preferred_text)

    return _build_email_metadata(subject, sender, body, to=recipient, date=date), attachments


def parse_msg(file_path: Path, output_dir: Path) -> tuple[dict[str, Any], list[Path]]:
    """Parse .msg file and extract attachments to output_dir using extract-msg."""
    if extract_msg is None:
        raise ImportError("extract-msg library is not installed.")

    output_dir.mkdir(parents=True, exist_ok=True)
    msg = extract_msg.Message(str(file_path))
    try:
        subject = _clean_text(msg.subject) or "(No Subject)"
        sender = _clean_text(msg.sender) or "(Unknown Sender)"
        recipient = _clean_text(getattr(msg, "to", "") or "")
        date = _clean_text(getattr(msg, "date", "") or "")
        body = _clean_text(msg.body)

        if not body:
            html_body = getattr(msg, "htmlBody", None)
            html_text = _decode_payload(html_body)
            body = _html_to_text(html_text)

        if not body:
            rtf_body = getattr(msg, "rtfBody", None)
            rtf_text = _decode_payload(rtf_body, "latin-1")
            body = _rtf_to_text(rtf_text)

        output_root = output_dir.resolve()
        attachments = []
        for attachment in msg.attachments:
            filename = _clean_text(attachment.getFilename() or "")
            if not filename:
                continue

            safe_name = Path(filename).name
            if not safe_name or safe_name in {".", ".."} or "\x00" in safe_name:
                logger.warning("Skipping unsafe attachment filename in %s", file_path.name)
                continue

            candidate_path = (output_dir / safe_name).resolve()
            if output_root not in candidate_path.parents:
                logger.warning("Skipping attachment with traversal attempt: %s", safe_name)
                continue

            try:
                data = attachment.data
                if data:
                    candidate_path.write_bytes(data)
                    attachments.append(candidate_path)
                else:
                    logger.warning("Attachment %s in %s has no data", safe_name, file_path.name)
            except Exception as e:
                logger.error("Failed to save attachment %s: %s", safe_name, e)
                try:
                    if candidate_path.exists():
                        candidate_path.unlink()
                except Exception as cleanup_err:
                    logger.warning(
                        "Failed to clean up failed attachment %s at %s: %s",
                        safe_name,
                        candidate_path,
                        cleanup_err,
                    )

        return _build_email_metadata(subject, sender, body, to=recipient, date=date), attachments
    finally:
        try:
            msg.close()
        except Exception:
            pass
