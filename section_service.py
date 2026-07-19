"""Business logic for managing course sections (a course offered in a term)."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Section

VALID_DAYS = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"}


class SectionService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_section(
        self, course_id: int, term_id: int, section_number: str,
        teacher_id: Optional[int] = None, gender: str = "male", room: str = "",
        days: str = "", start_time: str = "", end_time: str = "",
        capacity: int = 30,
    ) -> Section:
        if not section_number.strip():
            raise ValidationError("Section number is required.")
        if capacity <= 0:
            raise ValidationError("Capacity must be a positive number.")
        if gender not in ("male", "female"):
            raise ValidationError("Section gender must be male or female.")
        day_list = [d.strip().upper() for d in days.split(",") if d.strip()]
        for d in day_list:
            if d not in VALID_DAYS:
                raise ValidationError(f"'{d}' is not a valid day. Use: {sorted(VALID_DAYS)}.")
        try:
            cur = self.conn.execute(
                """INSERT INTO sections
                   (course_id, term_id, section_number, teacher_id, gender, room,
                    days, start_time, end_time, capacity, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
                (course_id, term_id, section_number.strip(), teacher_id, gender, room,
                 ",".join(day_list), start_time, end_time, capacity),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(
                f"Section '{section_number}' already exists for this course/term."
            ) from e
        self.conn.commit()
        return self.get_section(cur.lastrowid)

    def get_section(self, section_id: int) -> Section:
        row = self.conn.execute(
            "SELECT * FROM sections WHERE section_id = ?", (section_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No section with id {section_id}.")
        return Section.from_row(row)

    def list_sections(
        self, term_id: Optional[int] = None, course_id: Optional[int] = None,
        teacher_id: Optional[int] = None, gender: Optional[str] = None,
        limit: Optional[int] = None, offset: int = 0,
    ) -> List[Section]:
        clauses, params = self._filters(term_id, course_id, teacher_id, gender)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM sections {where} ORDER BY course_id, section_number"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        rows = self.conn.execute(query, params).fetchall()
        return [Section.from_row(r) for r in rows]

    def count_sections(
        self, term_id: Optional[int] = None, course_id: Optional[int] = None,
        teacher_id: Optional[int] = None, gender: Optional[str] = None,
    ) -> int:
        clauses, params = self._filters(term_id, course_id, teacher_id, gender)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.conn.execute(
            f"SELECT COUNT(*) AS c FROM sections {where}", params
        ).fetchone()["c"]

    @staticmethod
    def _filters(term_id, course_id, teacher_id, gender=None):
        clauses, params = [], []
        if term_id:
            clauses.append("term_id = ?")
            params.append(term_id)
        if course_id:
            clauses.append("course_id = ?")
            params.append(course_id)
        if teacher_id:
            clauses.append("teacher_id = ?")
            params.append(teacher_id)
        if gender:
            clauses.append("gender = ?")
            params.append(gender)
        return clauses, params

    def update_section(self, section_id: int, **fields) -> Section:
        self.get_section(section_id)
        allowed = {"teacher_id", "gender", "room", "days", "start_time", "end_time", "capacity", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_section(section_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE sections SET {set_clause} WHERE section_id = ?",
            (*updates.values(), section_id),
        )
        self.conn.commit()
        return self.get_section(section_id)

    def get_enrolled_count(self, section_id: int) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) AS cnt FROM enrollments
               WHERE section_id = ? AND status IN ('enrolled', 'completed')""",
            (section_id,),
        ).fetchone()
        return row["cnt"]

    def get_roster(self, section_id: int) -> List[sqlite3.Row]:
        """Raw joined rows (student + enrollment) -- a display concern,
        not a domain entity, so it skips the models layer."""
        return self.conn.execute(
            """SELECT s.student_id, s.student_number, s.first_name, s.last_name,
                      e.enrollment_id, e.status, e.grade, e.enrollment_date,
                      e.numeric_mark, e.coursework_mark, e.final_mark
               FROM enrollments e
               JOIN students s ON s.student_id = e.student_id
               WHERE e.section_id = ?
               ORDER BY s.last_name, s.first_name""",
            (section_id,),
        ).fetchall()

    @staticmethod
    def has_schedule_conflict(a: Section, b: Section) -> bool:
        if not a.days or not b.days:
            return False
        if not (set(a.days.split(",")) & set(b.days.split(","))):
            return False
        if not (a.start_time and a.end_time and b.start_time and b.end_time):
            return False
        return not (a.end_time <= b.start_time or b.end_time <= a.start_time)
