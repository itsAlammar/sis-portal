"""Business logic for assigning grades to enrollments."""

import sqlite3
from typing import Dict, List

from exceptions import NotFoundError, ValidationError
from models import Enrollment


class GradingService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_grade_scale(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM grade_scale ORDER BY grade_points DESC").fetchall()

    def _grade_points(self, letter: str) -> float:
        row = self.conn.execute(
            "SELECT grade_points FROM grade_scale WHERE letter = ?", (letter,)
        ).fetchone()
        if row is None:
            valid = [r["letter"] for r in self.get_grade_scale()]
            raise ValidationError(f"'{letter}' is not a valid grade. Use one of: {valid}.")
        return row["grade_points"]

    def assign_grade(self, enrollment_id: int, letter_grade: str) -> Enrollment:
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE enrollment_id = ?", (enrollment_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No enrollment with id {enrollment_id}.")
        if row["status"] == "dropped":
            raise ValidationError("Cannot grade a dropped enrollment.")

        letter_grade = letter_grade.strip().upper()
        points = self._grade_points(letter_grade)
        self.conn.execute(
            "UPDATE enrollments SET grade = ?, grade_points = ?, status = 'completed' "
            "WHERE enrollment_id = ?",
            (letter_grade, points, enrollment_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE enrollment_id = ?", (enrollment_id,)
        ).fetchone()
        return Enrollment.from_row(row)

    def assign_grade_by_pair(self, student_id: int, section_id: int, letter_grade: str) -> Enrollment:
        row = self.conn.execute(
            "SELECT enrollment_id FROM enrollments WHERE student_id = ? AND section_id = ?",
            (student_id, section_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("No matching enrollment found for that student/section.")
        return self.assign_grade(row["enrollment_id"], letter_grade)

    def bulk_assign_grades(self, section_id: int, grades_by_student: Dict[int, str]) -> List[Enrollment]:
        return [
            self.assign_grade_by_pair(student_id, section_id, letter)
            for student_id, letter in grades_by_student.items()
        ]
