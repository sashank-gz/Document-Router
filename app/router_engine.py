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
        return self._process_file(job_id, saved_path)

    def continue_processing(self, job_id: int) -> dict:
        """Resume processing of a job (e.g. after password unlock)."""
        job = self.job_store.get_job(job_id)
        if not job:
            raise ValueError("Job not found")
        saved_path = self.uploads_dir / job.file_name
        
        # Merge existing debug_info into a new dict
        from .pdf_utils import analyze_pdf
        pdf_info = analyze_pdf(saved_path)
        debug_info = {"pdf_traits": pdf_info.get("traits", [])}
        
        return self._process_file(job_id, saved_path, debug_info)

    def _process_file(self, job_id: int, saved_path: Path, initial_debug_info: dict | None = None) -> dict:
        """Internal synchronous method to run the classification and pipeline."""
        classification = None
        debug_info = initial_debug_info or {}
        
        try:
            from .pdf_utils import analyze_pdf
            import json
            
            # If not initialized, check encryption and properties
            if initial_debug_info is None:
                pdf_info = analyze_pdf(saved_path)
                if pdf_info.get("is_encrypted"):
                    self.job_store.update_job(
                        job_id,
                        status="REQUIRES_PASSWORD",
                        debug_info=json.dumps({"password_attempts": 0, "pdf_traits": pdf_info.get("traits", [])})
                    )
                    return {
                        "job_id": job_id,
                        "file_name": saved_path.name,
                        "status": "REQUIRES_PASSWORD",
                        "message": "The file is protected with a password.",
                        "pdf_traits": pdf_info.get("traits", [])
                    }
                debug_info["pdf_traits"] = pdf_info.get("traits", [])

            # ── Classify ─────────────────────────────────────────
            # Tier 2 text (multi-page based on config/settings.txt)
            tier_2_text = extract_classification_text(saved_path)

            # Multi-page text for Tier 3 (LLM) — wider scope
            multi_page_text = None
            if config.GROQ_ENABLED or config.GEMINI_ENABLED:
                multi_page_text = extract_pages_text(
                    saved_path, max_pages=config.CLASSIFICATION_MAX_PAGES,
                )

            classification, cls_debug_info = classify_document(
                filename=saved_path.name,
                keyword_text=tier_2_text,
                llm_text=multi_page_text,
            )
            
            # Merge debug info safely
            debug_info.update(cls_debug_info)

            self.job_store.update_job(
                job_id,
                route=classification.pipeline.value,
                status="CLASSIFIED",
                debug_info=json.dumps(debug_info) if debug_info else None
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
                "pdf_traits": debug_info.get("pdf_traits", [])
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
                "pdf_traits": debug_info.get("pdf_traits", [])
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
        
        # Add available outputs links
        stem = path.stem
        outputs = []
        for ext in [".md", ".json", ".html"]:
            if (path.parent / f"{stem}{ext}").exists():
                outputs.append(ext[1:].upper())
        result["available_outputs"] = outputs

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
            
        if debug_info:
            if "pdf_traits" in debug_info:
                result["pdf_traits"] = debug_info["pdf_traits"]
            if config.DEBUG_MODE:
                result["debug"] = debug_info
                
        return result
