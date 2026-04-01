"""
FastAPI application - Document Router Platform.

API endpoints for uploading PDFs, checking job status, and health.
"""

from __future__ import annotations

import html as html_mod
import json
import logging
from pathlib import Path
from string import Template as StringTemplate
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .file_service import build_pipeline_url, list_available_outputs
from .log_handler import JobStatusLogHandler, active_job_context
from .models import JobRecord, JobStore
from .router_engine import DocumentRouterEngine
from .utils import (
    highlight_json,
    resolve_processed_file,
    strip_uuid_prefix,
)

# Constants
MAX_PASSWORD_ATTEMPTS = 5


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
DB_PATH = BASE_DIR / "jobs.db"

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

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

job_store = JobStore(DB_PATH)
router_engine = DocumentRouterEngine(
    job_store=job_store,
    uploads_dir=UPLOADS_DIR,
    processed_dir=PROCESSED_DIR,
)

# Pipe terminal logs back to the database for active jobs
ui_handler = JobStatusLogHandler(job_store)
logging.getLogger().addHandler(ui_handler)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize local folders and database schema."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    job_store.initialize()

    # Log active LLM providers so the user knows what's configured

    providers = []
    if config.GROQ_ENABLED:
        providers.append(f"Groq ({config.GROQ_MODEL})")
    if config.GEMINI_ENABLED:
        providers.append(f"Gemini ({config.GEMINI_MODEL})")
    if providers:
        logger.info("LLM classification providers: %s", ", ".join(providers))
    else:
        logger.info("No LLM classification providers enabled - Tier 3 will be skipped")

    logger.info("Document Router Platform v2.0 started")


@app.post("/upload")
async def upload_documents(
    background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)
) -> dict:
    """Upload and process a batch of PDF files in the background."""
    from .file_service import save_upload_file

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    def process_job_with_context(job_id: int, saved_path: Path):
        token = active_job_context.set(job_id)
        try:
            router_engine._process_file(job_id, saved_path)
        finally:
            active_job_context.reset(token)

    jobs = []
    for file in files:
        saved_path = await save_upload_file(file, UPLOADS_DIR)
        job_id = job_store.create_job(
            file_name=saved_path.name,
            route="UNKNOWN",
            status="PROCESSING",
            debug_info=json.dumps({"logs": []}),
        )

        jobs.append({"job_id": job_id, "file_name": saved_path.name})

        # Enqueue the heavy lifting for the background pool
        background_tasks.add_task(process_job_with_context, job_id, saved_path)

    return {"count": len(jobs), "jobs": jobs}


class UnlockRequest(BaseModel):
    password: str


@app.post("/jobs/{job_id}/unlock")
def unlock_job(job_id: int, req: UnlockRequest, background_tasks: BackgroundTasks) -> dict:
    """Attempt to unlock a document job that requires a password."""
    import json

    from .security_utils import unlock_document

    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "REQUIRES_PASSWORD":
        raise HTTPException(status_code=400, detail="Job is not awaiting a password")

    debug_info = job.debug_info or {}
    attempts = debug_info.get("password_attempts", 0)

    if attempts >= MAX_PASSWORD_ATTEMPTS:
        raise HTTPException(
            status_code=400, detail="Maximum password attempts exceeded. Job failed permanently."
        )

    saved_path = UPLOADS_DIR / job.file_name
    success = unlock_document(saved_path, req.password)

    if success:
        # Mark as unlocked and process it
        debug_info["password_unlocked"] = True
        job_store.update_job(job_id, status="UPLOADED", debug_info=json.dumps(debug_info))

        def process_job_with_context_resume(j_id: int):
            token = active_job_context.set(j_id)
            try:
                router_engine.continue_processing(j_id)
            finally:
                active_job_context.reset(token)

        background_tasks.add_task(process_job_with_context_resume, job_id)
        return {"status": "ok", "message": "processing_resumed"}

    # Failed to unlock
    attempts += 1
    debug_info["password_attempts"] = attempts

    if attempts >= MAX_PASSWORD_ATTEMPTS:
        job_store.update_job(job_id, status="FAILED", debug_info=json.dumps(debug_info))
        raise HTTPException(
            status_code=400, detail="Maximum password attempts exceeded. Job failed permanently."
        )

    job_store.update_job(job_id, debug_info=json.dumps(debug_info))
    raise HTTPException(
        status_code=401,
        detail=f"Incorrect password. {MAX_PASSWORD_ATTEMPTS - attempts} attempts remaining.",
    )


