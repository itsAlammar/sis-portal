"""Majors / academic programs (التخصصات)."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Major


class MajorService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_major(
        self, code: str, name_en: str, name_ar: str,
        required_credit_hours: int = 120, department_id: Optional[int] = None,
        gender: str = "any",
    ) -> Major:
        if not code.strip() or not name_en.strip() or not name_ar.strip():
            raise ValidationError("Code and both names (EN/AR) are required.")
        if required_credit_hours <= 0:
            raise ValidationError("Required credit hours must be positive.")
        if gender not in ("male", "female", "any"):
            raise ValidationError("Gender must be male, female, or any.")
        try:
            cur = self.conn.execute(
                """INSERT INTO majors (code, name_en, name_ar, department_id,
                                        required_credit_hours, gender, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'active')""",
                (code.strip().upper(), name_en.strip(), name_ar.strip(),
                 department_id, required_credit_hours, gender),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"Major code '{code}' already exists.") from e
        self.conn.commit()
        return self.get_major(cur.lastrowid)

    def get_major(self, major_id: int) -> Major:
        row = self.conn.execute(
            "SELECT * FROM majors WHERE major_id = ?", (major_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No major with id {major_id}.")
        return Major.from_row(row)

    def list_majors(self, gender: Optional[str] = None, status: str = "active") -> List[Major]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if gender:
            # 'any' majors are open to all genders.
            clauses.append("(gender = ? OR gender = 'any')"); params.append(gender)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM majors {where} ORDER BY code", params
        ).fetchall()
        return [Major.from_row(r) for r in rows]

    def update_major(self, major_id: int, **fields) -> Major:
        self.get_major(major_id)
        allowed = {"name_en", "name_ar", "department_id", "required_credit_hours",
                   "gender", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_major(major_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE majors SET {set_clause} WHERE major_id = ?",
            (*updates.values(), major_id),
        )
        self.conn.commit()
        return self.get_major(major_id)
