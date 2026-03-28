from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.document_types import DocumentType, Pipeline
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_pipeline_responses(monkeypatch):
    """Mock all external pipeline calls to be deterministic."""
    mock_ocr = MagicMock(
        return_value={"status_code": 200, "response": {"filename": "ocr_output.json"}}
    )
    mock_llm = MagicMock(
        return_value={"status_code": 200, "response": {"filename": "llm_output.json"}}
    )

    monkeypatch.setattr("app.router_engine.send_to_ocr_pipeline", mock_ocr)
    monkeypatch.setattr("app.router_engine.send_to_llm_pipeline", mock_llm)

    return mock_ocr, mock_llm


@pytest.fixture
def mock_file_services(monkeypatch):
    """Mock file saving and moving to avoid disk side effects."""
    monkeypatch.setattr(
        "app.file_service.save_upload_file", MagicMock(return_value=Path("dummy.pdf"))
    )
    monkeypatch.setattr(
        "app.file_service.move_to_processed", MagicMock(return_value=Path("processed/dummy.pdf"))
    )
    monkeypatch.setattr(
        "app.file_service.extract_classification_text", MagicMock(return_value="dummy text")
    )
    monkeypatch.setattr(
        "app.file_service.extract_pages_text", MagicMock(return_value="dummy pages")
    )


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_security_traversal(mock_file_services):
    """Verify that directory traversal attempts are blocked by the viewer/downloader."""
    # Note: The upload itself saves to UPLOADS_DIR using the filename.
    # The vulnerability usually exists in download/view routes.
    bad_filenames = ["../../etc/passwd", "..\..\windows\system32\config", "safe.pdf/../../unsafe"]

    for filename in bad_filenames:
        response = client.get(f"/processed/{filename}")
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid filename"


def test_upload_invalid_extension(mock_file_services):
    """Verify that unsupported file types are rejected."""
    response = client.get("/processed/malicious.exe")
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@patch("app.router_engine.DocumentRouterEngine._process_file")
def test_upload_flow_baseline(mock_process, mock_file_services):
    """Verify standard upload triggers the background task and creates a job."""
    files = [("files", ("test.pdf", b"dummy content", "application/pdf"))]
    response = client.post("/upload", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert "job_id" in data["jobs"][0]

    # Verify job exists in DB
    job_id = data["jobs"][0]["job_id"]
    job_response = client.get(f"/jobs/{job_id}")
    assert job_response.status_code == 200
    assert job_response.json()["file_name"] == "test.pdf"


def test_viewer_json_highlighting():
    """Verify that the viewer correctly handles JSON content and highlighting."""
    # Patch where it is USED, not where it is defined
    with (
        patch("app.main.resolve_processed_file") as mock_resolve,
        patch("app.main.Path.read_text") as mock_read,
    ):

        mock_resolve.return_value = Path("dummy.json")
        mock_read.return_value = '{"status": "success"}'

        response = client.get("/view/dummy.json")
        assert response.status_code == 200
        # Check for syntax coloring span (purple is #C084FC)
        assert "color:#C084FC" in response.text


def test_pipeline_failure_handling(monkeypatch, mock_file_services):
    """Verify that a pipeline failure correctly marks the job as FAILED."""
    from app.pipeline_clients import PipelineError

    # Patch where it's used in router_engine
    monkeypatch.setattr(
        "app.router_engine.send_to_ocr_pipeline",
        MagicMock(side_effect=PipelineError("Cloud OCR Unavailable")),
    )

    # Mock classifier to return OCR pipeline
    from app.classifier import ClassificationResult

    mock_cls = MagicMock(
        return_value=(
            ClassificationResult(DocumentType.ACORD, Pipeline.OCR, "keyword"),
            {"debug": "info"},
        )
    )
    monkeypatch.setattr("app.router_engine.classify_document", mock_cls)

    from app.main import job_store, router_engine

    job_id = job_store.create_job("error_test.pdf", "OCR", "PROCESSING")

    router_engine._process_file(job_id, Path("error_test.pdf"))

    job = job_store.get_job(job_id)
    assert job.status == "FAILED"


def test_pipeline_timeout_handling(monkeypatch, mock_file_services):
    """Verify pipeline timeout is handled gracefully."""
    import requests

    # Patch requests.post where it is used in pipeline_clients
    monkeypatch.setattr(
        "app.pipeline_clients.requests.post",
        MagicMock(side_effect=requests.exceptions.Timeout("Connection timed out")),
    )

    # Mock classifier to return OCR pipeline
    from app.classifier import ClassificationResult

    mock_cls = MagicMock(
        return_value=(
            ClassificationResult(DocumentType.ACORD, Pipeline.OCR, "keyword"),
            {"debug": "info"},
        )
    )
    monkeypatch.setattr("app.router_engine.classify_document", mock_cls)

    from app.main import job_store, router_engine

    job_id = job_store.create_job("timeout_test.pdf", "OCR", "PROCESSING")

    router_engine._process_file(job_id, Path("timeout_test.pdf"))

    job = job_store.get_job(job_id)
    assert job.status == "FAILED"
