"""Business logic for enrolling and dropping students from sections."""

import sqlite3
from datetime import date
from typing import List, Optional

from exceptions import (
    CapacityError, DeadlineError, DuplicateEnrollmentError, NotFoundError,
    PrerequisiteError, SISError, ScheduleConflictError, ValidationError,
)
from models import Enrollment
from course_service import CourseService
from section_service import SectionService
from student_service import StudentService
from term_service import TermService
from waitlist_service import WaitlistService


class EnrollmentService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.students = StudentService(conn)
        self.sections = SectionService(conn)
        self.courses = CourseService(conn)
        self.terms = TermService(conn)
        self.waitlist = WaitlistService(conn)

    def enroll_student(
        self, student_id: int, section_id: int, override_conflicts: bool = False,
        as_of: Optional[str] = None,
    ) -> Enrollment:
        student = self.students.get_student(student_id)
        if student.status != "active":
            raise ValidationError(
                f"{student.full_name} is not active (status: {student.status})."
            )

        section = self.sections.get_section(section_id)
        if section.status != "open":
            raise ValidationError(f"Section is not open for enrollment (status: {section.status}).")

        # Gender segregation: a student may only join a section of their own
        # gender. (Sections are single-gender by design.)
        if section.gender != student.gender:
            raise ValidationError("This section is not open to the student's gender.")

        self._check_add_deadline(section, as_of)

        # Duplicate/capacity check and the insert must be atomic: without an
        # exclusive write lock two concurrent enrollments could both pass the
        # capacity check and overfill the section (the DB's UNIQUE constraint
        # only guards duplicates, not capacity). BEGIN IMMEDIATE serializes
        # writers around the read-decide-write.
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self.conn.execute(
                "SELECT 1 FROM enrollments WHERE student_id = ? AND section_id = ?",
                (student_id, section_id),
            ).fetchone()
            if existing:
                raise DuplicateEnrollmentError(
                    f"{student.full_name} is already enrolled in this section."
                )

            if self.sections.get_enrolled_count(section_id) >= section.capacity:
                raise CapacityError("This section is at full capacity.")

            course = self.courses.get_course(section.course_id)
            self._check_prerequisites(student_id, course.course_id)

            if not override_conflicts:
                self._check_schedule_conflict(student_id, section)

            enrollment_date = date.today().isoformat()
            cur = self.conn.execute(
                """INSERT INTO enrollments (student_id, section_id, enrollment_date, status)
                   VALUES (?, ?, ?, 'enrolled')""",
                (student_id, section_id, enrollment_date),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.get_enrollment(cur.lastrowid)

    def enroll_or_waitlist(self, student_id: int, section_id: int):
        """Tries a normal enrollment; if the section is full, falls back to
        joining the waitlist instead of raising. Returns
        ('enrolled', Enrollment) or ('waitlisted', WaitlistEntry)."""
        try:
            return "enrolled", self.enroll_student(student_id, section_id)
        except CapacityError:
            entry = self.waitlist.join(student_id, section_id)
            return "waitlisted", entry

    def _check_add_deadline(self, section, as_of: Optional[str]) -> None:
        term = self.terms.get_term(section.term_id)
        if not term.add_deadline:
            return
        today = as_of or date.today().isoformat()
        if today > term.add_deadline:
            raise DeadlineError(
                f"The add deadline for {term.name} ({term.add_deadline}) has passed."
            )

    def _check_drop_deadline(self, section, as_of: Optional[str]) -> None:
        term = self.terms.get_term(section.term_id)
        if not term.drop_deadline:
            return
        today = as_of or date.today().isoformat()
        if today > term.drop_deadline:
            raise DeadlineError(
                f"The drop deadline for {term.name} ({term.drop_deadline}) has passed."
            )

    def _check_prerequisites(self, student_id: int, course_id: int) -> None:
        groups = self.courses.get_prerequisite_groups(course_id)
        if not groups:
            return
        completed_codes = {
            row["course_code"]
            for row in self.conn.execute(
                """SELECT DISTINCT c.course_code FROM enrollments e
                   JOIN sections sec ON sec.section_id = e.section_id
                   JOIN courses c ON c.course_id = sec.course_id
                   WHERE e.student_id = ? AND e.status = 'completed'
                     AND e.grade_points IS NOT NULL AND e.grade_points > 0""",
                (student_id,),
            ).fetchall()
        }
        unmet = [
            group for group in groups
            if not any(c.course_code in completed_codes for c in group)
        ]
        if unmet:
            descriptions = [" or ".join(c.course_code for c in group) for group in unmet]
            raise PrerequisiteError(f"Missing prerequisite(s): {'; '.join(descriptions)}.")

    def _check_schedule_conflict(self, student_id: int, new_section) -> None:
        rows = self.conn.execute(
            """SELECT sec.section_id FROM enrollments e
               JOIN sections sec ON sec.section_id = e.section_id
               WHERE e.student_id = ? AND e.status = 'enrolled' AND sec.term_id = ?""",
            (student_id, new_section.term_id),
        ).fetchall()
        for row in rows:
            other = self.sections.get_section(row["section_id"])
            if self.sections.has_schedule_conflict(new_section, other):
                raise ScheduleConflictError(
                    f"Schedule conflicts with section {other.section_number} "
                    f"(course id {other.course_id})."
                )

    def drop_student(
        self, student_id: int, section_id: int, as_of: Optional[str] = None,
        override_deadline: bool = False,
    ) -> Enrollment:
        enrollment = self._get_enrollment_by_pair(student_id, section_id)
        if enrollment.status != "enrolled":
            raise ValidationError(f"Cannot drop an enrollment with status '{enrollment.status}'.")

        if not override_deadline:
            section = self.sections.get_section(section_id)
            self._check_drop_deadline(section, as_of)

        self.conn.execute(
            "UPDATE enrollments SET status = 'dropped', grade = 'W', grade_points = 0 "
            "WHERE enrollment_id = ?",
            (enrollment.enrollment_id,),
        )
        self.conn.commit()
        self._promote_from_waitlist(section_id)
        return self.get_enrollment(enrollment.enrollment_id)

    def _promote_from_waitlist(self, section_id: int) -> Optional[Enrollment]:
        """After a seat opens up, offers it to the longest-waiting student.
        If they can no longer take it (e.g. went inactive meanwhile), they
        are skipped and the next person in line is tried."""
        while True:
            entry = self.waitlist.get_next_waiting(section_id)
            if entry is None:
                return None
            try:
                enrollment = self.enroll_student(entry.student_id, section_id)
            except SISError:
                self.waitlist.mark_status(entry.waitlist_id, "skipped")
                continue
            self.waitlist.mark_status(entry.waitlist_id, "promoted")
            return enrollment

    def get_enrollment(self, enrollment_id: int) -> Enrollment:
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE enrollment_id = ?", (enrollment_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No enrollment with id {enrollment_id}.")
        return Enrollment.from_row(row)

    def _get_enrollment_by_pair(self, student_id: int, section_id: int) -> Enrollment:
        row = self.conn.execute(
            "SELECT * FROM enrollments WHERE student_id = ? AND section_id = ?",
            (student_id, section_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("No matching enrollment found for that student/section.")
        return Enrollment.from_row(row)

    def list_student_enrollments(
        self, student_id: int, term_id: Optional[int] = None
    ) -> List[sqlite3.Row]:
        query = """SELECT e.*, c.course_code, c.title, c.title_ar, c.credit_hours, c.price,
                          c.coursework_max,
                          sec.section_number, sec.term_id, sec.gender AS section_gender,
                          sec.days, sec.start_time, sec.end_time, sec.room
                   FROM enrollments e
                   JOIN sections sec ON sec.section_id = e.section_id
                   JOIN courses c ON c.course_id = sec.course_id
                   WHERE e.student_id = ?"""
        params = [student_id]
        if term_id:
            query += " AND sec.term_id = ?"
            params.append(term_id)
        query += " ORDER BY sec.term_id, c.course_code"
        return self.conn.execute(query, params).fetchall()
