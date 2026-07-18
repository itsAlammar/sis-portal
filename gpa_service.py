"""GPA calculation and academic standing on the 5.0 scale.

GPA = sum(grade_points * credit_hours) / sum(credit_hours), over completed
courses only, excluding W (withdrawn) and I (incomplete). grade_points come
from the grade_scale table (see database.GRADE_SCALE), so the whole scale
is data-driven.
"""

import sqlite3
from typing import Optional

from database import GPA_SCALE_MAX

# Standing thresholds on the 5.0 scale (common Saudi convention).
STANDING = [
    (4.50, {"en": "Excellent", "ar": "ممتاز"}),
    (3.75, {"en": "Very Good", "ar": "جيد جداً"}),
    (2.75, {"en": "Good", "ar": "جيد"}),
    (2.00, {"en": "Pass", "ar": "مقبول"}),
    (1.00, {"en": "Academic Probation", "ar": "إنذار أكاديمي"}),
    (0.00, {"en": "Academic Suspension", "ar": "فصل أكاديمي"}),
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
              AND e.grade NOT IN ('W', 'I') AND e.grade_points IS NOT NULL
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
        return round(quality_points / total_hours, 2)

    def calculate_term_gpa(self, student_id: int, term_id: int) -> Optional[float]:
        return self.calculate_gpa(student_id, term_id)

    def calculate_cumulative_gpa(self, student_id: int) -> Optional[float]:
        return self.calculate_gpa(student_id, term_id=None)

    def get_academic_standing(self, gpa: Optional[float], locale: str = "en") -> str:
        if gpa is None:
            return {"en": "No GPA yet", "ar": "لا يوجد معدل بعد"}[locale if locale in ("en", "ar") else "en"]
        for threshold, label in STANDING:
            if gpa >= threshold:
                return label.get(locale, label["en"])
        return STANDING[-1][1].get(locale, STANDING[-1][1]["en"])

    def get_earned_credit_hours(self, student_id: int) -> int:
        """Credit hours actually passed (grade above F is excluded only if
        F counts as fail; here F has points>1 on the 5-scale but is still a
        fail, so we exclude grades below the passing letter 'D')."""
        rows = self.conn.execute(
            """SELECT c.credit_hours FROM enrollments e
               JOIN sections sec ON sec.section_id = e.section_id
               JOIN courses c ON c.course_id = sec.course_id
               WHERE e.student_id = ? AND e.status = 'completed'
                 AND e.grade IS NOT NULL AND e.grade NOT IN ('F', 'W', 'I')""",
            (student_id,),
        ).fetchall()
        return sum(r["credit_hours"] for r in rows)

    def get_remaining_credit_hours(self, student_id: int) -> Optional[int]:
        """Hours left toward the student's major requirement (None if the
        student has no major set)."""
        row = self.conn.execute(
            """SELECT m.required_credit_hours AS req FROM students s
               JOIN majors m ON m.major_id = s.major_id
               WHERE s.student_id = ?""",
            (student_id,),
        ).fetchone()
        if row is None:
            return None
        return max(0, row["req"] - self.get_earned_credit_hours(student_id))

    @property
    def scale_max(self) -> float:
        return GPA_SCALE_MAX
