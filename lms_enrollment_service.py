"""Trainee enrollment in training courses: paid enrollment, staff payment
approval, and completion tracking."""

import sqlite3
from datetime import datetime
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import LMSEnrollment
from lms_service import LMSService
from payment_provider import get_provider


class LMSEnrollmentService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.courses = LMSService(conn)

    def enroll(self, trainee_id: int, lms_course_id: int,
               provider_name: str = "manual") -> LMSEnrollment:
        course = self.courses.get_course(lms_course_id)
        if course.status != "published":
            raise ValidationError("This course is not open for enrollment.")

        existing = self.conn.execute(
            "SELECT 1 FROM lms_enrollments WHERE trainee_id = ? AND lms_course_id = ?",
            (trainee_id, lms_course_id),
        ).fetchone()
        if existing:
            raise DuplicateError("You are already enrolled in this course.")

        provider = get_provider(provider_name)
        ref = provider.create_charge(course.price, description=course.title)
        # Free courses (price 0) or auto-settling providers open immediately.
        paid = provider.auto_settle or course.price <= 0
        cur = self.conn.execute(
            """INSERT INTO lms_enrollments (trainee_id, lms_course_id, amount,
                    payment_status, payment_ref, completion_status, enrolled_at)
               VALUES (?, ?, ?, ?, ?, 'in_progress', ?)""",
            (trainee_id, lms_course_id, course.price,
             "paid" if paid else "pending", ref,
             datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return self.get_enrollment(cur.lastrowid)

    def get_enrollment(self, lms_enrollment_id: int) -> LMSEnrollment:
        row = self.conn.execute(
            "SELECT * FROM lms_enrollments WHERE lms_enrollment_id = ?",
            (lms_enrollment_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No enrollment with id {lms_enrollment_id}.")
        return LMSEnrollment.from_row(row)

    def get_for(self, trainee_id: int, lms_course_id: int) -> Optional[LMSEnrollment]:
        row = self.conn.execute(
            "SELECT * FROM lms_enrollments WHERE trainee_id = ? AND lms_course_id = ?",
            (trainee_id, lms_course_id),
        ).fetchone()
        return LMSEnrollment.from_row(row) if row else None

    def list_for_trainee(self, trainee_id: int) -> List[LMSEnrollment]:
        rows = self.conn.execute(
            "SELECT * FROM lms_enrollments WHERE trainee_id = ? ORDER BY enrolled_at DESC",
            (trainee_id,),
        ).fetchall()
        return [LMSEnrollment.from_row(r) for r in rows]

    def list_for_course(self, lms_course_id: int) -> List[LMSEnrollment]:
        rows = self.conn.execute(
            "SELECT * FROM lms_enrollments WHERE lms_course_id = ? ORDER BY enrolled_at DESC",
            (lms_course_id,),
        ).fetchall()
        return [LMSEnrollment.from_row(r) for r in rows]

    def list_pending_payments(self) -> List[LMSEnrollment]:
        rows = self.conn.execute(
            "SELECT * FROM lms_enrollments WHERE payment_status = 'pending' ORDER BY enrolled_at",
        ).fetchall()
        return [LMSEnrollment.from_row(r) for r in rows]

    def mark_paid(self, lms_enrollment_id: int) -> LMSEnrollment:
        """Staff confirms a manual payment; opens access to the course."""
        self.get_enrollment(lms_enrollment_id)
        self.conn.execute(
            "UPDATE lms_enrollments SET payment_status = 'paid' WHERE lms_enrollment_id = ?",
            (lms_enrollment_id,),
        )
        self.conn.commit()
        return self.get_enrollment(lms_enrollment_id)

    def complete(self, lms_enrollment_id: int) -> LMSEnrollment:
        """Mark the course completed (MVP: content-based, requires payment).
        Later phases gate this on the course's attendance/quiz requirements."""
        enr = self.get_enrollment(lms_enrollment_id)
        if not enr.is_paid:
            raise ValidationError("Cannot complete an unpaid course.")
        self.conn.execute(
            "UPDATE lms_enrollments SET completion_status = 'completed', completed_at = ? "
            "WHERE lms_enrollment_id = ?",
            (datetime.now().isoformat(timespec="seconds"), lms_enrollment_id),
        )
        self.conn.commit()
        return self.get_enrollment(lms_enrollment_id)
