"""GPA calculation and academic standing."""

import sqlite3
from typing import Optional

STANDING_THRESHOLDS = [
    (3.5, "Dean's List"),
    (2.0, "Good Standing"),
    (1.0, "Academic Probation"),
    (0.0, "Academic Suspension"),
]


class GPAService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _completed_rows(self, student_id: int, term_id: Optional[int] = None):
        query = """
            SELECT e.grade_points, c.credit_hours
            FROM enrollments e
            JOIN sections sec ON sec.section_id = e.section_id
            JOIN courses c ON c.course_id = sec.course_id
            WHERE e.student_id = ? AND e.status = 'completed'
              AND e.grade NOT IN ('W', 'I')
        """
        params = [student_id]
        if term_id:
            query += " AND sec.term_id = ?"
            params.append(term_id)
        return self.conn.execute(query, params).fetchall()

    def calculate_gpa(self, student_id: int, term_id: Optional[int] = None) -> Optional[float]:
        rows = self._completed_rows(student_id, term_id)
        total_hours = sum(r["credit_hours"] for r in rows)
        if total_hours == 0:
            return None
        quality_points = sum(r["grade_points"] * r["credit_hours"] for r in rows)
        return round(quality_points / total_hours, 3)

    def calculate_term_gpa(self, student_id: int, term_id: int) -> Optional[float]:
        return self.calculate_gpa(student_id, term_id)

    def calculate_cumulative_gpa(self, student_id: int) -> Optional[float]:
        return self.calculate_gpa(student_id, term_id=None)

    def get_academic_standing(self, gpa: Optional[float]) -> str:
        if gpa is None:
            return "No GPA yet"
        for threshold, label in STANDING_THRESHOLDS:
            if gpa >= threshold:
                return label
        return STANDING_THRESHOLDS[-1][1]

    def get_earned_credit_hours(self, student_id: int) -> int:
        rows = self.conn.execute(
            """SELECT c.credit_hours FROM enrollments e
               JOIN sections sec ON sec.section_id = e.section_id
               JOIN courses c ON c.course_id = sec.course_id
               WHERE e.student_id = ? AND e.status = 'completed'
                 AND e.grade_points IS NOT NULL AND e.grade_points > 0""",
            (student_id,),
        ).fetchall()
        return sum(r["credit_hours"] for r in rows)
