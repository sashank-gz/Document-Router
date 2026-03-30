from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.extraction_handlers import ExtractionResult
from app.file_utils import FileCategory, get_file_category


@pytest.mark.parametrize(
    "filename, expected_category",
    [
        ("test.pdf", FileCategory.PDF),
        ("data.xlsx", FileCategory.SPREADSHEET),
        ("doc.docx", FileCategory.DOCUMENT),
        ("info.csv", FileCategory.DATA),
        ("config.json", FileCategory.DATA),
        ("mail.eml", FileCategory.EMAIL),
        ("outlook.msg", FileCategory.EMAIL),
        ("random.txt", FileCategory.UNSUPPORTED),
    ],
)
def test_file_category_detection(filename, expected_category):
    assert get_file_category(filename) == expected_category


def test_json_handler():
    from app.extraction_handlers import JSONHandler

    content = {"key": "value", "list": [1, 2, 3]}

    with patch("builtins.open", MagicMock()):
        with patch("json.load", return_value=content):
            handler = JSONHandler()
            result = handler.handle(Path("test.json"))

            assert "value" in result.raw_text
            assert "key" in result.markdown
            assert result.structured_json == content


def test_csv_handler():
    import io

    import pandas as pd

    from app.extraction_handlers import CSVHandler

    csv_data = "Name,Age\nAlice,30\nBob,25"
    df = pd.read_csv(io.StringIO(csv_data))

    with patch("pandas.read_csv", return_value=df):
        handler = CSVHandler()
        result = handler.handle(Path("test.csv"))

        assert "Alice" in result.raw_text
        assert "Age" in result.markdown
        assert result.structured_json[0]["Name"] == "Alice"


@patch("app.email_utils.parse_eml")
def test_email_handler_eml(mock_parse):
    from app.extraction_handlers import EmailHandler

    mock_parse.return_value = (
        {"subject": "Test", "from": "sender", "body": "Hello"},
        [Path("attachment.pdf")],
    )

    handler = EmailHandler()
    result = handler._handle_eml(Path("test.eml"))

    assert "Test" in result.markdown
    assert "Hello" in result.raw_text
    assert len(result.attachments) == 1
    assert result.attachments[0].name == "attachment.pdf"


@patch("app.extraction_handlers.extract_content")
@patch("app.router_engine.DocumentRouterEngine._process_file")
def test_email_attachment_recursion(mock_process, mock_extract, tmp_path):
    # Setup
    from app.router_engine import DocumentRouterEngine

    job_store = MagicMock()
    engine = DocumentRouterEngine(job_store, tmp_path, tmp_path)

    # Mock email extraction result with one attachment
    att_path = tmp_path / "attach.pdf"
    att_path.write_text("dummy")

    mock_extract.return_value = ExtractionResult(
        raw_text="Email body", markdown="# Email body", attachments=[att_path]
    )

    # Mock job creation
    job_store.create_job.return_value = 101

    # Execute
    engine._handle_email_attachments(100, Path("test.eml"), depth=0)

    # Verify
    job_store.create_job.assert_called_once()
    args, kwargs = job_store.create_job.call_args
    assert kwargs["parent_job_id"] == 100
    assert kwargs["file_name"] == "attach.pdf"

    # Verify recursion
    mock_process.assert_called_once()
    p_args, p_kwargs = mock_process.call_args
    assert p_args[0] == 101
    assert p_kwargs["depth"] == 0
