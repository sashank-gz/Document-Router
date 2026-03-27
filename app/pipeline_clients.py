"""
HTTP clients for downstream OCR and LLM extraction pipelines.

Endpoints and timeouts are loaded from app.config so they can be
set via environment variables.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from . import config

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when a pipeline call fails."""


def _post_file(endpoint: str, file_path: Path) -> dict:
    """POST a PDF to an extraction service and return the parsed response."""
    with file_path.open("rb") as f:
        files = {"file": (file_path.name, f, "application/pdf")}
        response = requests.post(endpoint, files=files, timeout=config.PIPELINE_TIMEOUT)

    if response.status_code >= 400:
        logger.error(
            "Pipeline call failed: endpoint=%s status=%s body=%s",
            endpoint,
            response.status_code,
            response.text,
        )
        raise PipelineError(f"Pipeline call failed with status {response.status_code}")

    content_type = response.headers.get("content-type", "")
    payload = response.json() if "application/json" in content_type else {"raw": response.text}
    return {
        "status_code": response.status_code,
        "endpoint": endpoint,
        "response": payload,
    }


def _dry_run_response(endpoint: str, file_path: Path) -> dict:
    """Return a simulated response when dry-run mode is active."""
    logger.info("DRY-RUN: would call %s with %s", endpoint, file_path.name)
    return {
        "mode": "DRY_RUN",
        "endpoint": endpoint,
        "file_name": file_path.name,
        "message": "Pipeline call skipped (dry-run mode)",
    }


def send_to_ocr_pipeline(file_path: Path) -> dict:
    """Forward a PDF to the OCR extraction service."""
    logger.info("Routing to OCR pipeline: %s → %s", file_path.name, config.OCR_ENDPOINT)
    if config.PIPELINE_DRY_RUN:
        return _dry_run_response(config.OCR_ENDPOINT, file_path)
    return _post_file(config.OCR_ENDPOINT, file_path)


def send_to_llm_pipeline(file_path: Path) -> dict:
    """Forward a PDF to the LLM extraction service."""
    logger.info("Routing to LLM pipeline: %s → %s", file_path.name, config.LLM_ENDPOINT)
    if config.PIPELINE_DRY_RUN:
        return _dry_run_response(config.LLM_ENDPOINT, file_path)
    return _post_file(config.LLM_ENDPOINT, file_path)
