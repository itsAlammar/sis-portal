"""Business logic for managing courses and their prerequisites."""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError
from models import Course


class CourseService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_course(
        self, course_code: str, title: str, credit_hours: int,
        department_id: Optional[int] = None, description: str = "",
    ) -> Course:
        if not course_code.strip() or not title.strip():
            raise ValidationError("Course code and title are required.")
        if credit_hours <= 0:
            raise ValidationError("Credit hours must be a positive number.")
        try:
            cur = self.conn.execute(
                """INSERT INTO courses
                   (course_code, title, credit_hours, department_id, description, status)
                   VALUES (?, ?, ?, ?, ?, 'active')""",
                (course_code.strip().upper(), title.strip(), credit_hours,
                 department_id, description),
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
        self, department_id: Optional[int] = None,
        limit: Optional[int] = None, offset: int = 0,
    ) -> List[Course]:
        query = "SELECT * FROM courses"
        params: list = []
        if department_id:
            query += " WHERE department_id = ?"
            params.append(department_id)
        query += " ORDER BY course_code"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return [Course.from_row(r) for r in self.conn.execute(query, params).fetchall()]

    def count_courses(self, department_id: Optional[int] = None) -> int:
        if department_id:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM courses WHERE department_id = ?", (department_id,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM courses").fetchone()
        return row["c"]

    def update_course(self, course_id: int, **fields) -> Course:
        self.get_course(course_id)
        allowed = {"title", "credit_hours", "department_id", "description", "status"}
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

    # -- prerequisites ----------------------------------------------------
    # Prerequisites are modeled as "groups": within a group, completing ANY
    # ONE course satisfies it (OR). ALL groups must be satisfied (AND).
    # A plain add_prerequisite() call creates its own single-course group,
    # so simple "must complete X" requirements work exactly as before.
    def add_prerequisite(
        self, course_id: int, prerequisite_course_id: int, group_id: Optional[int] = None
    ) -> None:
        if course_id == prerequisite_course_id:
            raise ValidationError("A course cannot be its own prerequisite.")
        self.get_course(course_id)
        self.get_course(prerequisite_course_id)
        if group_id is None:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(group_id), 0) + 1 AS next FROM course_prerequisites "
                "WHERE course_id = ?",
                (course_id,),
            ).fetchone()
            group_id = row["next"]
        try:
            self.conn.execute(
                "INSERT INTO course_prerequisites (course_id, prerequisite_course_id, group_id) "
                "VALUES (?, ?, ?)",
                (course_id, prerequisite_course_id, group_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("That prerequisite is already set.") from e
        self.conn.commit()

    def add_prerequisite_group(self, course_id: int, prerequisite_course_ids: List[int]) -> None:
        """Add a set of alternative courses where completing ANY ONE of
        them satisfies the requirement (e.g. 'MATH101 or MATH105')."""
        if len(prerequisite_course_ids) < 2:
            raise ValidationError("An alternative group needs at least two courses.")
        row = self.conn.execute(
            "SELECT COALESCE(MAX(group_id), 0) + 1 AS next FROM course_prerequisites "
            "WHERE course_id = ?",
            (course_id,),
        ).fetchone()
        group_id = row["next"]
        for prereq_id in prerequisite_course_ids:
            self.add_prerequisite(course_id, prereq_id, group_id=group_id)

    def remove_prerequisite(self, course_id: int, prerequisite_course_id: int) -> None:
        self.conn.execute(
            "DELETE FROM course_prerequisites "
            "WHERE course_id = ? AND prerequisite_course_id = ?",
            (course_id, prerequisite_course_id),
        )
        self.conn.commit()

    def get_prerequisites(self, course_id: int) -> List[Course]:
        """Flattened list of every prerequisite course, ignoring group
        structure -- convenient for simple display."""
        rows = self.conn.execute(
            """SELECT c.* FROM courses c
               JOIN course_prerequisites cp ON cp.prerequisite_course_id = c.course_id
               WHERE cp.course_id = ?
               ORDER BY cp.group_id, c.course_code""",
            (course_id,),
        ).fetchall()
        return [Course.from_row(r) for r in rows]

    def get_prerequisite_groups(self, course_id: int) -> List[List[Course]]:
        """Structured view: a list of groups, each a list of alternative
        courses (OR within a group, AND across groups)."""
        rows = self.conn.execute(
            """SELECT cp.group_id, c.* FROM courses c
               JOIN course_prerequisites cp ON cp.prerequisite_course_id = c.course_id
               WHERE cp.course_id = ?
               ORDER BY cp.group_id, c.course_code""",
            (course_id,),
        ).fetchall()
        groups = {}
        for r in rows:
            groups.setdefault(r["group_id"], []).append(Course.from_row(r))
        return list(groups.values())
