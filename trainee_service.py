"""External trainees for the training-courses track.

Distinct from SIS students: self-registered, authenticate against their own
`trainees` table, and only ever see training (LMS) content — never SIS data.
Passwords use the shared PBKDF2 helpers in auth_service.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from auth_service import hash_password, verify_password
from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Trainee


class TraineeService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def register(self, full_name: str, email: str, password: str,
                 phone: str = "") -> Trainee:
        """Self-registration: create an active trainee with a hashed password."""
        if not full_name.strip():
            raise ValidationError("Full name is required.")
        email = email.strip().lower()
        if "@" not in email or "." not in email:
            raise ValidationError("A valid email is required.")
        # Password length is enforced by auth_service.hash_password (single source).
        try:
            cur = self.conn.execute(
                """INSERT INTO trainees (full_name, email, phone, password_hash,
                        status, created_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (full_name.strip(), email, phone.strip() or None,
                 hash_password(password), datetime.now().isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("An account with this email already exists.") from e
        self.conn.commit()
        return self.get_trainee(cur.lastrowid)

    def authenticate(self, email: str, password: str) -> Optional[Trainee]:
        row = self.conn.execute(
            "SELECT * FROM trainees WHERE email = ? AND status = 'active'",
            (email.strip().lower(),),
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return Trainee.from_row(row)
        return None

    def get_trainee(self, trainee_id: int) -> Trainee:
        row = self.conn.execute(
            "SELECT * FROM trainees WHERE trainee_id = ?", (trainee_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No trainee with id {trainee_id}.")
        return Trainee.from_row(row)

    def list_trainees(self) -> List[Trainee]:
        rows = self.conn.execute(
            "SELECT * FROM trainees ORDER BY created_at DESC, trainee_id DESC"
        ).fetchall()
        return [Trainee.from_row(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM trainees").fetchone()["c"]

    def set_status(self, trainee_id: int, status: str) -> Trainee:
        if status not in ("active", "suspended"):
            raise ValidationError("Status must be active or suspended.")
        self.get_trainee(trainee_id)
        self.conn.execute(
            "UPDATE trainees SET status = ? WHERE trainee_id = ?", (status, trainee_id)
        )
        self.conn.commit()
        return self.get_trainee(trainee_id)

    def set_password(self, trainee_id: int, new_password: str) -> None:
        self.get_trainee(trainee_id)
        self.conn.execute(
            "UPDATE trainees SET password_hash = ? WHERE trainee_id = ?",
            (hash_password(new_password), trainee_id),
        )
        self.conn.commit()
