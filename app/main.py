"""
FastAPI application – Document Router Platform.

API endpoints for uploading PDFs, checking job status, and health.
"""

from __future__ import annotations

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

import logging
from pathlib import Path
from typing import Iterable, Optional
from . import config
from .document_types import Pipeline

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import JobRecord, JobStore
from .router_engine import DocumentRouterEngine

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
DB_PATH = BASE_DIR / "jobs.db"

STATIC_DIR = BASE_DIR / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("document-router")

app = FastAPI(title="Document Router Platform", version="2.0.0")

# Allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve processed output files downloading
app.mount("/processed", StaticFiles(directory=str(PROCESSED_DIR)), name="processed")

job_store = JobStore(DB_PATH)
router_engine = DocumentRouterEngine(
    job_store=job_store,
    uploads_dir=UPLOADS_DIR,
    processed_dir=PROCESSED_DIR,
)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize local folders and database schema."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    job_store.initialize()

    # Log active LLM providers so the user knows what's configured
    from . import config

    providers = []
    if config.GROQ_ENABLED:
        providers.append(f"Groq ({config.GROQ_MODEL})")
    if config.GEMINI_ENABLED:
        providers.append(f"Gemini ({config.GEMINI_MODEL})")
    if providers:
        logger.info("LLM classification providers: %s", ", ".join(providers))
    else:
        logger.info("No LLM classification providers enabled — Tier 3 will be skipped")

    logger.info("Document Router Platform v2.0 started")


@app.post("/upload")
async def upload_documents(files: list[UploadFile] = File(...)) -> dict:
    """Upload and process a batch of PDF files."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = []
    for file in files:
        result = await router_engine.process_upload(file)
        results.append(result)

    return {"count": len(results), "results": results}


class UnlockRequest(BaseModel):
    password: str

@app.post("/jobs/{job_id}/unlock")
def unlock_job(job_id: int, req: UnlockRequest) -> dict:
    """Attempt to unlock a PDF job that requires a password."""
    import json
    from .pdf_utils import unlock_pdf

    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "REQUIRES_PASSWORD":
        raise HTTPException(status_code=400, detail="Job is not awaiting a password")

    debug_info = job.debug_info or {}
    attempts = debug_info.get("password_attempts", 0)

    if attempts >= 5:
        raise HTTPException(status_code=400, detail="Maximum password attempts exceeded. Job failed permanently.")

    saved_path = UPLOADS_DIR / job.file_name
    success = unlock_pdf(saved_path, req.password)

    if success:
        # Mark as unlocked and process it
        debug_info["password_unlocked"] = True
        job_store.update_job(job_id, status="UPLOADED", debug_info=json.dumps(debug_info))
        return router_engine.continue_processing(job_id)

    # Failed to unlock
    attempts += 1
    debug_info["password_attempts"] = attempts

    if attempts >= 5:
        job_store.update_job(job_id, status="FAILED", debug_info=json.dumps(debug_info))
        raise HTTPException(status_code=400, detail="Maximum password attempts exceeded. Job failed permanently.")

    job_store.update_job(job_id, debug_info=json.dumps(debug_info))
    raise HTTPException(status_code=401, detail=f"Incorrect password. {5 - attempts} attempts remaining.")


def _enrich_job(job: JobRecord) -> JobRecord:
    """Add pipeline_url and available_outputs to a JobRecord."""
    if job.status == "COMPLETED" and not job.pipeline_url:
        if job.route == Pipeline.OCR.value:
            url = config.OCR_UI_URL
            sep = "&" if "?" in url else "?"
            job.pipeline_url = f"{url}{sep}file={job.file_name}"
        elif job.route == Pipeline.LLM.value:
            url = config.LLM_UI_URL
            sep = "&" if "?" in url else "?"
            job.pipeline_url = f"{url}{sep}file={job.file_name}"
            
    # Check for available Docling exports
    if job.file_name:
        stem = Path(job.file_name).stem
        outputs = []
        for ext in [".md", ".json", ".html"]:
            if (PROCESSED_DIR / f"{stem}{ext}").exists():
                outputs.append(ext[1:].upper())
        job.available_outputs = outputs
        
    return job


@app.get("/jobs", response_model=list[JobRecord])
def list_jobs() -> list[JobRecord]:
    """Return all tracked jobs, newest first."""
    jobs = job_store.list_jobs()
    return [_enrich_job(j) for j in jobs]


@app.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: int) -> JobRecord:
    """Return a single job by ID."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _enrich_job(job)


@app.get("/health")
def health_check() -> dict:
    """Simple health endpoint."""
    return {"status": "ok", "service": "document-router-platform", "version": "2.0.0"}


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve the frontend UI."""
    return FileResponse(STATIC_DIR / "index.html")
