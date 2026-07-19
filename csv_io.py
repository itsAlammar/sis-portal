"""CSV import and export for students, teachers, and courses.

Import returns (successes, errors) so a partial file still loads the good
rows and reports the bad ones. Export writes a header matching the import
template, so an exported file can be re-imported.
"""

import csv
import io
from typing import List, Tuple

from exceptions import SISError
from student_service import StudentService
from teacher_service import TeacherService
from course_service import CourseService


# -- students -------------------------------------------------------------
STUDENT_COLS = ["national_id", "first_name", "second_name", "third_name", "last_name",
                "name_ar", "email", "phone", "date_of_birth", "gender", "nationality"]


def students_template() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(STUDENT_COLS)
    w.writerow(["1012345678", "Sara", "Ali", "Mohammed", "Alsaud", "سارة علي محمد آل سعود",
                "sara@example.com", "0500000000", "2005-01-01", "female", "Saudi"])
    return out.getvalue()


def import_students(conn, text_stream) -> Tuple[List, List[str]]:
    svc = StudentService(conn)
    ok, errors = [], []
    for i, row in enumerate(csv.DictReader(text_stream), start=2):
        try:
            ok.append(svc.add_student(
                first_name=row.get("first_name", ""), second_name=row.get("second_name", ""),
                third_name=row.get("third_name", ""), last_name=row.get("last_name", ""),
                name_ar=row.get("name_ar", ""), national_id=(row.get("national_id") or None),
                email=row.get("email", ""), phone=row.get("phone", ""),
                date_of_birth=row.get("date_of_birth", ""), gender=row.get("gender", "male") or "male",
                nationality=row.get("nationality", "Saudi") or "Saudi",
            ))
        except SISError as e:
            errors.append(f"row {i}: {e}")
    return ok, errors


def export_students(conn) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["student_number"] + STUDENT_COLS)
    for s in StudentService(conn).list_students():
        w.writerow([s.student_number, s.national_id or "", s.first_name, s.second_name or "",
                    s.third_name or "", s.last_name, s.name_ar or "", s.email, s.phone or "",
                    s.date_of_birth or "", s.gender, s.nationality])
    return out.getvalue()


# -- teachers -------------------------------------------------------------
TEACHER_COLS = ["first_name", "last_name", "name_ar", "email", "phone", "gender", "title"]


def teachers_template() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(TEACHER_COLS)
    w.writerow(["Omar", "Haddad", "عمر حداد", "omar@example.com", "0500000000", "male", "Lecturer"])
    return out.getvalue()


def import_teachers(conn, text_stream) -> Tuple[List, List[str]]:
    svc = TeacherService(conn)
    ok, errors = [], []
    for i, row in enumerate(csv.DictReader(text_stream), start=2):
        try:
            ok.append(svc.add_teacher(
                first_name=row.get("first_name", ""), last_name=row.get("last_name", ""),
                email=row.get("email", ""), name_ar=row.get("name_ar", ""),
                gender=row.get("gender", "male") or "male", phone=row.get("phone", ""),
                title=row.get("title", ""),
            ))
        except SISError as e:
            errors.append(f"row {i}: {e}")
    return ok, errors


def export_teachers(conn) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["employee_number"] + TEACHER_COLS)
    for t in TeacherService(conn).list_teachers():
        w.writerow([t.employee_number, t.first_name, t.last_name, t.name_ar or "", t.email,
                    t.phone or "", t.gender, t.title or ""])
    return out.getvalue()


# -- courses --------------------------------------------------------------
COURSE_COLS = ["course_code", "title", "title_ar", "credit_hours", "price", "coursework_max"]


def courses_template() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COURSE_COLS)
    w.writerow(["CS101", "Introduction to Programming", "مقدمة في البرمجة", "3", "1500"])
    return out.getvalue()


def import_courses(conn, text_stream) -> Tuple[List, List[str]]:
    svc = CourseService(conn)
    ok, errors = [], []
    for i, row in enumerate(csv.DictReader(text_stream), start=2):
        try:
            ok.append(svc.add_course(
                course_code=row.get("course_code", ""), title=row.get("title", ""),
                title_ar=row.get("title_ar", ""), credit_hours=int(row.get("credit_hours") or 0),
                price=float(row.get("price") or 0),
                coursework_max=int(row.get("coursework_max") or 50),
            ))
        except (SISError, ValueError) as e:
            errors.append(f"row {i}: {e}")
    return ok, errors


def export_courses(conn) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COURSE_COLS)
    for c in CourseService(conn).list_courses():
        w.writerow([c.course_code, c.title, c.title_ar or "", c.credit_hours, c.price, c.coursework_max])
    return out.getvalue()
