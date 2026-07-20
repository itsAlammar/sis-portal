"""Exam scheduling: one midterm and one final slot per section.

Setting a slot again overwrites it (upsert), so the registrar can correct
dates freely. Conflict detection is advisory only -- overlapping exams are
flagged to the student, never blocked, per the owner's requirement.
"""

import sqlite3
from typing import List, Optional

from exceptions import NotFoundError, ValidationError

KINDS = ("midterm", "final")

_BASE_SELECT = """
    SELECT x.*, sec.section_number, sec.term_id, sec.teacher_id,
           c.course_code, c.title, c.title_ar
    FROM exam_schedule x
    JOIN sections sec ON sec.section_id = x.section_id
    JOIN courses c ON c.course_id = sec.course_id
"""


class ExamService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def set_exam(self, section_id: int, kind: str, date: str,
                 start_time: str = "", end_time: str = "", room: str = "") -> sqlite3.Row:
        if kind not in KINDS:
            raise ValidationError(f"Exam kind must be one of {list(KINDS)}.")
        if not (date or "").strip():
            raise ValidationError("Exam date is required.")
        exists = self.conn.execute(
            "SELECT 1 FROM sections WHERE section_id = ?", (section_id,)
        ).fetchone()
        if not exists:
            raise NotFoundError(f"No section with id {section_id}.")
        self.conn.execute(
            """INSERT INTO exam_schedule (section_id, kind, date, start_time, end_time, room)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(section_id, kind) DO UPDATE SET
                 date = excluded.date, start_time = excluded.start_time,
                 end_time = excluded.end_time, room = excluded.room""",
            (section_id, kind, date.strip(), start_time.strip() or None,
             end_time.strip() or None, room.strip() or None),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT * FROM exam_schedule WHERE section_id = ? AND kind = ?",
            (section_id, kind),
        ).fetchone()

    def delete_exam(self, exam_id: int) -> None:
        cur = self.conn.execute("DELETE FROM exam_schedule WHERE exam_id = ?", (exam_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"No exam with id {exam_id}.")
        self.conn.commit()

    def list_for_term(self, term_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            _BASE_SELECT + " WHERE sec.term_id = ? ORDER BY x.date, x.start_time, c.course_code",
            (term_id,),
        ).fetchall()

    def list_for_teacher(self, teacher_id: int, term_id: Optional[int] = None) -> List[sqlite3.Row]:
        query = _BASE_SELECT + " WHERE sec.teacher_id = ?"
        params = [teacher_id]
        if term_id:
            query += " AND sec.term_id = ?"
            params.append(term_id)
        return self.conn.execute(query + " ORDER BY x.date, x.start_time", params).fetchall()

    def list_for_student(self, student_id: int, term_id: Optional[int] = None) -> List[sqlite3.Row]:
        query = _BASE_SELECT + """
            JOIN enrollments e ON e.section_id = x.section_id
            WHERE e.student_id = ? AND e.status IN ('enrolled', 'completed')"""
        params = [student_id]
        if term_id:
            query += " AND sec.term_id = ?"
            params.append(term_id)
        return self.conn.execute(query + " ORDER BY x.date, x.start_time", params).fetchall()

    def conflicting_exam_ids(self, student_id: int, term_id: Optional[int] = None) -> set:
        """Exam ids of this student that clash: same date with overlapping
        times. A slot with missing times counts as all-day."""
        exams = self.list_for_student(student_id, term_id)
        conflicts = set()
        for i, a in enumerate(exams):
            for b in exams[i + 1:]:
                if a["date"] != b["date"]:
                    continue
                if self._overlaps(a, b):
                    conflicts.add(a["exam_id"])
                    conflicts.add(b["exam_id"])
        return conflicts

    @staticmethod
    def _overlaps(a: sqlite3.Row, b: sqlite3.Row) -> bool:
        if not (a["start_time"] and a["end_time"] and b["start_time"] and b["end_time"]):
            return True  # untimed slots block the whole day
        return a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]
