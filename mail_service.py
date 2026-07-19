"""Outgoing email for admissions notifications.

Behavior is controlled from admin Settings:
- email_enabled = 0  -> emails are NOT sent; they are recorded in email_log
  with status 'logged' so you can see exactly what WOULD have gone out.
- email_enabled = 1  -> sent via the configured SMTP server; success or
  failure is recorded in email_log either way.

The acceptance template lives in app_settings (acceptance_subject /
acceptance_body) and supports {name} {student_number} {major}
{national_id} {institution} placeholders.
"""

import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from typing import Optional

from database import get_setting


class MailService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _log(self, to, subject, body, kind, status, error=None) -> int:
        cur = self.conn.execute(
            """INSERT INTO email_log (to_address, subject, body, kind, status, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (to, subject, body, kind, status, error,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return cur.lastrowid

    def send(self, to: str, subject: str, body: str, kind: str = "") -> str:
        """Returns the resulting status: 'sent', 'logged', or 'failed'."""
        if get_setting(self.conn, "email_enabled", "0") != "1":
            self._log(to, subject, body, kind, "logged")
            return "logged"
        try:
            msg = EmailMessage()
            msg["From"] = get_setting(self.conn, "smtp_from", "") or get_setting(self.conn, "smtp_user", "")
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            host = get_setting(self.conn, "smtp_host", "")
            port = int(get_setting(self.conn, "smtp_port", "587") or 587)
            user = get_setting(self.conn, "smtp_user", "")
            password = get_setting(self.conn, "smtp_password", "")
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                if user:
                    server.login(user, password)
                server.send_message(msg)
            self._log(to, subject, body, kind, "sent")
            return "sent"
        except Exception as e:  # noqa: BLE001 - log any SMTP failure
            self._log(to, subject, body, kind, "failed", error=str(e))
            return "failed"

    def render_acceptance(self, student, major_name: Optional[str], locale: str = "ar"):
        """Fill the admin-editable acceptance template for a student."""
        institution = get_setting(
            self.conn,
            "institution_name_ar" if locale == "ar" else "institution_name_en", "",
        ) or get_setting(self.conn, "institution_name_en", "")
        values = {
            "name": student.name_ar or student.full_name,
            "student_number": student.student_number,
            "major": major_name or "—",
            "national_id": student.national_id or "—",
            "institution": institution,
        }
        subject = (get_setting(self.conn, "acceptance_subject", "") or "").format(**values)
        body = (get_setting(self.conn, "acceptance_body", "") or "").format(**values)
        return subject, body

    def send_acceptance(self, student, major_name: Optional[str]) -> str:
        subject, body = self.render_acceptance(student, major_name)
        return self.send(student.email, subject, body, kind="admission_acceptance")

    def list_log(self, limit: int = 50, offset: int = 0):
        return self.conn.execute(
            "SELECT * FROM email_log ORDER BY email_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM email_log").fetchone()["c"]
