"""Append-only audit trail: who did what, when, to which record.

Every state-changing action in the web app records an entry. The log is
never updated or deleted through the application -- it only grows.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional


class AuditService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(
        self, actor: str, action: str,
        entity_type: Optional[str] = None, entity_id: Optional[int] = None,
        details: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO audit_log (at, actor, action, entity_type, entity_id, details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(timespec="seconds"), actor, action,
             entity_type, entity_id, details),
        )
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]

    def list_entries(self, limit: int = 50, offset: int = 0) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
