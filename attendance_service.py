"""Attendance: per-section, per-date roll call recorded by the teacher.

Statuses: present, absent, late, excused. One row per
(section, student, date); re-recording the same date overwrites, so a
teacher can correct a mistake.
"""

import sqlite3
from datetime import date as date_cls
from typing import Dict, List, Optional

from exceptions import ValidationError

STATUSES = ("present", "absent", "late", "excused")


class AttendanceService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record_bulk(self, section_id: int, day: str, statuses: Dict[int, str],
                    recorded_by: str = "") -> int:
        if not day:
            day = date_cls.today().isoformat()
        count = 0
        for student_id, status in statuses.items():
            if status not in STATUSES:
                raise ValidationError(f"Invalid attendance status '{status}'.")
            self.conn.execute(
                """INSERT INTO attendance (section_id, student_id, date, status, recorded_by)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(section_id, student_id, date)
                   DO UPDATE SET status = excluded.status, recorded_by = excluded.recorded_by""",
                (section_id, student_id, day, status, recorded_by),
            )
            count += 1
        self.conn.commit()
        return count

    def for_section_date(self, section_id: int, day: str) -> Dict[int, str]:
        rows = self.conn.execute(
            "SELECT student_id, status FROM attendance WHERE section_id = ? AND date = ?",
            (section_id, day),
        ).fetchall()
        return {r["student_id"]: r["status"] for r in rows}

    def section_summary(self, section_id: int) -> Dict[int, Dict[str, int]]:
        """Per-student counts of each status for the section."""
        rows = self.conn.execute(
            """SELECT student_id, status, COUNT(*) AS n FROM attendance
               WHERE section_id = ? GROUP BY student_id, status""",
            (section_id,),
        ).fetchall()
        out: Dict[int, Dict[str, int]] = {}
        for r in rows:
            out.setdefault(r["student_id"], {}).update({r["status"]: r["n"]})
        return out

    def student_summary(self, student_id: int) -> List[sqlite3.Row]:
        """Per-course attendance counts for the student portal."""
        return self.conn.execute(
            """SELECT c.course_code, c.title, c.title_ar,
                      SUM(CASE WHEN a.status = 'absent' THEN 1 ELSE 0 END) AS absent,
                      SUM(CASE WHEN a.status = 'late' THEN 1 ELSE 0 END) AS late,
                      SUM(CASE WHEN a.status = 'excused' THEN 1 ELSE 0 END) AS excused,
                      COUNT(*) AS total
               FROM attendance a
               JOIN sections sec ON sec.section_id = a.section_id
               JOIN courses c ON c.course_id = sec.course_id
               WHERE a.student_id = ?
               GROUP BY sec.section_id ORDER BY c.course_code""",
            (student_id,),
        ).fetchall()

    def student_absences(self, student_id: int) -> List[sqlite3.Row]:
        """The student's individual absence/late records, newest first —
        the rows a portal excuse request can be raised against."""
        return self.conn.execute(
            """SELECT a.date, a.status, a.section_id, c.course_code, c.title, c.title_ar
               FROM attendance a
               JOIN sections sec ON sec.section_id = a.section_id
               JOIN courses c ON c.course_id = sec.course_id
               WHERE a.student_id = ? AND a.status IN ('absent', 'late')
               ORDER BY a.date DESC""",
            (student_id,),
        ).fetchall()

    def dates_for_section(self, section_id: int) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT date FROM attendance WHERE section_id = ? ORDER BY date DESC",
            (section_id,),
        ).fetchall()
        return [r["date"] for r in rows]
