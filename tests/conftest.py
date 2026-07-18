import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_connection, initialize_database  # noqa: E402
from major_service import MajorService  # noqa: E402
from student_service import StudentService  # noqa: E402
from teacher_service import TeacherService  # noqa: E402
from course_service import CourseService  # noqa: E402
from term_service import TermService  # noqa: E402
from section_service import SectionService  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    c = get_connection(tmp_path / "test.db")
    initialize_database(c)
    yield c
    c.close()


@pytest.fixture
def world(conn):
    """A small bilingual, gender-mixed world for the tests."""
    terms = TermService(conn)
    year = terms.get_or_create_year("2030-2031", "سنة")
    term = terms.add_term("Fall 2030", "2030-09-01", "2030-12-20", name_ar="الأول",
                          academic_year_id=year.year_id)
    terms.set_current_term(term.term_id)

    majors = MajorService(conn)
    cs = majors.add_major("CS", "Computer Science", "علوم الحاسب", 120)

    teachers = TeacherService(conn)
    t_m = teachers.add_teacher("Omar", "M", "om@t.edu", "عمر", gender="male")
    t_f = teachers.add_teacher("Sara", "F", "sa@t.edu", "سارة", gender="female")

    courses = CourseService(conn)
    cs101 = courses.add_course("CS101", "Intro", 3, title_ar="مقدمة", price=1000, major_id=cs.major_id)
    cs102 = courses.add_course("CS102", "DS", 3, title_ar="هياكل", price=1000)
    courses.add_prerequisite(cs102.course_id, cs101.course_id)
    courses.assign_teacher(cs101.course_id, t_m.teacher_id)
    courses.assign_teacher(cs101.course_id, t_f.teacher_id)

    sections = SectionService(conn)
    sec_m = sections.add_section(cs101.course_id, term.term_id, "01",
                                 teacher_id=t_m.teacher_id, gender="male", capacity=2)
    sec_f = sections.add_section(cs101.course_id, term.term_id, "02",
                                 teacher_id=t_f.teacher_id, gender="female", capacity=5)
    sec102_m = sections.add_section(cs102.course_id, term.term_id, "01",
                                    teacher_id=t_m.teacher_id, gender="male", capacity=5)

    students = StudentService(conn)
    male = students.add_student("Ali", "K", "ali@s.edu", name_ar="علي", national_id="1111111111",
                                gender="male", nationality="Saudi", major_id=cs.major_id)
    female = students.add_student("Reem", "S", "reem@s.edu", name_ar="ريم", national_id="2222222222",
                                  gender="female", nationality="Non-Saudi", major_id=cs.major_id)

    return dict(conn=conn, term=term, cs=cs, cs101=cs101, cs102=cs102,
                sec_m=sec_m, sec_f=sec_f, sec102_m=sec102_m, male=male, female=female,
                t_m=t_m, t_f=t_f)
