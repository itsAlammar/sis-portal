"""Bulk student import from CSV. Shared by the CLI and the web upload route
so both interfaces get identical validation and error reporting.

Expected columns (header row required): first_name, last_name, email
Optional columns: phone, date_of_birth, gender, program, department_code,
enrollment_date
"""

import csv
import io
import sqlite3
from typing import IO, List, Tuple

from exceptions import SISError
from student_service import StudentService

REQUIRED_COLUMNS = {"first_name", "last_name", "email"}


def import_students_from_csv(conn: sqlite3.Connection, file_obj: IO) -> Tuple[List[str], List[str]]:
    """Returns (successes, errors) as lists of human-readable strings.
    file_obj can be any text-mode readable, e.g. an open file or a Flask
    FileStorage's stream wrapped in io.TextIOWrapper."""
    students = StudentService(conn)
    successes: List[str] = []
    errors: List[str] = []

    reader = csv.DictReader(file_obj)
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        errors.append(
            f"CSV header must include at least: {', '.join(sorted(REQUIRED_COLUMNS))}. "
            f"Found: {', '.join(reader.fieldnames or []) or '(empty file)'}"
        )
        return successes, errors

    dept_cache = {
        row["code"]: row["department_id"]
        for row in conn.execute("SELECT * FROM departments")
    }

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            dept_code = (row.get("department_code") or "").strip().upper()
            department_id = dept_cache.get(dept_code) if dept_code else None
            s = students.add_student(
                first_name=(row.get("first_name") or "").strip(),
                last_name=(row.get("last_name") or "").strip(),
                email=(row.get("email") or "").strip(),
                phone=(row.get("phone") or "").strip(),
                date_of_birth=(row.get("date_of_birth") or "").strip(),
                gender=(row.get("gender") or "").strip(),
                program=(row.get("program") or "").strip(),
                department_id=department_id,
                enrollment_date=(row.get("enrollment_date") or "").strip() or None,
            )
            successes.append(f"Row {i}: created {s.student_number} ({s.full_name}).")
        except SISError as e:
            errors.append(f"Row {i}: {e}")
        except Exception as e:  # malformed row shouldn't kill the whole batch
            errors.append(f"Row {i}: unexpected error -- {e}")

    return successes, errors


def csv_template() -> str:
    """A starter CSV the user can download, fill in, and re-upload."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "first_name", "last_name", "email", "phone", "date_of_birth",
        "gender", "program", "department_code", "enrollment_date",
    ])
    writer.writerow([
        "Jane", "Doe", "jane.doe@student.academy.edu", "0500000000",
        "2001-04-12", "Female", "Computer Science", "CS", "2026-09-01",
    ])
    return buf.getvalue()
