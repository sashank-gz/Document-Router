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
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create_job(self, file_name: str, route: str, status: str) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (file_name, route, status, created_at) VALUES (?, ?, ?, ?)",
                (file_name, route, status, created_at),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_job(self, job_id: int, route: Optional[str] = None, status: Optional[str] = None) -> None:
        updates = []
        params = []

        if route is not None:
            updates.append("route = ?")
            params.append(route)

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if not updates:
            return

        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"

        with self._connect() as conn:
            conn.execute(query, tuple(params))
            conn.commit()

    def list_jobs(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, file_name, route, status, created_at FROM jobs ORDER BY id DESC").fetchall()
        return [JobRecord(**dict(row)) for row in rows]

    def get_job(self, job_id: int) -> Optional[JobRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, file_name, route, status, created_at FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()

        return JobRecord(**dict(row)) if row else None
