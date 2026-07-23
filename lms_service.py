"""Learning-management courses (الدورات التعليمية).

Distinct from academic courses (`course_service.py`): these are
training / learning offerings managed from the admin console and gated
by the `lms_enabled` setting. Content (lessons) is a later phase.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import LMSCourse

STATUSES = ("draft", "published", "archived")


class LMSService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_course(
        self, title: str, title_ar: str = "", code: str = "",
        description: str = "", description_ar: str = "", category: str = "",
        teacher_id: Optional[int] = None, status: str = "draft",
    ) -> LMSCourse:
        if not title.strip():
            raise ValidationError("Course title is required.")
        if status not in STATUSES:
            raise ValidationError("Status must be draft, published, or archived.")
        try:
            cur = self.conn.execute(
                """INSERT INTO lms_courses (code, title, title_ar, description,
                        description_ar, category, teacher_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code.strip().upper() or None, title.strip(), title_ar.strip() or None,
                 description.strip() or None, description_ar.strip() or None,
                 category.strip() or None, teacher_id, status,
                 datetime.now().isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"Course code '{code}' already exists.") from e
        self.conn.commit()
        return self.get_course(cur.lastrowid)

    def get_course(self, lms_course_id: int) -> LMSCourse:
        row = self.conn.execute(
            "SELECT * FROM lms_courses WHERE lms_course_id = ?", (lms_course_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No LMS course with id {lms_course_id}.")
        return LMSCourse.from_row(row)

    def list_courses(self, status: Optional[str] = None) -> List[LMSCourse]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM lms_courses WHERE status = ? ORDER BY created_at DESC, lms_course_id DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM lms_courses ORDER BY created_at DESC, lms_course_id DESC"
            ).fetchall()
        return [LMSCourse.from_row(r) for r in rows]

    def count(self, status: Optional[str] = None) -> int:
        if status:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM lms_courses WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM lms_courses").fetchone()
        return row["c"]

    def update_course(self, lms_course_id: int, **fields) -> LMSCourse:
        self.get_course(lms_course_id)
        allowed = {"code", "title", "title_ar", "description", "description_ar",
                   "category", "teacher_id", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in updates and updates["status"] not in STATUSES:
            raise ValidationError("Status must be draft, published, or archived.")
        if "title" in updates and not str(updates["title"]).strip():
            raise ValidationError("Course title is required.")
        if not updates:
            return self.get_course(lms_course_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        try:
            self.conn.execute(
                f"UPDATE lms_courses SET {set_clause} WHERE lms_course_id = ?",
                (*updates.values(), lms_course_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("Course code already exists.") from e
        self.conn.commit()
        return self.get_course(lms_course_id)

    def set_status(self, lms_course_id: int, status: str) -> LMSCourse:
        if status not in STATUSES:
            raise ValidationError("Status must be draft, published, or archived.")
        return self.update_course(lms_course_id, status=status)
