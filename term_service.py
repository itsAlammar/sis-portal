"""Business logic for managing academic terms (semesters)."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Term


class TermService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_term(
        self, name: str, start_date: str, end_date: str,
        add_deadline: Optional[str] = None, drop_deadline: Optional[str] = None,
    ) -> Term:
        if not name.strip():
            raise ValidationError("Term name is required.")
        if start_date >= end_date:
            raise ValidationError("Start date must be before end date.")
        try:
            cur = self.conn.execute(
                """INSERT INTO terms (name, start_date, end_date, is_current,
                                       add_deadline, drop_deadline)
                   VALUES (?, ?, ?, 0, ?, ?)""",
                (name.strip(), start_date, end_date, add_deadline or None, drop_deadline or None),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"A term named '{name}' already exists.") from e
        self.conn.commit()
        return self.get_term(cur.lastrowid)

    def update_term(self, term_id: int, **fields) -> Term:
        self.get_term(term_id)
        allowed = {"add_deadline", "drop_deadline", "start_date", "end_date"}
        # A field passed as "" or None means "clear it"; a field simply not
        # passed at all means "leave it alone" (it won't appear in `fields`).
        updates = {k: (v or None) for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_term(term_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE terms SET {set_clause} WHERE term_id = ?", (*updates.values(), term_id)
        )
        self.conn.commit()
        return self.get_term(term_id)

    def get_term(self, term_id: int) -> Term:
        row = self.conn.execute(
            "SELECT * FROM terms WHERE term_id = ?", (term_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No term with id {term_id}.")
        return Term.from_row(row)

    def list_terms(self) -> List[Term]:
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
