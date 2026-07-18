"""Business logic for managing students."""

import re
import sqlite3
from datetime import date
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Student

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_STATUSES = {"active", "suspended", "graduated", "withdrawn"}


class StudentService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- creation ---------------------------------------------------------
    def add_student(
        self, first_name: str, last_name: str, email: str,
        phone: str = "", date_of_birth: str = "", gender: str = "",
        program: str = "", department_id: Optional[int] = None,
        enrollment_date: Optional[str] = None,
    ) -> Student:
        if not first_name.strip() or not last_name.strip():
            raise ValidationError("First and last name are required.")
        if not EMAIL_RE.match(email or ""):
            raise ValidationError(f"'{email}' is not a valid email address.")

        enrollment_date = enrollment_date or date.today().isoformat()
        student_number = self._generate_student_number(enrollment_date[:4])
        created_at = date.today().isoformat()

        try:
            cur = self.conn.execute(
                """INSERT INTO students
                   (student_number, first_name, last_name, email, phone,
                    date_of_birth, gender, program, department_id,
                    enrollment_date, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (student_number, first_name.strip(), last_name.strip(), email.strip(),
                 phone, date_of_birth, gender, program, department_id,
                 enrollment_date, created_at),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"A student with email '{email}' already exists.") from e
        self.conn.commit()
        return self.get_student(cur.lastrowid)

    def _generate_student_number(self, year: str) -> str:
        prefix = f"S{year}"
        cur = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM students WHERE student_number LIKE ?",
            (f"{prefix}%",),
        )
        count = cur.fetchone()["cnt"]
        return f"{prefix}{count + 1:04d}"

    # -- reads --------------------------------------------------------------
    def get_student(self, student_id: int) -> Student:
        row = self.conn.execute(
            "SELECT * FROM students WHERE student_id = ?", (student_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No student with id {student_id}.")
        return Student.from_row(row)

    def get_student_by_number(self, student_number: str) -> Student:
        row = self.conn.execute(
            "SELECT * FROM students WHERE student_number = ?", (student_number,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No student with number '{student_number}'.")
        return Student.from_row(row)

    def list_students(
        self, status: Optional[str] = None,
        limit: Optional[int] = None, offset: int = 0,
    ) -> List[Student]:
        query = "SELECT * FROM students"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY last_name, first_name"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return [Student.from_row(r) for r in self.conn.execute(query, params).fetchall()]

    def count_students(self, status: Optional[str] = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM students WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()
        return row["c"]

    def search_students(self, query: str) -> List[Student]:
        like = f"%{query.strip()}%"
        rows = self.conn.execute(
            """SELECT * FROM students
               WHERE first_name LIKE ? OR last_name LIKE ?
                  OR email LIKE ? OR student_number LIKE ?
               ORDER BY last_name, first_name""",
            (like, like, like, like),
        ).fetchall()
        return [Student.from_row(r) for r in rows]

    # -- updates --------------------------------------------------------------
    def update_student(self, student_id: int, **fields) -> Student:
        self.get_student(student_id)  # raises if missing
        allowed = {
            "first_name", "last_name", "email", "phone", "date_of_birth",
            "gender", "program", "department_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_student(student_id)
        if "email" in updates and not EMAIL_RE.match(updates["email"]):
            raise ValidationError(f"'{updates['email']}' is not a valid email address.")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        try:
            self.conn.execute(
                f"UPDATE students SET {set_clause} WHERE student_id = ?",
                (*updates.values(), student_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("Email already in use by another student.") from e
        self.conn.commit()
        return self.get_student(student_id)

    def set_status(self, student_id: int, status: str) -> Student:
        if status not in VALID_STATUSES:
            raise ValidationError(f"Status must be one of {sorted(VALID_STATUSES)}.")
        self.get_student(student_id)
        self.conn.execute(
            "UPDATE students SET status = ? WHERE student_id = ?", (status, student_id)
        )
        self.conn.commit()
        return self.get_student(student_id)
