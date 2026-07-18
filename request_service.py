"""Student service requests: deferral, major transfer, exam deferral,
course equivalency, and other requests routed to staff for review.

This is the backbone of the "Other services" area. The workflow is
deliberately generic (kind + free-text details + review) so new request
types can be added without a schema change.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import NotFoundError, ValidationError
from models import ServiceRequest

KINDS = {"deferral", "major_transfer", "exam_deferral", "equivalency",
         "financial_aid", "other"}


class RequestService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def submit(self, student_id: int, kind: str, details: str = "") -> ServiceRequest:
        if kind not in KINDS:
            raise ValidationError(f"Unknown request type '{kind}'.")
        cur = self.conn.execute(
            """INSERT INTO service_requests (student_id, kind, details, status, created_at)
               VALUES (?, ?, ?, 'pending', ?)""",
            (student_id, kind, details.strip(), datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, request_id: int) -> ServiceRequest:
        row = self.conn.execute(
            "SELECT * FROM service_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No request with id {request_id}.")
        return ServiceRequest.from_row(row)

    def list_for_student(self, student_id: int) -> List[ServiceRequest]:
        rows = self.conn.execute(
            "SELECT * FROM service_requests WHERE student_id = ? ORDER BY created_at DESC",
            (student_id,),
        ).fetchall()
        return [ServiceRequest.from_row(r) for r in rows]

    def list_all(self, status: Optional[str] = None) -> List[sqlite3.Row]:
        """Joined with student for the staff review screen."""
        query = """SELECT sr.*, s.student_number, s.first_name, s.last_name, s.name_ar
                   FROM service_requests sr
                   JOIN students s ON s.student_id = sr.student_id"""
        params = []
        if status:
            query += " WHERE sr.status = ?"; params.append(status)
        query += " ORDER BY sr.created_at DESC"
        return self.conn.execute(query, params).fetchall()

    def count_pending(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM service_requests WHERE status = 'pending'"
        ).fetchone()["c"]

    def review(self, request_id: int, decision: str, reviewer: str, note: str = "") -> ServiceRequest:
        if decision not in ("approved", "rejected"):
            raise ValidationError("Decision must be approved or rejected.")
        self.get(request_id)
        self.conn.execute(
            """UPDATE service_requests SET status = ?, review_note = ?,
               reviewed_by = ?, reviewed_at = ? WHERE request_id = ?""",
            (decision, note.strip() or None, reviewer,
             datetime.now().isoformat(timespec="seconds"), request_id),
        )
        self.conn.commit()
        return self.get(request_id)
