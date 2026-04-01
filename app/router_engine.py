"""
Core routing workflow - orchestrates file save, classification, pipeline
dispatch, and job status tracking for each uploaded document.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import UploadFile

from . import config
from .classifier import classify_document
from .document_types import Pipeline
from .file_service import (
    build_pipeline_url,
    extract_document_raw_text,
    list_available_outputs,
    move_to_processed,
    save_upload_file,
)
from .file_utils import FileCategory, get_file_category
from .models import JobStore
from .pipeline_clients import PipelineError, send_to_llm_pipeline, send_to_ocr_pipeline

logger = logging.getLogger(__name__)


class DocumentRouterEngine:
    """Save -> Classify -> Route -> Track for each uploaded file (PDF, EMAIL, etc.)."""

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

    def _process_file(
        self, job_id: int, saved_path: Path, initial_debug_info: dict | None = None, depth: int = 0
    ) -> dict:
        """Internal synchronous method to run the classification and pipeline."""
        return self._process_file_internal(job_id, saved_path, initial_debug_info, depth)

    def continue_processing(self, job_id: int) -> dict:
        """Resume processing of a job (e.g. after password unlock)."""
        job = self.job_store.get_job(job_id)
        if not job:
            raise ValueError("Job not found")
        saved_path = self.uploads_dir / job.file_name

        from .file_utils import FileCategory, get_file_category

        category = get_file_category(saved_path)
        debug_info = {}
        if category == FileCategory.PDF:
            from .pdf_utils import analyze_pdf

            pdf_info = analyze_pdf(saved_path)
            debug_info["pdf_traits"] = pdf_info.get("traits", [])

        return self._process_file(job_id, saved_path, debug_info)

    def _update_job_status(self, job_id: int, status: str, **kwargs) -> None:
        """Helper to update job status and optionally other fields like debug_info."""
        if "debug_info" in kwargs and isinstance(kwargs["debug_info"], dict):
            kwargs["debug_info"] = json.dumps(kwargs["debug_info"])
        self.job_store.update_job(job_id, status=status, **kwargs)

    def _process_file_internal(
        self, job_id: int, saved_path: Path, initial_debug_info: dict | None = None, depth: int = 0
    ) -> dict:
        """Internal synchronous method to run the classification and pipeline."""

        start_time = time.time()
        debug_info = initial_debug_info or {}
        category = get_file_category(saved_path)
        debug_info["file_category"] = category.value

        try:
            from .security_utils import is_encrypted

            # Universal password check before any format-specific extraction
            if initial_debug_info is None and is_encrypted(saved_path):
                # If we detect a password, immediately pause routing
                self._update_job_status(
                    job_id,
                    status="REQUIRES_PASSWORD",
                    debug_info={"password_attempts": 0},
                )
                return {
                    "job_id": job_id,
                    "file_name": saved_path.name,
                    "status": "REQUIRES_PASSWORD",
                    "message": "The document is protected with a password.",
                }

            # 1. Pre-processing (Normalization, traits)
            saved_path, pre_proc_res = self._run_pre_processing(
                job_id, saved_path, debug_info, category, is_fresh=(initial_debug_info is None)
            )
            if pre_proc_res:
                return pre_proc_res

            # 2. Classification
            classification, cls_debug_info = self._classify_document_internal(saved_path)
            debug_info.update(cls_debug_info)

            # 3. Post-Classification Hooks (e.g. Email attachment recursion)
            self._handle_post_classification_hooks(job_id, saved_path, category, depth)

            # 4. Finalize job state before routing
            db_job = self.job_store.get_job(job_id)
            if db_job and db_job.debug_info:
                db_debug = db_job.debug_info
                if isinstance(db_debug, str):
                    try:
                        db_debug = json.loads(db_debug)
                    except json.JSONDecodeError:
                        db_debug = {}
                if isinstance(db_debug, dict) and "logs" in db_debug:
                    debug_info["logs"] = db_debug["logs"]

            self._update_job_status(
                job_id,
                status="CLASSIFIED",
                route=classification.pipeline.value,
                document_type=classification.document_type.value,
                classification_tier=classification.tier,
                debug_info=debug_info,
            )

            logger.info(
                "Classification complete: file=%s type=%s pipeline=%s score=%.2f",
                saved_path.name,
                classification.document_type.value,
                classification.pipeline.value,
                classification.score,
            )

            # 5. Route to pipeline
            return self._route(job_id, saved_path, classification, debug_info, start_time)

        except (PipelineError, Exception) as exc:
            elapsed = round(time.time() - start_time, 1)
            return self._handle_error(
                job_id,
                saved_path,
                exc,
                debug_info,
                classification=locals().get("classification"),
                elapsed=elapsed,
            )

    def _run_pre_processing(
        self,
        job_id: int,
        saved_path: Path,
        debug_info: dict,
        category: FileCategory,
        is_fresh: bool,
    ) -> tuple[Path, dict | None]:
        """Normalize file and detect traits if applicable."""
        if category == FileCategory.PDF:
            return self._analyze_pdf(job_id, saved_path, debug_info, is_fresh=is_fresh)

        # Non-PDF files skip traits/normalization for now
        debug_info["pdf_traits"] = []
        return saved_path, None

    def _classify_document_internal(self, saved_path: Path) -> tuple:
        """Centralized text extraction and classification logic."""
        return self._classify(saved_path, {})

    def _handle_post_classification_hooks(
        self, job_id: int, saved_path: Path, category: FileCategory, depth: int
    ) -> None:
        """Trigger side effects like email recursion."""
        if category == FileCategory.EMAIL and depth < config.EMAIL_MAX_RECURSION_DEPTH:
            self._handle_email_attachments(job_id, saved_path, depth + 1)

    def _handle_error(
        self,
        job_id: int,
        saved_path: Path,
        error: Exception,
        debug_info: dict,
        classification=None,
        elapsed: float | None = None,
    ) -> dict:
        """Centralized error handling for the routing engine."""
        log_msg = (
            "Pipeline processing failed" if isinstance(error, PipelineError) else "Routing failed"
        )
        logger.exception("%s: file=%s", log_msg, saved_path.name)

        return self._build_error_result(
            job_id, saved_path, error, debug_info, classification, elapsed
        )

    def _analyze_pdf(
        self,
        job_id: int,
        saved_path: Path,
        debug_info: dict,
        *,
        is_fresh: bool,
    ) -> tuple[Path, dict | None]:
        """Normalize PDF, detect traits, check encryption."""
        from .pdf_utils import analyze_pdf, normalize_pdf

        if not is_fresh:
            return saved_path, None

        saved_path = normalize_pdf(saved_path)

        if config.ENABLE_PDF_TRAITS:
            pdf_info = analyze_pdf(saved_path)
            traits = pdf_info.get("traits", [])
            debug_info["pdf_traits"] = traits
        else:
            debug_info["pdf_traits"] = []

        return saved_path, None

    def _classify(self, saved_path: Path, debug_info: dict) -> tuple:
        """Extract text and run the 3-tier classifier."""
        # Tier 2 classification now uses normalized raw text

        tier_2_text = extract_document_raw_text(saved_path)

        multi_page_text = None
        if config.GROQ_ENABLED or config.GEMINI_ENABLED:
            # For Tier 3, we still use full text (Docling-ready)
            multi_page_text = tier_2_text

        classification, cls_debug_info = classify_document(
            filename=saved_path.name,
            keyword_text=tier_2_text,
            llm_text=multi_page_text,
        )
        debug_info.update(cls_debug_info)
        return classification, debug_info

    def _handle_post_classification_hooks(
        self, job_id: int, saved_path: Path, category: FileCategory, depth: int
    ) -> None:
        """Trigger side effects like email recursion or archive expansion."""
        if depth >= config.EMAIL_MAX_RECURSION_DEPTH:
            return

        if category == FileCategory.EMAIL:
            self._handle_email_attachments(job_id, saved_path, depth + 1)
        elif category == FileCategory.ARCHIVE:
            self._handle_archive_extraction(job_id, saved_path, depth + 1)

    def _spawn_child_jobs(self, parent_job_id: int, file_paths: list[Path], depth: int) -> None:
        """Generic logic to create and process child jobs for attachments or extracted files."""
        from .file_utils import is_supported

        if not file_paths:
            return

        logger.info(
            "Spawning %d child jobs for parent job %d (depth %d)",
            len(file_paths),
            parent_job_id,
            depth,
        )

        for att_path in file_paths:
            if not is_supported(att_path):
                logger.warning("Skipping unsupported file: %s", att_path.name)
                continue

            # Create a new job for the child file
            child_job_id = self.job_store.create_job(
                file_name=att_path.name,
                route="UNKNOWN",
                status="UPLOADED",
                parent_job_id=parent_job_id,
            )

            logger.info("Spawning child job %d for file %s", child_job_id, att_path.name)
            # Process synchronously as we are already in a BackgroundTask context
            self._process_file(child_job_id, att_path, depth=depth)

    def _handle_email_attachments(self, parent_job_id: int, email_path: Path, depth: int) -> None:
        """Extract and spawn new jobs for email attachments."""
        from .extraction_handlers import extract_content

        try:
            category = get_file_category(email_path)
            res = extract_content(email_path, category)

            if res.attachments:
                self._spawn_child_jobs(parent_job_id, res.attachments, depth)

        except Exception as exc:
            logger.exception(
                "Failed to handle email attachments for job %d: %s", parent_job_id, exc
            )
            self._record_hook_error(parent_job_id, "attachment_error", exc)

    def _handle_archive_extraction(
        self, parent_job_id: int, archive_path: Path, depth: int
    ) -> None:
        """Extract and spawn new jobs for ZIP contents."""
        from .extraction_handlers import extract_content

        try:
            category = get_file_category(archive_path)
            res = extract_content(archive_path, category)

            if res.attachments:
                self._spawn_child_jobs(parent_job_id, res.attachments, depth)

        except Exception as exc:
            logger.exception("Failed to extract archive for job %d: %s", parent_job_id, exc)
            self._record_hook_error(parent_job_id, "archive_error", exc)

    def _record_hook_error(self, job_id: int, field_name: str, error: Exception) -> None:
        """Safely record a hook error into the job's debug_info."""
        try:
            job = self.job_store.get_job(job_id)
            debug_info = job.debug_info if job and job.debug_info else {}
            if isinstance(debug_info, str):
                try:
                    debug_info = json.loads(debug_info)
                except json.JSONDecodeError:
                    debug_info = {}
            if isinstance(debug_info, dict):
                debug_info[field_name] = str(error)
                self.job_store.update_job(job_id, debug_info=json.dumps(debug_info))
        except Exception as log_exc:
            logger.error("Failed to record hook error for job %d: %s", job_id, log_exc)

    def _route(
        self,
        job_id: int,
        saved_path: Path,
        classification,
        debug_info: dict,
        start_time: float,
    ) -> dict:
        """Dispatch to the appropriate pipeline and finalize the job."""
        self._update_job_status(job_id, status="ROUTED")

        pipeline_result = None
        message = None

        if classification.pipeline == Pipeline.MANUAL:
            message = "Routed to manual review queue"
        else:
            self._update_job_status(job_id, status="PROCESSING")
            if classification.pipeline == Pipeline.OCR:
                pipeline_result = send_to_ocr_pipeline(saved_path)
            else:
                pipeline_result = send_to_llm_pipeline(saved_path)

        processed_path = move_to_processed(saved_path, self.processed_dir)
        elapsed = round(time.time() - start_time, 1)

        res = self._build_result(
            job_id,
            processed_path,
            classification,
            message=message,
            pipeline_result=pipeline_result,
            debug_info=debug_info,
        )

        self._update_job_status(
            job_id,
            status="COMPLETED",
            extraction_time=elapsed,
            pipeline_url=res.get("pipeline_url"),
        )
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
        update_fields = {"extraction_time": elapsed} if elapsed is not None else {}

        result: dict = {
            "job_id": job_id,
            "file_name": saved_path.name,
            "status": "FAILED",
            "error": str(error),
            "pdf_traits": debug_info.get("pdf_traits", []),
        }

        if classification:
            result.update(
                {
                    "document_type": classification.document_type.value,
                    "pipeline": classification.pipeline.value,
                    "classification_tier": classification.tier,
                    "confidence": classification.score,
                    "pipeline_url": build_pipeline_url(classification.pipeline),
                }
            )

        self._update_job_status(
            job_id, status="FAILED", pipeline_url=result.get("pipeline_url"), **update_fields
        )
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
            "confidence": classification.score,
            "status": "COMPLETED",
            "available_outputs": list_available_outputs(path.parent, path.stem),
        }

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
