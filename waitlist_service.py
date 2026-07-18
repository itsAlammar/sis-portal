"""Business logic for section waitlists.

This module only manages waitlist entries themselves (join, leave, list,
position). The decision to auto-promote someone off a waitlist happens in
EnrollmentService, which calls back into this service's simple accessors --
keeping the actual enrollment logic in exactly one place.
"""

import sqlite3
from datetime import date
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import WaitlistEntry


class WaitlistService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def join(self, student_id: int, section_id: int) -> WaitlistEntry:
        already_enrolled = self.conn.execute(
            "SELECT 1 FROM enrollments WHERE student_id = ? AND section_id = ? "
            "AND status IN ('enrolled', 'completed')",
            (student_id, section_id),
        ).fetchone()
        if already_enrolled:
            raise ValidationError("Already enrolled in this section -- no need to wait list.")
        try:
            cur = self.conn.execute(
                """INSERT INTO waitlist (student_id, section_id, joined_at, status)
                   VALUES (?, ?, ?, 'waiting')""",
                (student_id, section_id, date.today().isoformat()),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("Already on the waitlist for this section.") from e
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, waitlist_id: int) -> WaitlistEntry:
        row = self.conn.execute(
            "SELECT * FROM waitlist WHERE waitlist_id = ?", (waitlist_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No waitlist entry with id {waitlist_id}.")
        return WaitlistEntry.from_row(row)

    def leave(self, student_id: int, section_id: int) -> None:
        self.conn.execute(
            "UPDATE waitlist SET status = 'cancelled' "
            "WHERE student_id = ? AND section_id = ? AND status = 'waiting'",
            (student_id, section_id),
        )
        self.conn.commit()

    def list_for_section(self, section_id: int) -> List[sqlite3.Row]:
        """Raw joined rows (student + position) in join order, waiting only."""
        return self.conn.execute(
            """SELECT w.*, s.student_number, s.first_name, s.last_name,
                      ROW_NUMBER() OVER (ORDER BY w.joined_at, w.waitlist_id) AS position
               FROM waitlist w
               JOIN students s ON s.student_id = w.student_id
               WHERE w.section_id = ? AND w.status = 'waiting'
               ORDER BY w.joined_at, w.waitlist_id""",
            (section_id,),
        ).fetchall()

    def list_for_student(self, student_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            """SELECT w.*, c.course_code, c.title, sec.section_number, t.name AS term_name
               FROM waitlist w
               JOIN sections sec ON sec.section_id = w.section_id
               JOIN courses c ON c.course_id = sec.course_id
               JOIN terms t ON t.term_id = sec.term_id
               WHERE w.student_id = ? AND w.status = 'waiting'
               ORDER BY w.joined_at""",
            (student_id,),
        ).fetchall()

    def get_position(self, student_id: int, section_id: int) -> Optional[int]:
        for row in self.list_for_section(section_id):
            if row["student_id"] == student_id:
                return row["position"]
        return None

    def get_next_waiting(self, section_id: int) -> Optional[WaitlistEntry]:
        row = self.conn.execute(
            """SELECT * FROM waitlist WHERE section_id = ? AND status = 'waiting'
               ORDER BY joined_at, waitlist_id LIMIT 1""",
            (section_id,),
        ).fetchone()
        return WaitlistEntry.from_row(row) if row else None

    def mark_status(self, waitlist_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE waitlist SET status = ? WHERE waitlist_id = ?", (status, waitlist_id)
        )
        self.conn.commit()
