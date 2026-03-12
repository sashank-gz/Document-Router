"""
Core routing workflow — orchestrates file save, classification, pipeline
dispatch, and job status tracking for each uploaded document.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import UploadFile

from . import config
from .classifier import classify_document
from .document_types import Pipeline
from .file_service import (
    extract_classification_text,
    extract_pages_text,
    move_to_processed,
    save_upload_file,
)
from .models import JobStore
from .pipeline_clients import PipelineError, send_to_llm_pipeline, send_to_ocr_pipeline

logger = logging.getLogger(__name__)


class DocumentRouterEngine:
    """Save → Classify → Route → Track for each uploaded PDF."""

    def __init__(self, job_store: JobStore, uploads_dir: Path, processed_dir: Path) -> None:
        self.job_store = job_store
        self.uploads_dir = uploads_dir
        self.processed_dir = processed_dir

    async def process_upload(self, upload_file: UploadFile) -> dict:
        """Full lifecycle for one uploaded PDF."""
        saved_path = await save_upload_file(upload_file, self.uploads_dir)
        job_id = self.job_store.create_job(
            file_name=saved_path.name, route="UNKNOWN", status="UPLOADED",
        )

        classification = None
        debug_info = {}
        try:
            # ── Classify ─────────────────────────────────────────
            # Tier 2 text (multi-page based on config/settings.txt)
            tier_2_text = extract_classification_text(saved_path)

            # Multi-page text for Tier 3 (LLM) — wider scope
            multi_page_text = None
            if config.GROQ_ENABLED or config.GEMINI_ENABLED:
                multi_page_text = extract_pages_text(
                    saved_path, max_pages=config.CLASSIFICATION_MAX_PAGES,
                )

            classification, debug_info = classify_document(
                filename=saved_path.name,
                keyword_text=tier_2_text,
                llm_text=multi_page_text,
            )

            self.job_store.update_job(
                job_id,
                route=classification.pipeline.value,
                status="CLASSIFIED",
            )

            logger.info(
                "Classification: file=%s type=%s pipeline=%s tier=%s confidence=%.2f",
                saved_path.name,
                classification.document_type.value,
                classification.pipeline.value,
                classification.tier,
                classification.confidence,
            )

            # ── Route ────────────────────────────────────────────
            if classification.pipeline == Pipeline.MANUAL:
                self.job_store.update_job(job_id, status="ROUTED")
                processed_path = move_to_processed(saved_path, self.processed_dir)
                self.job_store.update_job(job_id, status="COMPLETED")
                res = self._build_result(
                    job_id, processed_path, classification,
                    message="Routed to manual review queue",
                    debug_info=debug_info,
                )
                self.job_store.update_job(job_id, pipeline_url=res.get("pipeline_url"))
                return res

            self.job_store.update_job(job_id, status="ROUTED")
            self.job_store.update_job(job_id, status="PROCESSING")

            if classification.pipeline == Pipeline.OCR:
                pipeline_result = send_to_ocr_pipeline(saved_path)
            else:
                pipeline_result = send_to_llm_pipeline(saved_path)

            processed_path = move_to_processed(saved_path, self.processed_dir)
            self.job_store.update_job(job_id, status="COMPLETED")
            res = self._build_result(
                job_id, processed_path, classification,
                pipeline_result=pipeline_result,
                debug_info=debug_info,
            )
            self.job_store.update_job(job_id, pipeline_url=res.get("pipeline_url"))
            return res

        except PipelineError as exc:
            logger.exception("Pipeline processing failed: file=%s", saved_path.name)
            self.job_store.update_job(job_id, status="FAILED")
            result = {
                "job_id": job_id,
                "file_name": saved_path.name,
                "status": "FAILED",
                "error": str(exc),
            }
            # Include classification data if available
            if classification:
                result["document_type"] = classification.document_type.value
                result["pipeline"] = classification.pipeline.value
                result["classification_tier"] = classification.tier
                result["confidence"] = classification.confidence
                if classification.pipeline == Pipeline.OCR:
                    result["pipeline_url"] = config.OCR_UI_URL
                elif classification.pipeline == Pipeline.LLM:
                    result["pipeline_url"] = config.LLM_UI_URL
            
            self.job_store.update_job(job_id, pipeline_url=result.get("pipeline_url"))
            return result

        except Exception as exc:
            logger.exception("Routing failed: file=%s", saved_path.name)
            self.job_store.update_job(job_id, status="FAILED")
            result = {
                "job_id": job_id,
                "file_name": saved_path.name,
                "status": "FAILED",
                "error": str(exc),
            }
            if classification:
                result["document_type"] = classification.document_type.value
                result["pipeline"] = classification.pipeline.value
                result["classification_tier"] = classification.tier
                result["confidence"] = classification.confidence
                if classification.pipeline == Pipeline.OCR:
                    result["pipeline_url"] = config.OCR_UI_URL
                elif classification.pipeline == Pipeline.LLM:
                    result["pipeline_url"] = config.LLM_UI_URL
            
            self.job_store.update_job(job_id, pipeline_url=result.get("pipeline_url"))
            return result

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_result(
        job_id: int,
        path: Path,
        classification,
        *,
        message: str | None = None,
        pipeline_result: dict | None = None,
        debug_info: dict | None = None,
    ) -> dict:
        result: dict = {
            "job_id": job_id,
            "file_name": path.name,
            "document_type": classification.document_type.value,
            "pipeline": classification.pipeline.value,
            "classification_tier": classification.tier,
            "confidence": classification.confidence,
            "status": "COMPLETED",
        }
        # Include the service URL so the frontend can link to it
        if classification.pipeline == Pipeline.OCR:
            url = config.OCR_UI_URL
            if pipeline_result and isinstance(pipeline_result.get("response"), dict):
                remote_file = pipeline_result["response"].get("filename")
                if remote_file:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}file={remote_file}"
            result["pipeline_url"] = url
        elif classification.pipeline == Pipeline.LLM:
            url = config.LLM_UI_URL
            if pipeline_result and isinstance(pipeline_result.get("response"), dict):
                remote_file = pipeline_result["response"].get("filename")
                if remote_file:
                    sep = "&" if "?" in url else "?"
                    url = f"{url}{sep}file={remote_file}"
            result["pipeline_url"] = url
        if message:
            result["message"] = message
        if pipeline_result:
            result["pipeline_result"] = pipeline_result
        if debug_info and config.DEBUG_MODE:
            result["debug"] = debug_info
        return result
