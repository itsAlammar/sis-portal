"""Business logic for managing teachers (instructors)."""

import re
import sqlite3
from datetime import date
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Teacher

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_STATUSES = {"active", "inactive"}
VALID_GENDERS = {"male", "female"}


class TeacherService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_teacher(
        self, first_name: str, last_name: str, email: str,
        name_ar: str = "", gender: str = "male", phone: str = "",
        department_id: Optional[int] = None, title: str = "",
        hire_date: Optional[str] = None,
    ) -> Teacher:
        if not first_name.strip() or not last_name.strip():
            raise ValidationError("First and last name are required.")
        if not EMAIL_RE.match(email or ""):
            raise ValidationError(f"'{email}' is not a valid email address.")
        if gender not in VALID_GENDERS:
            raise ValidationError("Gender must be male or female.")

        hire_date = hire_date or date.today().isoformat()
        employee_number = self._generate_employee_number(hire_date[:4])
        created_at = date.today().isoformat()
        try:
            cur = self.conn.execute(
                """INSERT INTO teachers
                   (employee_number, first_name, last_name, name_ar, email, phone,
                    gender, department_id, title, hire_date, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (employee_number, first_name.strip(), last_name.strip(), name_ar.strip(),
                 email.strip(), phone, gender, department_id, title, hire_date, created_at),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"A teacher with email '{email}' already exists.") from e
        self.conn.commit()
        return self.get_teacher(cur.lastrowid)

    def _generate_employee_number(self, year: str) -> str:
        prefix = f"T{year}"
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM teachers WHERE employee_number LIKE ?", (f"{prefix}%",),
        ).fetchone()["c"]
        return f"{prefix}{count + 1:04d}"

    def get_teacher(self, teacher_id: int) -> Teacher:
        row = self.conn.execute(
            "SELECT * FROM teachers WHERE teacher_id = ?", (teacher_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No teacher with id {teacher_id}.")
        return Teacher.from_row(row)

    def list_teachers(
        self, status: Optional[str] = None, gender: Optional[str] = None,
        limit: Optional[int] = None, offset: int = 0,
    ) -> List[Teacher]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if gender:
            clauses.append("gender = ?"); params.append(gender)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM teachers {where} ORDER BY last_name, first_name"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"; params += [limit, offset]
        return [Teacher.from_row(r) for r in self.conn.execute(query, params).fetchall()]

    def count_teachers(self, status: Optional[str] = None) -> int:
        if status:
            return self.conn.execute(
                "SELECT COUNT(*) AS c FROM teachers WHERE status = ?", (status,)
            ).fetchone()["c"]
        return self.conn.execute("SELECT COUNT(*) AS c FROM teachers").fetchone()["c"]

    def search_teachers(self, query: str) -> List[Teacher]:
        like = f"%{query.strip()}%"
        rows = self.conn.execute(
            """SELECT * FROM teachers
               WHERE first_name LIKE ? OR last_name LIKE ? OR name_ar LIKE ?
                  OR email LIKE ? OR employee_number LIKE ?
               ORDER BY last_name, first_name""",
            (like, like, like, like, like),
        ).fetchall()
        return [Teacher.from_row(r) for r in rows]

    def update_teacher(self, teacher_id: int, **fields) -> Teacher:
        self.get_teacher(teacher_id)
        allowed = {"first_name", "last_name", "name_ar", "email", "phone",
                   "gender", "department_id", "title"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_teacher(teacher_id)
        if "email" in updates and not EMAIL_RE.match(updates["email"]):
            raise ValidationError(f"'{updates['email']}' is not a valid email address.")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        try:
            self.conn.execute(
                f"UPDATE teachers SET {set_clause} WHERE teacher_id = ?",
                (*updates.values(), teacher_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("Email already in use by another teacher.") from e
        self.conn.commit()
        return self.get_teacher(teacher_id)

    def set_status(self, teacher_id: int, status: str) -> Teacher:
        if status not in VALID_STATUSES:
            raise ValidationError(f"Status must be one of {sorted(VALID_STATUSES)}.")
        self.get_teacher(teacher_id)
        self.conn.execute(
            "UPDATE teachers SET status = ? WHERE teacher_id = ?", (status, teacher_id)
        )
        self.conn.commit()
        return self.get_teacher(teacher_id)
