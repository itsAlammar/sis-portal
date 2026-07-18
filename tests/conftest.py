import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import get_connection, initialize_database  # noqa: E402
from auth_service import AuthService  # noqa: E402
from student_service import StudentService  # noqa: E402
from teacher_service import TeacherService  # noqa: E402
from course_service import CourseService  # noqa: E402
from term_service import TermService  # noqa: E402
from section_service import SectionService  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    initialize_database(connection)
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn):
    """A small consistent world: one term, two courses (CS102 requires
    CS101), one 2-seat section, three active students."""
    terms = TermService(conn)
    term = terms.add_term("Fall 2030", "2030-09-01", "2030-12-20")
    terms.set_current_term(term.term_id)

    teachers = TeacherService(conn)
    teacher = teachers.add_teacher("Tina", "Teach", "tina@test.edu")

    courses = CourseService(conn)
    cs101 = courses.add_course("CS101", "Intro", 3)
    cs102 = courses.add_course("CS102", "Data Structures", 3)
    courses.add_prerequisite(cs102.course_id, cs101.course_id)

    sections = SectionService(conn)
    sec101 = sections.add_section(cs101.course_id, term.term_id, "01",
                                  teacher_id=teacher.teacher_id, capacity=2,
                                  days="MON,WED", start_time="09:00", end_time="09:50")
    sec102 = sections.add_section(cs102.course_id, term.term_id, "01",
                                  teacher_id=teacher.teacher_id, capacity=10)

    students = StudentService(conn)
    alice = students.add_student("Alice", "One", "alice@test.edu")
    bob = students.add_student("Bob", "Two", "bob@test.edu")
    carol = students.add_student("Carol", "Three", "carol@test.edu")

    return {
        "conn": conn, "term": term, "teacher": teacher,
        "cs101": cs101, "cs102": cs102, "sec101": sec101, "sec102": sec102,
        "alice": alice, "bob": bob, "carol": carol,
    }


@pytest.fixture
def webapp(tmp_path, monkeypatch):
    """Flask test client wired to a throwaway database, plus helpers."""
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "web.db")
    import webapp as webapp_module
    webapp_module.app.config["TESTING"] = True

    conn = get_connection(tmp_path / "web.db")
    initialize_database(conn)

    auth = AuthService(conn)
    admin = auth.create_user("boss", "admin-pass-1", "admin")
    registrar = auth.create_user("reggie", "registrar-pw", "registrar")

    teacher_rec = TeacherService(conn).add_teacher("Tina", "Teach", "tina@web.edu")
    other_teacher = TeacherService(conn).add_teacher("Oscar", "Other", "oscar@web.edu")
    teacher_user = auth.create_user("tina", "teacher-pw-1", "teacher",
                                    teacher_id=teacher_rec.teacher_id)

    term = TermService(conn).add_term("Fall 2030", "2030-09-01", "2030-12-20")
    course = CourseService(conn).add_course("CS101", "Intro", 3)
    sections = SectionService(conn)
    own_section = sections.add_section(course.course_id, term.term_id, "01",
                                       teacher_id=teacher_rec.teacher_id, capacity=5)
    other_section = sections.add_section(course.course_id, term.term_id, "02",
                                         teacher_id=other_teacher.teacher_id, capacity=5)

    student = StudentService(conn).add_student("Sam", "Student", "sam@web.edu")

    client = webapp_module.app.test_client()

    def login(username, password):
        page = client.get("/login")
        token = _extract_csrf(page)
        return client.post("/login", data={
            "username": username, "password": password, "csrf_token": token,
        }, follow_redirects=False)

    def csrf(path="/login"):
        return _extract_csrf(client.get(path))

    yield {
        "client": client, "conn": conn, "login": login, "csrf": csrf,
        "admin": admin, "registrar": registrar, "teacher_user": teacher_user,
        "teacher_rec": teacher_rec, "own_section": own_section,
        "other_section": other_section, "student": student, "term": term,
    }
    conn.close()


def _extract_csrf(response):
    import re
    html = response.get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "no csrf token found in page"
    return m.group(1)
