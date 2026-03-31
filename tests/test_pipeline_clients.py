from unittest.mock import Mock, patch

from app.pipeline_clients import _post_file


def _mock_response() -> Mock:
    response = Mock()
    response.status_code = 200
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {"ok": True}
    return response


def test_post_file_uses_pdf_mime(tmp_path):
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.7")

    with patch("app.pipeline_clients.requests.post", return_value=_mock_response()) as mock_post:
        _post_file("http://example.test/process", file_path)

    sent_file = mock_post.call_args.kwargs["files"]["file"]
    assert sent_file[2] == "application/pdf"


def test_post_file_falls_back_to_octet_stream_for_unknown_extension(tmp_path):
    file_path = tmp_path / "sample.unknownext"
    file_path.write_bytes(b"payload")

    with patch("app.pipeline_clients.requests.post", return_value=_mock_response()) as mock_post:
        _post_file("http://example.test/process", file_path)

    sent_file = mock_post.call_args.kwargs["files"]["file"]
    assert sent_file[2] == "application/octet-stream"
