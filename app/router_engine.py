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
    build_pipeline_url,
    extract_classification_text,
    extract_pages_text,
    list_available_outputs,
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
            file_name=saved_path.name,
            route="UNKNOWN",
            status="UPLOADED",
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

    def _process_file(
        self, job_id: int, saved_path: Path, initial_debug_info: dict | None = None
    ) -> dict:
        """Internal synchronous method to run the classification and pipeline."""
        import time

        start_time = time.time()
        classification = None
        debug_info = initial_debug_info or {}

        try:
            import json

            # Step 1: Analyze PDF (normalize, detect traits, check encryption)
            encrypted_result = self._analyze_pdf(
                job_id, saved_path, debug_info, is_fresh=(initial_debug_info is None)
            )
            if encrypted_result:
                return encrypted_result

            # Step 2: Classify
            classification, debug_info = self._classify(saved_path, debug_info)

            # Preserve streaming logs from the DB before overwriting
            try:
                db_job = self.job_store.get_job(job_id)
                if db_job and db_job.debug_info and "logs" in db_job.debug_info:
                    debug_info["logs"] = db_job.debug_info["logs"]
            except Exception:
                pass

            self.job_store.update_job(
                job_id,
                route=classification.pipeline.value,
                status="CLASSIFIED",
                document_type=classification.document_type.value,
                classification_tier=classification.tier,
                debug_info=json.dumps(debug_info) if debug_info else None,
            )

            logger.info(
                "Classification: file=%s type=%s pipeline=%s tier=%s confidence=%.2f",
                saved_path.name,
                classification.document_type.value,
                classification.pipeline.value,
                classification.tier,
                classification.confidence,
            )

            # Step 3: Route to pipeline
            return self._route(job_id, saved_path, classification, debug_info, start_time)

        except PipelineError as exc:
            logger.exception("Pipeline processing failed: file=%s", saved_path.name)
            elapsed = round(time.time() - start_time, 1)
            return self._build_error_result(
                job_id,
                saved_path,
                exc,
                debug_info,
                classification,
                elapsed,
            )

        except Exception as exc:
            logger.exception("Routing failed: file=%s", saved_path.name)
            return self._build_error_result(
                job_id,
                saved_path,
                exc,
                debug_info,
                classification,
            )

    # ── Sub-steps ────────────────────────────────────────────────

    def _analyze_pdf(
        self,
        job_id: int,
        saved_path: Path,
        debug_info: dict,
        *,
        is_fresh: bool,
    ) -> dict | None:
        """Normalize PDF, detect traits, check encryption.

        Returns a dict (early response) if the file is encrypted, else None.
        """
        import json

        from .pdf_utils import analyze_pdf, normalize_pdf

        if not is_fresh:
            return None

        saved_path = normalize_pdf(saved_path)

        if config.ENABLE_PDF_TRAITS:
            pdf_info = analyze_pdf(saved_path)
            if pdf_info.get("is_encrypted"):
                self.job_store.update_job(
                    job_id,
                    status="REQUIRES_PASSWORD",
                    debug_info=json.dumps(
                        {"password_attempts": 0, "pdf_traits": pdf_info.get("traits", [])}
                    ),
                )
                return {
                    "job_id": job_id,
                    "file_name": saved_path.name,
                    "status": "REQUIRES_PASSWORD",
                    "message": "The file is protected with a password.",
                    "pdf_traits": pdf_info.get("traits", []),
                }
            debug_info["pdf_traits"] = pdf_info.get("traits", [])
        else:
            debug_info["pdf_traits"] = []

        return None

    def _classify(self, saved_path: Path, debug_info: dict) -> tuple:
        """Extract text and run the 3-tier classifier. Returns (classification, debug_info)."""
        tier_2_text = extract_classification_text(saved_path)

        multi_page_text = None
        if config.GROQ_ENABLED or config.GEMINI_ENABLED:
            multi_page_text = extract_pages_text(
                saved_path,
                max_pages=config.CLASSIFICATION_MAX_PAGES,
            )

        classification, cls_debug_info = classify_document(
            filename=saved_path.name,
            keyword_text=tier_2_text,
            llm_text=multi_page_text,
        )
        debug_info.update(cls_debug_info)
        return classification, debug_info

    def _route(
        self,
        job_id: int,
        saved_path: Path,
        classification,
        debug_info: dict,
        start_time: float,
    ) -> dict:
        """Dispatch to the appropriate pipeline and finalize the job."""
        import time

        if classification.pipeline == Pipeline.MANUAL:
            self.job_store.update_job(job_id, status="ROUTED")
            processed_path = move_to_processed(saved_path, self.processed_dir)
            elapsed = round(time.time() - start_time, 1)
            self.job_store.update_job(job_id, status="COMPLETED", extraction_time=elapsed)
            res = self._build_result(
                job_id,
                processed_path,
                classification,
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
        elapsed = round(time.time() - start_time, 1)
        self.job_store.update_job(job_id, status="COMPLETED", extraction_time=elapsed)
        res = self._build_result(
            job_id,
            processed_path,
            classification,
            pipeline_result=pipeline_result,
            debug_info=debug_info,
        )
        self.job_store.update_job(job_id, pipeline_url=res.get("pipeline_url"))
        return res

    def _build_error_result(
        self,
        job_id: int,
        saved_path: Path,
        error: Exception,
        debug_info: dict,
        classification=None,
        elapsed: float | None = None,
    ) -> dict:
        """Build a standardized error response dict."""
        if elapsed is not None:
            self.job_store.update_job(job_id, status="FAILED", extraction_time=elapsed)
        else:
            self.job_store.update_job(job_id, status="FAILED")

        result: dict = {
            "job_id": job_id,
            "file_name": saved_path.name,
            "status": "FAILED",
            "error": str(error),
            "pdf_traits": debug_info.get("pdf_traits", []),
        }
        if classification:
            result["document_type"] = classification.document_type.value
            result["pipeline"] = classification.pipeline.value
            result["classification_tier"] = classification.tier
            result["confidence"] = classification.confidence
            result["pipeline_url"] = build_pipeline_url(classification.pipeline)

        self.job_store.update_job(job_id, pipeline_url=result.get("pipeline_url"))
        return result

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

        # Available export formats
        result["available_outputs"] = list_available_outputs(path.parent, path.stem)

        # Pipeline UI URL
        remote_file = None
        if pipeline_result and isinstance(pipeline_result.get("response"), dict):
            remote_file = pipeline_result["response"].get("filename")
        result["pipeline_url"] = build_pipeline_url(classification.pipeline, remote_file or None)

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
