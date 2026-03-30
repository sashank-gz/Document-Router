"""
Logging handler that streams processing logs to the job database.

Captures relevant log messages from Docling, RapidOCR, and the
document-router pipeline, then persists them as part of each job's
debug_info for real-time display in the frontend UI.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

active_job_context: ContextVar[int | None] = ContextVar("active_job", default=None)
_in_log_handler: ContextVar[bool] = ContextVar("in_log_handler", default=False)

# Cap retained log lines per job to avoid unbounded growth
MAX_LOG_ENTRIES = 200


class JobStatusLogHandler(logging.Handler):
    """Logging handler that appends relevant log lines to the active job's DB record."""

    def __init__(self, job_store):
        super().__init__()
        self.job_store = job_store
        self.logger = logging.getLogger(__name__)

    def emit(self, record: logging.LogRecord) -> None:
        if _in_log_handler.get():
            return

        token = _in_log_handler.set(True)
        try:
            job_id = active_job_context.get()
            if job_id is None:
                return

            if record.levelno < logging.INFO:
                return

            name = record.name.lower()
            if not ("docling" in name or "rapidocr" in name or "document-router" in name):
                return

            msg = record.getMessage().strip()

            # Filter out generic HTTP logs and noise
            msg_lower = msg.lower()
            if "get /" in msg_lower or "post /" in msg_lower or "http/1.1" in msg_lower:
                return

            # Clean up model download/load paths for cleaner UI display
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

            # Skip redundant status updates already handled by router_engine
            if msg in ("COMPLETED", "FAILED", "REQUIRES_PASSWORD"):
                return

            try:
                job = self.job_store.get_job(job_id)
            except Exception as e:
                # Use sys.stderr or print if logger fails to avoid recursion loops
                print(f"ERROR: get_job failed for {job_id} in log_handler: {e}", file=sys.stderr)
                return

            if not job:
                return

            debug_info = job.debug_info or {}
            if isinstance(debug_info, str):
                try:
                    debug_info = json.loads(debug_info)
                except Exception:
                    debug_info = {}

            logs = debug_info.get("logs", [])
            if not isinstance(logs, list):
                logs = []

            logs.append(msg)
            # Enforce maximum retained log entries
            logs = logs[-MAX_LOG_ENTRIES:]
            debug_info["logs"] = logs

            try:
                payload = json.dumps(debug_info)
                self.job_store.update_job(job_id, debug_info=payload)
            except Exception as e:
                print(f"ERROR: update_job failed for {job_id} in log_handler: {e}", file=sys.stderr)
        finally:
            _in_log_handler.reset(token)
