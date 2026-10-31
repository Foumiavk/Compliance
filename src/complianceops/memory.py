from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .domain import AssessmentResponse


class AuditMemoryStore:
    """Bounded prompt history with durable, transactional run and tool records."""

    def __init__(self, path: str | Path, max_events: int = 20) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self.path = Path(path)
        self.max_events = max_events
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL, actor TEXT NOT NULL,
                    content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_audit ON events(audit_id, id);
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_audit ON runs(audit_id, created_at);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def add_event(self, audit_id: str, actor: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO events(audit_id, actor, content, created_at) VALUES (?, ?, ?, ?)",
                (audit_id, actor, content, datetime.now(UTC).isoformat()),
            )

    def save_run(self, run: AssessmentResponse) -> None:
        now = datetime.now(UTC).isoformat()
        verified_summary = json.dumps({
            "run_id": run.run_id,
            "architecture": run.architecture,
            "findings": [item.model_dump() for item in run.findings],
            "proposal_ids": [item.proposal_id for item in run.proposals],
            "draft_id": run.draft.draft_id if run.draft else None,
            "executed": False,
            "published": False,
        })
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs(run_id, audit_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (run.run_id, run.audit_id, run.model_dump_json(), now),
            )
            connection.execute(
                "INSERT INTO events(audit_id, actor, content, created_at) VALUES (?, ?, ?, ?)",
                (run.audit_id, "verified_result", verified_summary, now),
            )

    def inspect(self, audit_id: str) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT actor, content, created_at FROM events WHERE audit_id = ? ORDER BY id DESC LIMIT ?",
                (audit_id, self.max_events),
            ).fetchall()
            count = connection.execute(
                "SELECT COUNT(*) FROM runs WHERE audit_id = ?", (audit_id,)
            ).fetchone()[0]
        return {"audit_id": audit_id, "run_count": count, "timeline": [dict(row) for row in reversed(rows)]}

    def get_run(self, audit_id: str, run_id: str) -> AssessmentResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM runs WHERE audit_id = ? AND run_id = ?", (audit_id, run_id)
            ).fetchone()
        return AssessmentResponse.model_validate_json(row["payload"]) if row else None

    def clear(self, audit_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM runs WHERE audit_id = ?", (audit_id,))
            connection.execute("DELETE FROM events WHERE audit_id = ?", (audit_id,))
