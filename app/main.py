"""
FastAPI application – Document Router Platform.

API endpoints for uploading PDFs, checking job status, and health.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


@app.get("/jobs", response_model=list[JobRecord])
def list_jobs() -> Iterable[JobRecord]:
    """Return all tracked jobs, newest first."""
    return job_store.list_jobs()


@app.get("/jobs/{job_id}", response_model=JobRecord)
def get_job(job_id: int) -> JobRecord:
    """Return a single job by ID."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/health")
def health_check() -> dict:
    """Simple health endpoint."""
    return {"status": "ok", "service": "document-router-platform", "version": "2.0.0"}


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve the frontend UI."""
    return FileResponse(STATIC_DIR / "index.html")
