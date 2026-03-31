from email.message import EmailMessage

from app.email_utils import _build_email_metadata, parse_eml


def test_parse_eml_html_body_extraction(tmp_path):
    msg = EmailMessage()
    msg["Subject"] = "Submission Update"
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg.set_content(
        "<html><body><p>Hello Policy Team</p><p>Coverage updated.</p></body></html>",
        subtype="html",
    )

    eml_path = tmp_path / "sample.eml"
    eml_path.write_bytes(msg.as_bytes())

    metadata, attachments = parse_eml(eml_path, tmp_path / "attachments")

    assert metadata["subject"] == "Submission Update"
    assert metadata["from"] == "sender@example.com"
    assert metadata["to"] == "receiver@example.com"
    assert "Hello Policy Team" in metadata["body"]
    assert "Coverage updated." in metadata["body"]
    assert attachments == []


def test_build_email_metadata_strips_null_bytes():
    metadata = _build_email_metadata("Policy\x00", "User\x00", "Body\x00")

    assert metadata["subject"] == "Policy"
    assert metadata["from"] == "User"
    assert metadata["body"] == "Body"
