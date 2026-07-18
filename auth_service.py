"""Authentication: staff accounts (admin / registrar / teacher) and
student portal passwords.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library so the
CLI keeps working without Flask installed. Stored format:
    pbkdf2$<iterations>$<salt-hex>$<hash-hex>
"""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Student, User

PBKDF2_ITERATIONS = 300_000
VALID_ROLES = {"admin", "registrar", "teacher"}
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


class AuthService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- staff accounts ---------------------------------------------------
    def create_user(
        self, username: str, password: str, role: str,
        teacher_id: Optional[int] = None,
    ) -> User:
        username = username.strip().lower()
        if not username:
            raise ValidationError("Username is required.")
        if role not in VALID_ROLES:
            raise ValidationError(f"Role must be one of {sorted(VALID_ROLES)}.")
        if role == "teacher":
            if not teacher_id:
                raise ValidationError("A teacher account must be linked to a teacher record.")
            exists = self.conn.execute(
                "SELECT 1 FROM teachers WHERE teacher_id = ?", (teacher_id,)
            ).fetchone()
            if not exists:
                raise NotFoundError(f"No teacher with id {teacher_id}.")
        else:
            teacher_id = None
        try:
            cur = self.conn.execute(
                """INSERT INTO users (username, password_hash, role, teacher_id, status, created_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (username, hash_password(password), role, teacher_id,
                 datetime.now().isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"A user named '{username}' already exists.") from e
        self.conn.commit()
        return self.get_user(cur.lastrowid)

    def get_user(self, user_id: int) -> User:
        row = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No user with id {user_id}.")
        return User.from_row(row)

    def get_user_by_username(self, username: str) -> Optional[User]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
        return User.from_row(row) if row else None

    def list_users(self) -> List[User]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [User.from_row(r) for r in rows]

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Returns the User on success, None on any failure (unknown
        username, wrong password, disabled account) -- deliberately the
        same outcome for each, so login errors don't leak which part failed."""
        user = self.get_user_by_username(username)
        if user is None or user.status != "active":
            # Burn a hash anyway so response timing doesn't reveal whether
            # the username exists.
            verify_password(password, hash_password("timing-equalizer"))
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def set_user_password(self, user_id: int, new_password: str) -> None:
        self.get_user(user_id)
        self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (hash_password(new_password), user_id),
        )
        self.conn.commit()

    def set_user_status(self, user_id: int, status: str) -> None:
        if status not in {"active", "disabled"}:
            raise ValidationError("Status must be 'active' or 'disabled'.")
        self.get_user(user_id)
        self.conn.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        self.conn.commit()

    def count_admins(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND status = 'active'"
        ).fetchone()["c"]

    # -- student portal passwords ------------------------------------------
    def authenticate_student(self, student_number: str, password: str) -> Optional[Student]:
        row = self.conn.execute(
            "SELECT * FROM students WHERE student_number = ?", (student_number.strip(),)
        ).fetchone()
        if row is None or not row["password_hash"]:
            verify_password(password, hash_password("timing-equalizer"))
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return Student.from_row(row)

    def student_has_password(self, student_number: str) -> Optional[bool]:
        """True/False for an existing student, None if no such student."""
        row = self.conn.execute(
            "SELECT password_hash FROM students WHERE student_number = ?",
            (student_number.strip(),),
        ).fetchone()
        if row is None:
            return None
        return bool(row["password_hash"])

    def activate_student(
        self, student_number: str, email: str, new_password: str
    ) -> Optional[Student]:
        """First-time portal activation: the student proves identity with
        the email on file, then chooses a password. Only works while no
        password is set -- after that, resets go through the registrar."""
        row = self.conn.execute(
            "SELECT * FROM students WHERE student_number = ? AND email = ?",
            (student_number.strip(), email.strip()),
        ).fetchone()
        if row is None or row["password_hash"]:
            return None
        self.conn.execute(
            "UPDATE students SET password_hash = ? WHERE student_id = ?",
            (hash_password(new_password), row["student_id"]),
        )
        self.conn.commit()
        return Student.from_row(row)

    def set_student_password(self, student_id: int, new_password: Optional[str]) -> None:
        """Registrar-side set/reset. Passing None clears the password so the
        student can re-activate with their email."""
        stored = hash_password(new_password) if new_password else None
        self.conn.execute(
            "UPDATE students SET password_hash = ? WHERE student_id = ?",
            (stored, student_id),
        )
        self.conn.commit()
