"""
Job tracking models and SQLite persistence.

Provides ``JobRecord`` (Pydantic model) and ``JobStore`` (SQLite CRUD).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class JobRecord(BaseModel):
    id: int
    file_name: str
    route: str
    status: str
    created_at: str
    pipeline_url: str | None = None
    document_type: str | None = None
    classification_tier: str | None = None
    extraction_time: float | None = None
    debug_info: dict | None = None
    available_outputs: list[str] = []
    parent_job_id: int | None = None


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    route TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    pipeline_url TEXT,
                    document_type TEXT,
                    classification_tier TEXT,
                    extraction_time REAL,
                    debug_info TEXT,
                    parent_job_id INTEGER
                )
                """
            )
            conn.commit()

            # Migration for parent_job_id
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN parent_job_id INTEGER")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            # Quick migration for existing databases
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN pipeline_url TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN debug_info TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN document_type TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN classification_tier TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN extraction_time REAL")
                conn.commit()
            except sqlite3.OperationalError:
                pass

    def create_job(
        self,
        file_name: str,
        route: str,
        status: str,
        debug_info: str | None = None,
        document_type: str | None = None,
        classification_tier: str | None = None,
        extraction_time: float | None = None,
        parent_job_id: int | None = None,
    ) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (file_name, route, status, created_at, debug_info, document_type, classification_tier, extraction_time, parent_job_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_name,
                    route,
                    status,
                    created_at,
                    debug_info,
                    document_type,
                    classification_tier,
                    extraction_time,
                    parent_job_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_job(
        self,
        job_id: int,
        route: str | None = None,
        status: str | None = None,
        pipeline_url: str | None = None,
        debug_info: str | None = None,
        document_type: str | None = None,
        classification_tier: str | None = None,
        extraction_time: float | None = None,
    ) -> None:
        updates = []
        params = []

        if route is not None:
            updates.append("route = ?")
            params.append(route)

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if pipeline_url is not None:
            updates.append("pipeline_url = ?")
            params.append(pipeline_url)

        if debug_info is not None:
            updates.append("debug_info = ?")
            params.append(debug_info)

        if document_type is not None:
            updates.append("document_type = ?")
            params.append(document_type)

        if classification_tier is not None:
            updates.append("classification_tier = ?")
            params.append(classification_tier)

        if extraction_time is not None:
            updates.append("extraction_time = ?")
            params.append(extraction_time)

        if not updates:
            return

        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"

        with self._connect() as conn:
            conn.execute(query, tuple(params))
            conn.commit()

    def append_job_log(self, job_id: int, msg: str, max_entries: int = 200) -> None:
        """Atomically append a log message to a job's debug_info log list."""
        import json

        with self._connect() as conn:
            # Use BEGIN IMMEDIATE to lock the database for writing
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT debug_info FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    conn.rollback()
                    return

                debug_info_raw = row["debug_info"]
                try:
                    debug_info = json.loads(debug_info_raw) if debug_info_raw else {}
                except json.JSONDecodeError:
                    debug_info = {}

                logs = debug_info.get("logs", [])
                if not isinstance(logs, list):
                    logs = []

                logs.append(msg)
                logs = logs[-max_entries:]
                debug_info["logs"] = logs

                conn.execute(
                    "UPDATE jobs SET debug_info = ? WHERE id = ?",
                    (json.dumps(debug_info), job_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _parse_row(self, row) -> JobRecord:
        import json

        d = dict(row)
        if d.get("debug_info"):
            try:
                d["debug_info"] = json.loads(d["debug_info"])
            except json.JSONDecodeError:
                d["debug_info"] = {"raw": d["debug_info"]}
        return JobRecord(**d)

    def list_jobs(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, file_name, route, status, created_at, pipeline_url, document_type, classification_tier, extraction_time, debug_info, parent_job_id FROM jobs ORDER BY id DESC"
            ).fetchall()
        return [self._parse_row(row) for row in rows]

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, file_name, route, status, created_at, pipeline_url, document_type, classification_tier, extraction_time, debug_info, parent_job_id FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

        return self._parse_row(row) if row else None
