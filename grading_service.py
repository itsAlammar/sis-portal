"""Assigning grades to enrollments.

Grades are entered as a numeric mark out of 100. The letter and 5.0
grade points are looked up from the grade_scale table, so changing the
scale in one place (database.GRADE_SCALE) changes grading everywhere.
Direct letter entry (W, I, or an explicit letter) is still supported.
"""

import sqlite3
from typing import Dict, List

from exceptions import NotFoundError, ValidationError
from models import Enrollment


class GradingService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_grade_scale(self) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM grade_scale ORDER BY grade_points DESC, letter"
        ).fetchall()

    def letter_for_mark(self, mark: float) -> str:
        row = self.conn.execute(
            """SELECT letter FROM grade_scale
               WHERE min_percent IS NOT NULL AND max_percent IS NOT NULL
                 AND ? >= min_percent AND ? <= max_percent
               ORDER BY grade_points DESC LIMIT 1""",
            (mark, mark),
        ).fetchone()
        if row is None:
            raise ValidationError(f"No grade band covers a mark of {mark}.")
        return row["letter"]

    def _points(self, letter: str) -> float:
        row = self.conn.execute(
            "SELECT grade_points FROM grade_scale WHERE letter = ?", (letter,)
        ).fetchone()
        if row is None:
            valid = [r["letter"] for r in self.get_grade_scale()]
            raise ValidationError(f"'{letter}' is not a valid grade. Use one of: {valid}.")
        return row["grade_points"]

    def _apply(self, enrollment_id, numeric_mark, letter):
        points = self._points(letter)
        self.conn.execute(
            "UPDATE enrollments SET numeric_mark = ?, grade = ?, grade_points = ?, "
            "status = 'completed' WHERE enrollment_id = ?",
            (numeric_mark, letter, points, enrollment_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE enrollment_id = ?", (enrollment_id,)
        ).fetchone()
        return Enrollment.from_row(row)

    def _lookup(self, enrollment_id):
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE enrollment_id = ?", (enrollment_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No enrollment with id {enrollment_id}.")
        if row["status"] == "dropped":
            raise ValidationError("Cannot grade a dropped enrollment.")
        return row

    def assign_mark(self, enrollment_id: int, mark: float) -> Enrollment:
        self._lookup(enrollment_id)
        if mark < 0 or mark > 100:
            raise ValidationError("Mark must be between 0 and 100.")
        return self._apply(enrollment_id, mark, self.letter_for_mark(mark))

    def assign_grade(self, enrollment_id: int, letter_grade: str) -> Enrollment:
        """Assign an explicit letter (e.g. W/I, or a letter without a mark)."""
        self._lookup(enrollment_id)
        return self._apply(enrollment_id, None, letter_grade.strip().upper())

    def _enrollment_id(self, student_id, section_id):
        row = self.conn.execute(
            "SELECT enrollment_id FROM enrollments WHERE student_id = ? AND section_id = ?",
            (student_id, section_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("No matching enrollment found for that student/section.")
        return row["enrollment_id"]

    def assign_mark_by_pair(self, student_id: int, section_id: int, mark: float) -> Enrollment:
        return self.assign_mark(self._enrollment_id(student_id, section_id), mark)

    def assign_grade_by_pair(self, student_id: int, section_id: int, value: str) -> Enrollment:
        """Accepts either a numeric mark ('88') or a letter ('W'/'A+')."""
        value = value.strip().upper()
        eid = self._enrollment_id(student_id, section_id)
        try:
            mark = float(value)
        except ValueError:
            return self.assign_grade(eid, value)
        return self.assign_mark(eid, mark)

    def bulk_assign(self, section_id: int, marks_by_student: Dict[int, str]) -> List[Enrollment]:
        return [
            self.assign_grade_by_pair(sid, section_id, value)
            for sid, value in marks_by_student.items()
        ]