def _enrich_job(job: JobRecord) -> JobRecord:
    """Add pipeline_url and available_outputs to a JobRecord."""
    if job.status == "COMPLETED" and not job.pipeline_url:
        from .document_types import Pipeline

        try:
            pipeline = Pipeline(job.route)
        except ValueError:
            pipeline = None
        if pipeline:
            job.pipeline_url = build_pipeline_url(pipeline, job.file_name)

    if job.file_name:
        job.available_outputs = list_available_outputs(PROCESSED_DIR, Path(job.file_name).stem)

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


@app.get("/jobs/{job_id}/logs")
def get_job_logs(job_id: int) -> dict:
    """Fetch terminal output logs for a job"""
    job = job_store.get_job(job_id)
    if job and job.debug_info:
        return {"logs": job.debug_info.get("logs", [])}
    return {"logs": []}


@app.get("/health")
def health_check() -> dict:
    """Simple health endpoint."""
    return {"status": "ok", "service": "document-router-platform", "version": "2.0.0"}


@app.get("/processed/{filename}")
def serve_processed_file(filename: str) -> FileResponse:
    """Serve a processed output file securely."""
    import mimetypes

    file_path = resolve_processed_file(PROCESSED_DIR, filename)
    mime_type, _ = mimetypes.guess_type(str(file_path))
    mime_type = mime_type or "application/octet-stream"

    # Whitelist of safe inline types
    safe_inline_types = [
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/json",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
    ]

    is_safe = mime_type in safe_inline_types or mime_type.startswith("text/")

    import urllib.parse

    safe_name = file_path.name.replace('"', "").replace("\r", "").replace("\n", "")
    encoded_name = urllib.parse.quote(file_path.name, safe="")

    if is_safe:
        disposition = f"inline; filename=\"{safe_name}\"; filename*=UTF-8''{encoded_name}"
    else:
        disposition = f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{encoded_name}"

    return FileResponse(
        file_path, media_type=mime_type, headers={"Content-Disposition": disposition}
    )


@app.get("/view/{filename}")
def view_processed_file(filename: str):
    """Serve a processed file (MD/JSON/HTML) wrapped in a styled viewer page."""
    file_path = resolve_processed_file(PROCESSED_DIR, filename)
    safe_filename = file_path.name

    content = file_path.read_text(encoding="utf-8", errors="replace")

    is_json = safe_filename.lower().endswith(".json")
    if is_json:
        try:
            content = json.dumps(json.loads(content), indent=2, ensure_ascii=False)
        except Exception:
            pass

    escaped = html_mod.escape(content)
    if is_json:
        escaped = highlight_json(escaped)

    display_name = strip_uuid_prefix(safe_filename)
    display_name_html = html_mod.escape(display_name)
    filename_encoded = quote(safe_filename, safe="")
    filename_html = html_mod.escape(filename_encoded)

    tpl_path = TEMPLATES_DIR / "viewer.html"
    tpl = StringTemplate(tpl_path.read_text(encoding="utf-8"))
    viewer_html = tpl.safe_substitute(
        display_name_html=display_name_html,
        filename_html=filename_html,
        content_html=escaped,
    )
    return HTMLResponse(content=viewer_html)


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve the frontend UI."""
    return FileResponse(STATIC_DIR / "index.html")
