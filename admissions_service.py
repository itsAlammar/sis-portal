"""Admissions: self-registration applications and their approval.

A prospective student submits an application (national ID, quad name in
Arabic + English, DOB, email, mobile, gender, nationality, chosen major).
It sits in `pending` until a registrar/admin reviews it. Approval creates
the actual student record, generates a university number, and links back
to the application; rejection records a note. Nothing self-activates.
"""

import re
import sqlite3
from datetime import date, datetime
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import AdmissionApplication
from student_service import StudentService

NATIONAL_ID_RE = re.compile(r"^\d{10}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdmissionsService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def submit_application(
        self, national_id: str, first_name: str, second_name: str, third_name: str,
        last_name: str, name_ar: str, email: str, phone: str, date_of_birth: str,
        gender: str, nationality: str, major_id: Optional[int] = None,
    ) -> AdmissionApplication:
        # Every field is mandatory (per requirement).
        fields = {
            "national ID": national_id, "first name": first_name,
            "second name": second_name, "third name": third_name,
            "last name": last_name, "Arabic name": name_ar, "email": email,
            "mobile": phone, "date of birth": date_of_birth,
            "gender": gender, "nationality": nationality,
        }
        for label, value in fields.items():
            if not value or not str(value).strip():
                raise ValidationError(f"The {label} field is required.")
        if not NATIONAL_ID_RE.match(national_id.strip()):
            raise ValidationError("National ID must be exactly 10 digits.")
        if not EMAIL_RE.match(email.strip()):
            raise ValidationError("Please enter a valid email address.")
        if gender not in ("male", "female"):
            raise ValidationError("Gender must be male or female.")

        # Reject a duplicate that is already a student or has a pending app.
        if self.conn.execute("SELECT 1 FROM students WHERE national_id = ?",
                             (national_id.strip(),)).fetchone():
            raise DuplicateError("A student with this national ID already exists.")
        if self.conn.execute(
            "SELECT 1 FROM admission_applications WHERE national_id = ? AND status = 'pending'",
            (national_id.strip(),),
        ).fetchone():
            raise DuplicateError("An application with this national ID is already pending review.")

        cur = self.conn.execute(
            """INSERT INTO admission_applications
               (national_id, first_name, second_name, third_name, last_name, name_ar,
                email, phone, date_of_birth, gender, nationality, major_id,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (national_id.strip(), first_name.strip(), second_name.strip(),
             third_name.strip(), last_name.strip(), name_ar.strip(), email.strip(),
             phone.strip(), date_of_birth, gender, nationality.strip(), major_id,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_application(cur.lastrowid)

    def get_application(self, application_id: int) -> AdmissionApplication:
        row = self.conn.execute(
            "SELECT * FROM admission_applications WHERE application_id = ?", (application_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No application with id {application_id}.")
        return AdmissionApplication.from_row(row)

    def list_applications(self, status: Optional[str] = "pending") -> List[AdmissionApplication]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM admission_applications WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM admission_applications ORDER BY created_at DESC"
            ).fetchall()
        return [AdmissionApplication.from_row(r) for r in rows]

    def count_pending(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) AS c FROM admission_applications WHERE status = 'pending'"
        ).fetchone()["c"]

    def approve(self, application_id: int, reviewer: str, temp_password: Optional[str] = None):
        """Create the student, issue a university number, activate portal
        access with a temporary password (returned so it can be shown once)."""
        app = self.get_application(application_id)
        if app.status != "pending":
            raise ValidationError(f"Application already {app.status}.")

        students = StudentService(self.conn)
        student = students.add_student(
            first_name=app.first_name, second_name=app.second_name,
            third_name=app.third_name, last_name=app.last_name, name_ar=app.name_ar,
            national_id=app.national_id, email=app.email, phone=app.phone,
            date_of_birth=app.date_of_birth, gender=app.gender,
            nationality=app.nationality, major_id=app.major_id,
        )
        # Portal password: caller supplies one, else default to national ID.
        from auth_service import AuthService
        AuthService(self.conn).set_student_password(
            student.student_id, temp_password or app.national_id
        )
        self.conn.execute(
            """UPDATE admission_applications
               SET status = 'approved', student_id = ?, reviewed_by = ?, reviewed_at = ?
               WHERE application_id = ?""",
            (student.student_id, reviewer, datetime.now().isoformat(timespec="seconds"),
             application_id),
        )
        self.conn.commit()
        return student

    def reject(self, application_id: int, reviewer: str, note: str = "") -> None:
        app = self.get_application(application_id)
        if app.status != "pending":
            raise ValidationError(f"Application already {app.status}.")
        self.conn.execute(
            """UPDATE admission_applications
               SET status = 'rejected', review_note = ?, reviewed_by = ?, reviewed_at = ?
               WHERE application_id = ?""",
            (note.strip() or None, reviewer, datetime.now().isoformat(timespec="seconds"),
             application_id),
        )
        self.conn.commit()
