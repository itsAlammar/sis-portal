"""Weekly-timetable conflict detection and a lightweight draft generator.

Both features are pure Python (no OR-Tools / no heavy solver) so they run
comfortably on free PythonAnywhere-style hosting.

* Conflict detection (advisory only, never blocks): flags a teacher taught in
  two overlapping sections, a room double-booked, or a student enrolled in two
  overlapping sections — same spirit as the exam-clash warnings.
* Draft generator: a greedy pass that drops each unscheduled section into the
  first free day-pattern/time-slot that introduces no teacher or room clash,
  leaving anything it can't place untouched for manual editing. Sections that
  already have a fixed schedule are kept as-is unless the caller explicitly
  asks to regenerate everything.
"""

import sqlite3
from dataclasses import dataclass, replace
from typing import List

from section_service import SectionService

# A simple hourly grid; the greedy generator tries these in order.
TIME_SLOTS = [
    ("08:00", "08:50"), ("09:00", "09:50"), ("10:00", "10:50"),
    ("11:00", "11:50"), ("12:00", "12:50"), ("13:00", "13:50"),
    ("14:00", "14:50"), ("15:00", "15:50"),
]
# Common two/three-day teaching patterns.
DAY_PATTERNS = [["SUN", "TUE", "THU"], ["MON", "WED"], ["SUN", "TUE"], ["MON", "WED", "THU"]]


@dataclass
class Conflict:
    kind: str            # teacher, room, student
    a: object            # Section
    b: object            # Section
    ref: object = None   # teacher_id / room / student_id involved


class TimetableService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.sections = SectionService(conn)

    # -- conflict detection ----------------------------------------------
    def section_conflicts(self, term_id: int) -> List[Conflict]:
        secs = self.sections.list_sections(term_id=term_id)
        by_id = {s.section_id: s for s in secs}
        conflicts: List[Conflict] = []
        for i, a in enumerate(secs):
            for b in secs[i + 1:]:
                if not SectionService.has_schedule_conflict(a, b):
                    continue
                if a.teacher_id and b.teacher_id and a.teacher_id == b.teacher_id:
                    conflicts.append(Conflict("teacher", a, b, a.teacher_id))
                if _same_room(a, b):
                    conflicts.append(Conflict("room", a, b, a.room.strip()))
        conflicts.extend(self._student_conflicts(term_id, by_id))
        return conflicts

    def _student_conflicts(self, term_id: int, by_id: dict) -> List[Conflict]:
        rows = self.conn.execute(
            """SELECT e.student_id, e.section_id FROM enrollments e
               JOIN sections sec ON sec.section_id = e.section_id
               WHERE sec.term_id = ? AND e.status = 'enrolled'""",
            (term_id,),
        ).fetchall()
        by_student: dict = {}
        for r in rows:
            by_student.setdefault(r["student_id"], []).append(r["section_id"])
        out: List[Conflict] = []
        for student_id, sec_ids in by_student.items():
            for i in range(len(sec_ids)):
                for j in range(i + 1, len(sec_ids)):
                    a, b = by_id.get(sec_ids[i]), by_id.get(sec_ids[j])
                    if a and b and SectionService.has_schedule_conflict(a, b):
                        out.append(Conflict("student", a, b, student_id))
        return out

    def conflicting_section_ids(self, term_id: int) -> set:
        ids = set()
        for c in self.section_conflicts(term_id):
            ids.add(c.a.section_id)
            ids.add(c.b.section_id)
        return ids

    # -- greedy draft generator ------------------------------------------
    def generate_draft(self, term_id: int, overwrite_fixed: bool = False) -> dict:
        """Places unscheduled sections into the first clash-free slot. With
        overwrite_fixed=True every section is re-placed from scratch (used only
        after the admin confirms). Returns a summary with counts and the ids it
        could not place."""
        secs = self.sections.list_sections(term_id=term_id)
        placed, to_place = [], []
        for s in secs:
            if _is_scheduled(s) and not overwrite_fixed:
                placed.append(s)
            else:
                to_place.append(s)
        result = {"kept": len(placed), "placed": 0, "unplaced": []}
        for s in to_place:
            slot = self._first_free_slot(s, placed)
            if slot is None:
                result["unplaced"].append(s.section_id)
                continue
            days, start, end = slot
            self.sections.update_section(s.section_id, days=days,
                                         start_time=start, end_time=end)
            placed.append(replace(s, days=days, start_time=start, end_time=end))
            result["placed"] += 1
        return result

    def _first_free_slot(self, section, placed):
        for pattern in DAY_PATTERNS:
            for start, end in TIME_SLOTS:
                candidate = replace(section, days=",".join(pattern),
                                    start_time=start, end_time=end)
                if not any(_basic_clash(candidate, p) for p in placed):
                    return ",".join(pattern), start, end
        return None


def _is_scheduled(s) -> bool:
    return bool(s.days and s.start_time and s.end_time)


def _same_room(a, b) -> bool:
    return bool(a.room and b.room and a.room.strip()
                and a.room.strip() == b.room.strip())


def _basic_clash(a, b) -> bool:
    """A teacher or room clash between two time-overlapping sections — the two
    hard constraints the greedy generator must never violate."""
    if not SectionService.has_schedule_conflict(a, b):
        return False
    same_teacher = a.teacher_id and b.teacher_id and a.teacher_id == b.teacher_id
    return bool(same_teacher or _same_room(a, b))
