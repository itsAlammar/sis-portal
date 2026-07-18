"""Business logic for managing courses, prerequisites, and instructors."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Course, Teacher


class CourseService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_course(
        self, course_code: str, title: str, credit_hours: int,
        title_ar: str = "", price: float = 0, department_id: Optional[int] = None,
        major_id: Optional[int] = None, description: str = "",
    ) -> Course:
        if not course_code.strip() or not title.strip():
            raise ValidationError("Course code and title are required.")
        if credit_hours <= 0:
            raise ValidationError("Credit hours must be a positive number.")
        if price < 0:
            raise ValidationError("Price cannot be negative.")
        try:
            cur = self.conn.execute(
                """INSERT INTO courses
                   (course_code, title, title_ar, credit_hours, price, department_id,
                    major_id, description, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (course_code.strip().upper(), title.strip(), title_ar.strip() or None,
                 credit_hours, price, department_id, major_id, description),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError(f"Course code '{course_code}' already exists.") from e
        self.conn.commit()
        return self.get_course(cur.lastrowid)

    def get_course(self, course_id: int) -> Course:
        row = self.conn.execute(
            "SELECT * FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No course with id {course_id}.")
        return Course.from_row(row)

    def get_course_by_code(self, course_code: str) -> Course:
        row = self.conn.execute(
            "SELECT * FROM courses WHERE course_code = ?", (course_code.strip().upper(),)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No course with code '{course_code}'.")
        return Course.from_row(row)

    def list_courses(
        self, department_id: Optional[int] = None, major_id: Optional[int] = None,
        limit: Optional[int] = None, offset: int = 0,
    ) -> List[Course]:
        clauses, params = [], []
        if department_id:
            clauses.append("department_id = ?"); params.append(department_id)
        if major_id:
            clauses.append("major_id = ?"); params.append(major_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM courses {where} ORDER BY course_code"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"; params += [limit, offset]
        return [Course.from_row(r) for r in self.conn.execute(query, params).fetchall()]

    def count_courses(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM courses").fetchone()["c"]

    def update_course(self, course_id: int, **fields) -> Course:
        self.get_course(course_id)
        allowed = {"title", "title_ar", "credit_hours", "price", "department_id",
                   "major_id", "description", "status"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_course(course_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE courses SET {set_clause} WHERE course_id = ?",
            (*updates.values(), course_id),
        )
        self.conn.commit()
        return self.get_course(course_id)

    # -- instructors (many teachers per course) ---------------------------
    def assign_teacher(self, course_id: int, teacher_id: int) -> None:
        self.get_course(course_id)
        try:
            self.conn.execute(
                "INSERT INTO course_teachers (course_id, teacher_id) VALUES (?, ?)",
                (course_id, teacher_id),
            )
        except sqlite3.IntegrityError:
            return  # already assigned -- idempotent
        self.conn.commit()

    def remove_teacher(self, course_id: int, teacher_id: int) -> None:
        self.conn.execute(
            "DELETE FROM course_teachers WHERE course_id = ? AND teacher_id = ?",
            (course_id, teacher_id),
        )
        self.conn.commit()

    def get_teachers(self, course_id: int) -> List[Teacher]:
        rows = self.conn.execute(
            """SELECT t.* FROM teachers t
               JOIN course_teachers ct ON ct.teacher_id = t.teacher_id
               WHERE ct.course_id = ? ORDER BY t.last_name, t.first_name""",
            (course_id,),
        ).fetchall()
        return [Teacher.from_row(r) for r in rows]

    # -- prerequisites (OR within a group, AND across groups) -------------
    def add_prerequisite(self, course_id, prerequisite_course_id, group_id=None) -> None:
        if course_id == prerequisite_course_id:
            raise ValidationError("A course cannot be its own prerequisite.")
        self.get_course(course_id)
        self.get_course(prerequisite_course_id)
        if group_id is None:
            group_id = self.conn.execute(
                "SELECT COALESCE(MAX(group_id), 0) + 1 AS n FROM course_prerequisites "
                "WHERE course_id = ?", (course_id,),
            ).fetchone()["n"]
        try:
            self.conn.execute(
                "INSERT INTO course_prerequisites (course_id, prerequisite_course_id, group_id) "
                "VALUES (?, ?, ?)", (course_id, prerequisite_course_id, group_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("That prerequisite is already set.") from e
        self.conn.commit()

    def add_prerequisite_group(self, course_id, prerequisite_course_ids) -> None:
        if len(prerequisite_course_ids) < 2:
            raise ValidationError("An alternative group needs at least two courses.")
        group_id = self.conn.execute(
            "SELECT COALESCE(MAX(group_id), 0) + 1 AS n FROM course_prerequisites "
            "WHERE course_id = ?", (course_id,),
        ).fetchone()["n"]
        for pid in prerequisite_course_ids:
            self.add_prerequisite(course_id, pid, group_id=group_id)

    def remove_prerequisite(self, course_id, prerequisite_course_id) -> None:
        self.conn.execute(
            "DELETE FROM course_prerequisites WHERE course_id = ? AND prerequisite_course_id = ?",
            (course_id, prerequisite_course_id),
        )
        self.conn.commit()

    def get_prerequisite_groups(self, course_id) -> List[List[Course]]:
        rows = self.conn.execute(
            """SELECT cp.group_id, c.* FROM courses c
               JOIN course_prerequisites cp ON cp.prerequisite_course_id = c.course_id
               WHERE cp.course_id = ? ORDER BY cp.group_id, c.course_code""",
            (course_id,),
        ).fetchall()
        groups = {}
        for r in rows:
            groups.setdefault(r["group_id"], []).append(Course.from_row(r))
        return list(groups.values())
