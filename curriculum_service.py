"""Structured degree plans (الخطة الدراسية المهيكلة).

A curriculum maps a major to an ordered set of courses, each tagged with a
suggested level/semester (1..8) and a kind (required / elective). Unlike the
flat course catalog, this lets a student see a real graduation plan and lets
the system flag which plan courses are done, in progress, or still remaining.

Completion is advisory: prerequisite warnings and remaining-hours figures are
shown to guide the student, never to block anything (blocking stays in the
enrollment service).
"""

import sqlite3
from typing import List, Optional

from exceptions import DuplicateError, NotFoundError, ValidationError

KINDS = ("required", "elective")
MIN_LEVEL, MAX_LEVEL = 1, 8

_BASE_SELECT = """
    SELECT cc.curriculum_id, cc.major_id, cc.course_id, cc.level, cc.kind,
           cc.elective_block, c.course_code, c.title, c.title_ar, c.credit_hours
    FROM curriculum_courses cc
    JOIN courses c ON c.course_id = cc.course_id
"""


class CurriculumService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- management (admin, inside the major page) ------------------------
    def add_course(self, major_id: int, course_id: int, level: int = 1,
                   kind: str = "required", elective_block: str = "") -> sqlite3.Row:
        level = self._check_level(level)
        if kind not in KINDS:
            raise ValidationError(f"Curriculum kind must be one of {list(KINDS)}.")
        if not self.conn.execute("SELECT 1 FROM majors WHERE major_id = ?", (major_id,)).fetchone():
            raise NotFoundError(f"No major with id {major_id}.")
        if not self.conn.execute("SELECT 1 FROM courses WHERE course_id = ?", (course_id,)).fetchone():
            raise NotFoundError(f"No course with id {course_id}.")
        try:
            cur = self.conn.execute(
                """INSERT INTO curriculum_courses (major_id, course_id, level, kind, elective_block)
                   VALUES (?, ?, ?, ?, ?)""",
                (major_id, course_id, level, kind, (elective_block or "").strip() or None),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateError("This course is already in the major's plan.") from e
        self.conn.commit()
        return self.get_entry(cur.lastrowid)

    def get_entry(self, curriculum_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            _BASE_SELECT + " WHERE cc.curriculum_id = ?", (curriculum_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No curriculum entry with id {curriculum_id}.")
        return row

    def remove_course(self, curriculum_id: int) -> None:
        cur = self.conn.execute(
            "DELETE FROM curriculum_courses WHERE curriculum_id = ?", (curriculum_id,)
        )
        if cur.rowcount == 0:
            raise NotFoundError(f"No curriculum entry with id {curriculum_id}.")
        self.conn.commit()

    def update_entry(self, curriculum_id: int, **fields) -> sqlite3.Row:
        self.get_entry(curriculum_id)
        allowed = {"level", "kind", "elective_block"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "level" in updates:
            updates["level"] = self._check_level(updates["level"])
        if "kind" in updates and updates["kind"] not in KINDS:
            raise ValidationError(f"Curriculum kind must be one of {list(KINDS)}.")
        if not updates:
            return self.get_entry(curriculum_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        self.conn.execute(
            f"UPDATE curriculum_courses SET {set_clause} WHERE curriculum_id = ?",
            (*updates.values(), curriculum_id),
        )
        self.conn.commit()
        return self.get_entry(curriculum_id)

    def list_for_major(self, major_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            _BASE_SELECT + " WHERE cc.major_id = ? ORDER BY cc.level, c.course_code",
            (major_id,),
        ).fetchall()

    def plan_total_hours(self, major_id: int) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(SUM(c.credit_hours), 0) AS h
               FROM curriculum_courses cc JOIN courses c ON c.course_id = cc.course_id
               WHERE cc.major_id = ?""",
            (major_id,),
        ).fetchone()
        return row["h"]

    @staticmethod
    def _check_level(value) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValidationError(f"Level must be a whole number between {MIN_LEVEL} and {MAX_LEVEL}.")
        if not MIN_LEVEL <= value <= MAX_LEVEL:
            raise ValidationError(f"Level must be a whole number between {MIN_LEVEL} and {MAX_LEVEL}.")
        return value

    # -- student view (خطتي الدراسية) -------------------------------------
    def plan_for_student(self, student_id: int) -> Optional[dict]:
        """The student's degree plan grouped by level, each course tagged with
        a status (completed / in_progress / remaining) and an optional
        prerequisite warning. Returns None if the student has no major set."""
        srow = self.conn.execute(
            "SELECT major_id FROM students WHERE student_id = ?", (student_id,)
        ).fetchone()
        if srow is None:
            raise NotFoundError(f"No student with id {student_id}.")
        major_id = srow["major_id"]
        if not major_id:
            return None

        completed = self._completed_course_ids(student_id)
        completed_codes = self._codes_for(completed)
        enrolled = self._enrolled_course_ids(student_id)

        entries = self.list_for_major(major_id)
        by_level, done_hours, total_hours = {}, 0, 0
        for e in entries:
            total_hours += e["credit_hours"]
            if e["course_id"] in completed:
                status = "completed"
                done_hours += e["credit_hours"]
            elif e["course_id"] in enrolled:
                status = "in_progress"
            else:
                status = "remaining"
            item = {
                "curriculum_id": e["curriculum_id"], "course_id": e["course_id"],
                "course_code": e["course_code"], "title": e["title"],
                "title_ar": e["title_ar"], "credit_hours": e["credit_hours"],
                "level": e["level"], "kind": e["kind"],
                "elective_block": e["elective_block"], "status": status,
                # Prerequisite advisory: only meaningful for courses not yet done.
                "prereq_warning": (
                    self._unmet_prereqs(e["course_id"], completed_codes)
                    if status != "completed" else []
                ),
            }
            by_level.setdefault(e["level"], []).append(item)
        levels = [(lvl, by_level[lvl]) for lvl in sorted(by_level)]
        return {
            "major_id": major_id, "levels": levels,
            "plan_hours": total_hours, "done_hours": done_hours,
            "remaining_hours": max(0, total_hours - done_hours),
        }

    def _completed_course_ids(self, student_id: int) -> set:
        return {
            r["course_id"] for r in self.conn.execute(
                """SELECT DISTINCT sec.course_id FROM enrollments e
                   JOIN sections sec ON sec.section_id = e.section_id
                   WHERE e.student_id = ? AND e.status = 'completed'
                     AND e.grade IS NOT NULL AND e.grade NOT IN ('W', 'I', 'F')
                     AND e.grade_points IS NOT NULL AND e.grade_points > 0""",
                (student_id,),
            ).fetchall()
        }

    def _enrolled_course_ids(self, student_id: int) -> set:
        return {
            r["course_id"] for r in self.conn.execute(
                """SELECT DISTINCT sec.course_id FROM enrollments e
                   JOIN sections sec ON sec.section_id = e.section_id
                   WHERE e.student_id = ? AND e.status = 'enrolled'""",
                (student_id,),
            ).fetchall()
        }

    def _codes_for(self, course_ids: set) -> set:
        if not course_ids:
            return set()
        placeholders = ",".join("?" * len(course_ids))
        return {
            r["course_code"] for r in self.conn.execute(
                f"SELECT course_code FROM courses WHERE course_id IN ({placeholders})",
                tuple(course_ids),
            ).fetchall()
        }

    def _unmet_prereqs(self, course_id: int, completed_codes: set) -> List[str]:
        """Prerequisite groups (OR within a group, AND across groups) the
        student hasn't satisfied yet. Display-only, mirrors the enrollment
        service's rule without raising."""
        rows = self.conn.execute(
            """SELECT cp.group_id, c.course_code FROM course_prerequisites cp
               JOIN courses c ON c.course_id = cp.prerequisite_course_id
               WHERE cp.course_id = ? ORDER BY cp.group_id, c.course_code""",
            (course_id,),
        ).fetchall()
        groups = {}
        for r in rows:
            groups.setdefault(r["group_id"], []).append(r["course_code"])
        unmet = []
        for codes in groups.values():
            if not any(code in completed_codes for code in codes):
                unmet.append(" / ".join(codes))
        return unmet
