from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class JobRecord(BaseModel):
    id: int
    file_name: str
    route: str
    status: str
    created_at: str
    pipeline_url: Optional[str] = None
    document_type: Optional[str] = None
    classification_tier: Optional[str] = None
    debug_info: Optional[dict] = None
    available_outputs: list[str] = []


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
                    debug_info TEXT
                )
                """
            )
            conn.commit()

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

    def create_job(self, file_name: str, route: str, status: str, debug_info: Optional[str] = None, document_type: Optional[str] = None, classification_tier: Optional[str] = None) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (file_name, route, status, created_at, debug_info, document_type, classification_tier) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (file_name, route, status, created_at, debug_info, document_type, classification_tier),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_job(
        self,
        job_id: int,
        route: Optional[str] = None,
        status: Optional[str] = None,
        pipeline_url: Optional[str] = None,
        debug_info: Optional[str] = None,
        document_type: Optional[str] = None,
        classification_tier: Optional[str] = None,
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

        if not updates:
            return

        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"

        with self._connect() as conn:
            conn.execute(query, tuple(params))
            conn.commit()

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
            rows = conn.execute("SELECT id, file_name, route, status, created_at, pipeline_url, document_type, classification_tier, debug_info FROM jobs ORDER BY id DESC").fetchall()
        return [self._parse_row(row) for row in rows]

    def get_job(self, job_id: int) -> Optional[JobRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, file_name, route, status, created_at, pipeline_url, document_type, classification_tier, debug_info FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

        return self._parse_row(row) if row else None
