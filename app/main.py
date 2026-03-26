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
from contextvars import ContextVar
import json

active_job_context = ContextVar("active_job", default=None)

class JobStatusLogHandler(logging.Handler):
    def __init__(self, job_store):
        super().__init__()
        self.job_store = job_store

    def emit(self, record):
        job_id = active_job_context.get()
        if not job_id:
            return
        
        if record.levelno < logging.INFO:
            return
            
        name = record.name.lower()
        if not ("docling" in name or "rapidocr" in name or "document-router" in name):
            return
            
        msg = record.getMessage().strip()
        
        msg_lower = msg.lower()
        if "get /" in msg_lower or "post /" in msg_lower or "http/1.1" in msg_lower:
            return

        if "C:\\" in msg or "D:\\" in msg or "Downloading" in msg:
            if "File exists and is valid" in msg:
                model_name = msg.split("\\")[-1]
                msg = f"Verified model: {model_name}"
            elif "Using" in msg and ".onnx" in msg:
                model_name = msg.split("\\")[-1]
                msg = f"Loaded model: {model_name}"
            else:
                return

        if len(msg) > 90:
            msg = msg[:87] + "..."
            
        if msg in ("COMPLETED", "FAILED", "REQUIRES_PASSWORD"):
            return
            
        job = self.job_store.get_job(job_id)
        if not job:
            return
            
        debug_info = job.debug_info or {}
        logs = debug_info.get("logs", [])
        logs.append(msg)
        debug_info["logs"] = logs
        
        try:
            self.job_store.update_job(job_id, debug_info=json.dumps(debug_info))
        except Exception:
            pass

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


from fastapi import BackgroundTasks

@app.post("/upload")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...)
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
            file_name=saved_path.name, route="UNKNOWN", status="PROCESSING",
            debug_info=json.dumps({"logs": []})
        )
        
        jobs.append({"job_id": job_id, "file_name": saved_path.name})
        
        # Enqueue the heavy lifting for the background pool
        background_tasks.add_task(process_job_with_context, job_id, saved_path)

    return {"count": len(jobs), "jobs": jobs}


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


@app.get("/view/{filename}")
def view_processed_file(filename: str):
    """Serve a processed file (MD/JSON/HTML) wrapped in a styled viewer page."""
    from fastapi.responses import HTMLResponse

    file_path = PROCESSED_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    # Escape HTML entities so content renders as plain text
    import html as html_mod
    escaped = html_mod.escape(content)

    # Extract original name (strip UUID prefix)
    display_name = filename
    import re
    m = re.match(r'^[0-9a-f]{32}_(.+)$', filename, re.IGNORECASE)
    if m:
        display_name = m.group(1)

    viewer_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{html_mod.escape(display_name)}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0F1117;
            color: #E2E8F0;
            font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
            font-size: 13px;
            line-height: 1.6;
        }}
        .toolbar {{
            position: sticky; top: 0; z-index: 10;
            display: flex; align-items: center; justify-content: space-between;
            padding: 10px 20px;
            background: #1A1D28;
            border-bottom: 1px solid #2D3348;
        }}
        .toolbar-title {{
            font-weight: 600; font-size: 0.9rem; color: #A5B4FC;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }}
        .toolbar-actions a, .toolbar-actions button {{
            padding: 6px 14px; border-radius: 6px; font-size: 0.78rem;
            text-decoration: none; font-weight: 500; cursor: pointer; border: none;
        }}
        .btn-back {{
            background: #2D3348; color: #E2E8F0;
        }}
        .btn-back:hover {{ background: #3D4460; }}
        .btn-download {{
            background: #4F46E5; color: white; margin-left: 8px;
        }}
        .btn-download:hover {{ background: #4338CA; }}
        .content {{
            padding: 20px 24px;
            overflow-x: auto;
            white-space: pre;
        }}
    </style>
</head>
<body>
    <div class="toolbar">
        <span class="toolbar-title">{html_mod.escape(display_name)}</span>
        <div class="toolbar-actions">
            <a href="javascript:history.back()" class="btn-back">← Back</a>
            <a href="/processed/{html_mod.escape(filename)}" download class="btn-download">↓ Download</a>
        </div>
    </div>
    <div class="content">{escaped}</div>
</body>
</html>"""
    return HTMLResponse(content=viewer_html)


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve the frontend UI."""
    return FileResponse(STATIC_DIR / "index.html")
