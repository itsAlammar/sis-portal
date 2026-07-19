"""Business logic for academic years and terms (semesters)."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import AcademicYear, Term


class TermService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- academic years ---------------------------------------------------
    def add_year(self, name: str, name_ar: str = "") -> AcademicYear:
        if not name.strip():
            raise ValidationError("Academic year name is required.")
        try:
            cur = self.conn.execute(
                "INSERT INTO academic_years (name, name_ar) VALUES (?, ?)",
                (name.strip(), name_ar.strip() or None),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"Academic year '{name}' already exists.") from e
        self.conn.commit()
        return AcademicYear.from_row(
            self.conn.execute("SELECT * FROM academic_years WHERE year_id = ?",
                              (cur.lastrowid,)).fetchone()
        )

    def get_or_create_year(self, name: str, name_ar: str = "") -> AcademicYear:
        row = self.conn.execute(
            "SELECT * FROM academic_years WHERE name = ?", (name.strip(),)
        ).fetchone()
        if row:
            return AcademicYear.from_row(row)
        return self.add_year(name, name_ar)

    def list_years(self) -> List[AcademicYear]:
        rows = self.conn.execute("SELECT * FROM academic_years ORDER BY name DESC").fetchall()
        return [AcademicYear.from_row(r) for r in rows]

    def get_year(self, year_id: int) -> Optional[AcademicYear]:
        row = self.conn.execute(
            "SELECT * FROM academic_years WHERE year_id = ?", (year_id,)
        ).fetchone()
        return AcademicYear.from_row(row) if row else None

    # -- terms ------------------------------------------------------------
    def add_term(
        self, name: str, start_date: str, end_date: str,
        name_ar: str = "", academic_year_id: Optional[int] = None,
        kind: str = "regular",
        add_deadline: Optional[str] = None, drop_deadline: Optional[str] = None,
        grades_deadline: Optional[str] = None,
    ) -> Term:
        if not name.strip():
            raise ValidationError("Term name is required.")
        if start_date >= end_date:
            raise ValidationError("Start date must be before end date.")
        try:
            cur = self.conn.execute(
                """INSERT INTO terms (name, name_ar, academic_year_id, kind, start_date,
                                       end_date, is_current, add_deadline, drop_deadline,
                                       grades_deadline)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (name.strip(), name_ar.strip() or None, academic_year_id, kind,
                 start_date, end_date, add_deadline or None, drop_deadline or None,
                 grades_deadline or None),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"A term named '{name}' already exists.") from e
        self.conn.commit()
        return self.get_term(cur.lastrowid)

    def update_term(self, term_id: int, **fields) -> Term:
        self.get_term(term_id)
        allowed = {"add_deadline", "drop_deadline", "grades_deadline", "start_date",
                   "end_date", "name_ar", "academic_year_id", "kind"}
        updates = {k: (v if v != "" else None) for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_term(term_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE terms SET {set_clause} WHERE term_id = ?", (*updates.values(), term_id)
        )
        self.conn.commit()
        return self.get_term(term_id)

    def get_term(self, term_id: int) -> Term:
        row = self.conn.execute("SELECT * FROM terms WHERE term_id = ?", (term_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No term with id {term_id}.")
        return Term.from_row(row)

    def list_terms(self, academic_year_id: Optional[int] = None) -> List[Term]:
        if academic_year_id:
            rows = self.conn.execute(
                "SELECT * FROM terms WHERE academic_year_id = ? ORDER BY start_date",
                (academic_year_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM terms ORDER BY start_date").fetchall()
        return [Term.from_row(r) for r in rows]

    def set_current_term(self, term_id: int) -> Term:
        self.get_term(term_id)
        self.conn.execute("UPDATE terms SET is_current = 0")
        self.conn.execute("UPDATE terms SET is_current = 1 WHERE term_id = ?", (term_id,))
        self.conn.commit()
        return self.get_term(term_id)

    def get_current_term(self) -> Optional[Term]:
        row = self.conn.execute("SELECT * FROM terms WHERE is_current = 1").fetchone()
        return Term.from_row(row) if row else None
