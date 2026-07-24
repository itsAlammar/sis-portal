"""Learning-management courses (الدورات التعليمية).

Distinct from academic courses (`course_service.py`): these are
training / learning offerings managed from the admin console and gated
by the `lms_enabled` setting. Content (lessons) is a later phase.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import LMSCourse, LMSLesson, LMSSession

ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")

STATUSES = ("draft", "published", "archived")
DELIVERY_MODES = ("content", "session", "hybrid")


class LMSService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_course(
        self, title: str, title_ar: str = "", code: str = "",
        description: str = "", description_ar: str = "", category: str = "",
        teacher_id: Optional[int] = None, status: str = "draft",
        price: float = 0, delivery_mode: str = "content",
        require_content: int = 1, require_attendance_pct: int = 0,
        require_quiz_pass: int = 0,
    ) -> LMSCourse:
        if not title.strip():
            raise ValidationError("Course title is required.")
        if status not in STATUSES:
            raise ValidationError("Status must be draft, published, or archived.")
        if delivery_mode not in DELIVERY_MODES:
            raise ValidationError("Delivery mode must be content, session, or hybrid.")
        if price < 0:
            raise ValidationError("Price cannot be negative.")
        try:
            cur = self.conn.execute(
                """INSERT INTO lms_courses (code, title, title_ar, description,
                        description_ar, category, teacher_id, status, price,
                        delivery_mode, require_content, require_attendance_pct,
                        require_quiz_pass, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code.strip().upper() or None, title.strip(), title_ar.strip() or None,
                 description.strip() or None, description_ar.strip() or None,
                 category.strip() or None, teacher_id, status, price, delivery_mode,
                 int(require_content), int(require_attendance_pct), int(require_quiz_pass),
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
                   "category", "teacher_id", "status", "price", "delivery_mode",
                   "require_content", "require_attendance_pct", "require_quiz_pass"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in updates and updates["status"] not in STATUSES:
            raise ValidationError("Status must be draft, published, or archived.")
        if "delivery_mode" in updates and updates["delivery_mode"] not in DELIVERY_MODES:
            raise ValidationError("Delivery mode must be content, session, or hybrid.")
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

    # -- lessons (course content) ------------------------------------------
    def add_lesson(self, lms_course_id: int, title: str, title_ar: str = "",
                   body: str = "", link: str = "", sort_order: Optional[int] = None) -> LMSLesson:
        self.get_course(lms_course_id)
        if not title.strip():
            raise ValidationError("Lesson title is required.")
        if sort_order is None:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM lms_lessons WHERE lms_course_id = ?",
                (lms_course_id,),
            ).fetchone()
            sort_order = row["n"]
        cur = self.conn.execute(
            """INSERT INTO lms_lessons (lms_course_id, title, title_ar, body, link,
                    sort_order, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lms_course_id, title.strip(), title_ar.strip() or None,
             body.strip() or None, link.strip() or None, int(sort_order),
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_lesson(cur.lastrowid)

    def get_lesson(self, lms_lesson_id: int) -> LMSLesson:
        row = self.conn.execute(
            "SELECT * FROM lms_lessons WHERE lms_lesson_id = ?", (lms_lesson_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No lesson with id {lms_lesson_id}.")
        return LMSLesson.from_row(row)

    def list_lessons(self, lms_course_id: int) -> List[LMSLesson]:
        rows = self.conn.execute(
            "SELECT * FROM lms_lessons WHERE lms_course_id = ? ORDER BY sort_order, lms_lesson_id",
            (lms_course_id,),
        ).fetchall()
        return [LMSLesson.from_row(r) for r in rows]

    def delete_lesson(self, lms_lesson_id: int) -> None:
        self.get_lesson(lms_lesson_id)
        self.conn.execute("DELETE FROM lms_lessons WHERE lms_lesson_id = ?", (lms_lesson_id,))
        self.conn.commit()

    # -- sessions (scheduled meetings) + attendance ------------------------
    def add_session(self, lms_course_id: int, session_date: str, title: str = "",
                    start_time: str = "", end_time: str = "", room: str = "",
                    link: str = "") -> LMSSession:
        self.get_course(lms_course_id)
        if not session_date.strip():
            raise ValidationError("Session date is required.")
        cur = self.conn.execute(
            """INSERT INTO lms_sessions (lms_course_id, title, session_date, start_time,
                    end_time, room, link, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (lms_course_id, title.strip() or None, session_date.strip(),
             start_time.strip() or None, end_time.strip() or None,
             room.strip() or None, link.strip() or None,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_session(cur.lastrowid)

    def get_session(self, lms_session_id: int) -> LMSSession:
        row = self.conn.execute(
            "SELECT * FROM lms_sessions WHERE lms_session_id = ?", (lms_session_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No session with id {lms_session_id}.")
        return LMSSession.from_row(row)

    def list_sessions(self, lms_course_id: int) -> List[LMSSession]:
        rows = self.conn.execute(
            "SELECT * FROM lms_sessions WHERE lms_course_id = ? "
            "ORDER BY session_date, start_time, lms_session_id",
            (lms_course_id,),
        ).fetchall()
        return [LMSSession.from_row(r) for r in rows]

    def delete_session(self, lms_session_id: int) -> None:
        self.get_session(lms_session_id)
        self.conn.execute("DELETE FROM lms_sessions WHERE lms_session_id = ?", (lms_session_id,))
        self.conn.commit()

    def record_attendance(self, lms_session_id: int, marks: dict) -> None:
        """Upsert attendance for a session: {trainee_id: status}."""
        self.get_session(lms_session_id)
        for trainee_id, status in marks.items():
            if status not in ATTENDANCE_STATUSES:
                raise ValidationError(f"Invalid attendance status: {status}.")
            self.conn.execute(
                """INSERT INTO lms_session_attendance (lms_session_id, trainee_id, status)
                   VALUES (?, ?, ?)
                   ON CONFLICT(lms_session_id, trainee_id) DO UPDATE SET status = excluded.status""",
                (lms_session_id, int(trainee_id), status),
            )
        self.conn.commit()

    def get_attendance(self, lms_session_id: int) -> dict:
        rows = self.conn.execute(
            "SELECT trainee_id, status FROM lms_session_attendance WHERE lms_session_id = ?",
            (lms_session_id,),
        ).fetchall()
        return {r["trainee_id"]: r["status"] for r in rows}

    def attendance_pct(self, lms_course_id: int, trainee_id: int) -> int:
        """Percentage of the course's sessions the trainee attended
        (present or late count as attended). 100 when there are no sessions."""
        total = self.conn.execute(
            "SELECT COUNT(*) AS c FROM lms_sessions WHERE lms_course_id = ?", (lms_course_id,)
        ).fetchone()["c"]
        if total == 0:
            return 100
        attended = self.conn.execute(
            """SELECT COUNT(*) AS c FROM lms_session_attendance a
               JOIN lms_sessions s ON s.lms_session_id = a.lms_session_id
               WHERE s.lms_course_id = ? AND a.trainee_id = ?
                 AND a.status IN ('present', 'late')""",
            (lms_course_id, trainee_id),
        ).fetchone()["c"]
        return round(attended * 100 / total)
