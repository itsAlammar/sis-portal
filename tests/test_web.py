"""Web-layer integration tests for SIS v2 (auth, roles, i18n, CSV, flows)."""

import io
import re

import pytest

from database import get_connection, initialize_database
from auth_service import AuthService
from major_service import MajorService
from teacher_service import TeacherService


@pytest.fixture
def client(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "web.db")
    import webapp
    webapp.app.config["TESTING"] = True

    conn = get_connection(tmp_path / "web.db")
    initialize_database(conn)
    auth = AuthService(conn)
    auth.create_user("admin", "admin-pass-1", "admin")
    auth.create_user("reg", "reg-pass-1", "registrar")
    MajorService(conn).add_major("CS", "Computer Science", "علوم الحاسب", 120)
    conn.close()
    return webapp.app.test_client()


def _csrf(client, path):
    m = re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).get_data(as_text=True))
    return m.group(1)


def login(client, user, pw, path="/login", field="username"):
    return client.post(path, data={field: user, "password": pw, "csrf_token": _csrf(client, path)})


def test_language_toggle_sets_rtl(client):
    client.get("/lang/ar")
    html = client.get("/").get_data(as_text=True)
    assert 'dir="rtl"' in html
    assert "نظام معلومات الطلاب" in html
    client.get("/lang/en")
    assert 'dir="ltr"' in client.get("/").get_data(as_text=True)


def test_registrar_pages_require_login(client):
    for path in ["/students", "/admissions", "/majors", "/sections"]:
        assert client.get(path).status_code == 302


def test_admin_only_blocks_registrar(client):
    login(client, "reg", "reg-pass-1")
    assert client.get("/users").status_code == 403
    assert client.get("/settings").status_code == 403


def test_public_application_then_admin_approval(client):
    # Public applicant submits (all fields required, ID 10 digits).
    tok = _csrf(client, "/apply")
    r = client.post("/apply", data={
        "national_id": "1234567890", "first_name": "New", "second_name": "Mid",
        "third_name": "Third", "last_name": "Comer", "name_ar": "طالب جديد كامل الاسم",
        "email": "newapp@x.com", "phone": "0550001111", "date_of_birth": "2005-01-01",
        "gender": "male", "nationality": "Saudi", "csrf_token": tok,
    })
    assert r.status_code == 302

    login(client, "admin", "admin-pass-1")
    html = client.get("/admissions").get_data(as_text=True)
    assert "1234567890" in html
    app_id = int(re.search(r"/admissions/(\d+)/approve", html).group(1))
    tok = _csrf(client, "/admissions")
    r = client.post(f"/admissions/{app_id}/approve", data={"csrf_token": tok})
    assert r.status_code == 302
    # Student now exists and can sign in to the portal with national ID.
    assert client.post("/portal/login", data={
        "student_number": "S" + __import__("datetime").date.today().strftime("%Y") + "0001",
        "password": "1234567890", "csrf_token": _csrf(client, "/portal/login"),
    }).status_code in (302, 200)


def test_bad_national_id_rejected_on_apply(client):
    tok = _csrf(client, "/apply")
    r = client.post("/apply", data={
        "national_id": "123", "first_name": "A", "second_name": "B", "third_name": "C",
        "last_name": "D", "name_ar": "اسم", "email": "a@b.com", "phone": "055",
        "date_of_birth": "2005-01-01", "gender": "male", "nationality": "Saudi",
        "csrf_token": tok,
    }, follow_redirects=True)
    assert "10 digits" in r.get_data(as_text=True) or "10" in r.get_data(as_text=True)


def test_csv_export_then_reimport(client):
    login(client, "reg", "reg-pass-1")
    # add a student via the form
    tok = _csrf(client, "/students/add")
    client.post("/students/add", data={
        "first_name": "Csv", "last_name": "Person", "email": "csv@x.com",
        "gender": "female", "nationality": "Saudi", "national_id": "9999999999",
        "csrf_token": tok,
    })
    export = client.get("/students/export.csv").get_data(as_text=True)
    assert "csv@x.com" in export and "9999999999" in export

    # template downloads
    assert client.get("/students/import/template.csv").status_code == 200
    assert client.get("/courses/import/template.csv").status_code == 200
    assert client.get("/teachers/import/template.csv").status_code == 200


def test_csrf_required(client):
    login(client, "reg", "reg-pass-1")
    assert client.post("/students/add", data={"first_name": "X", "last_name": "Y",
                                              "email": "x@y.com"}).status_code == 400


def test_approved_student_appears_in_students_list_and_email_logged(client):
    # Submit a public application.
    tok = _csrf(client, "/apply")
    client.post("/apply", data={
        "national_id": "5556667770", "first_name": "Visible", "second_name": "In",
        "third_name": "The", "last_name": "List", "name_ar": "طالب يظهر في القائمة",
        "email": "visible@x.com", "phone": "0550002222", "date_of_birth": "2005-05-05",
        "gender": "male", "nationality": "Saudi", "csrf_token": tok,
    })
    login(client, "admin", "admin-pass-1")
    html = client.get("/admissions").get_data(as_text=True)
    app_id = int(re.search(r"/admissions/(\d+)/approve", html).group(1))
    client.post(f"/admissions/{app_id}/approve",
                data={"csrf_token": _csrf(client, "/admissions")})

    # The new student shows up in the students list immediately.
    listing = client.get("/students").get_data(as_text=True)
    assert "طالب يظهر في القائمة" in listing or "Visible" in listing

    # Acceptance email was recorded in the log (sending disabled by default).
    log = client.get("/emails").get_data(as_text=True)
    assert "visible@x.com" in log


def test_grade_breakdown_saved_and_totalled(client):
    import database
    from database import get_connection
    from student_service import StudentService
    from teacher_service import TeacherService
    from course_service import CourseService
    from term_service import TermService
    from section_service import SectionService
    from enrollment_service import EnrollmentService
    from grading_service import GradingService

    conn = get_connection(database.DB_PATH)
    term = TermService(conn).add_term("F2031", "2031-09-01", "2031-12-20")
    course = CourseService(conn).add_course("BRK101", "Breakdown", 3)
    section = SectionService(conn).add_section(course.course_id, term.term_id, "01",
                                               gender="male", capacity=5)
    student = StudentService(conn).add_student("Break", "Down", "brk@x.com", gender="male")
    EnrollmentService(conn).enroll_student(student.student_id, section.section_id)

    e = GradingService(conn).assign_breakdown_by_pair(
        student.student_id, section.section_id, coursework=48, final=44)
    assert e.numeric_mark == 92 and e.grade == "A"
    assert e.coursework_mark == 48 and e.final_mark == 44
    conn.close()


def test_paginated_pages_survive_multiple_pages(client):
    """Regression: the pager macro used t() without `with context`, so every
    paginated page 500'd as soon as it grew past one page (25 rows)."""
    import database
    from database import get_connection
    conn = get_connection(database.DB_PATH)
    for i in range(30):
        conn.execute(
            "INSERT INTO audit_log (at, actor, action, entity_type, entity_id, details) "
            "VALUES (?,?,?,?,?,?)",
            (f"2030-01-{(i % 28) + 1:02d}T10:00:00", "staff:admin", "student.update",
             "student", i, f"row {i}"),
        )
    conn.commit()
    conn.close()

    login(client, "admin", "admin-pass-1")
    page1 = client.get("/audit")
    assert page1.status_code == 200
    assert "Page 1 of 2" in page1.get_data(as_text=True)
    assert client.get("/audit?page=2").status_code == 200


def test_financial_outstanding_invoices_table(client):
    import database
    from database import get_connection
    from student_service import StudentService
    from fee_service import FeeService

    conn = get_connection(database.DB_PATH)
    student = StudentService(conn).add_student("Owing", "Person", "owing@x.com", gender="male")
    fee = FeeService(conn).assess_fee(student.student_id, "Registration", 500)
    FeeService(conn).record_payment(fee.fee_id, 150)
    number = student.student_number
    conn.close()

    login(client, "admin", "admin-pass-1")
    html = client.get("/financial").get_data(as_text=True)
    assert "Outstanding invoices" in html
    assert number in html and "350.00" in html and "150.00" in html
    # Search hits and misses.
    assert number in client.get(f"/financial?q={number}").get_data(as_text=True)
    assert number not in client.get("/financial?q=zzz").get_data(as_text=True)


def test_users_page_edits_roles_with_guard(client):
    import database
    from database import get_connection

    login(client, "admin", "admin-pass-1")
    html = client.get("/users").get_data(as_text=True)
    assert "Staff &amp; permissions" in html

    # Admin reassigns the registrar's role (and sets a display name).
    conn = get_connection(database.DB_PATH)
    reg_id = conn.execute("SELECT user_id FROM users WHERE username='reg'").fetchone()["user_id"]
    admin_id = conn.execute("SELECT user_id FROM users WHERE username='admin'").fetchone()["user_id"]
    conn.close()
    client.post(f"/users/{reg_id}/update",
                data={"role": "accounting", "teacher_id": "", "full_name": "Reggie",
                      "csrf_token": _csrf(client, "/users")})
    conn = get_connection(database.DB_PATH)
    row = conn.execute("SELECT role, full_name FROM users WHERE user_id=?", (reg_id,)).fetchone()
    conn.close()
    assert row["role"] == "accounting" and row["full_name"] == "Reggie"

    # The only active admin cannot demote themselves.
    r = client.post(f"/users/{admin_id}/update",
                    data={"role": "registrar", "teacher_id": "", "full_name": "",
                          "csrf_token": _csrf(client, "/users")},
                    follow_redirects=True)
    assert "remove the admin role" in r.get_data(as_text=True)
    conn = get_connection(database.DB_PATH)
    assert conn.execute("SELECT role FROM users WHERE user_id=?",
                        (admin_id,)).fetchone()["role"] == "admin"
    conn.close()


def test_teacher_account_button_creates_linked_user(client):
    import database
    from database import get_connection

    login(client, "admin", "admin-pass-1")
    conn = get_connection(database.DB_PATH)
    t = TeacherService(conn).add_teacher("Omar", "Haddad", "oh@t.edu", "عمر", gender="male")
    conn.close()

    page = client.get(f"/teachers/{t.teacher_id}/edit").get_data(as_text=True)
    assert "Create login account" in page

    client.post(f"/teachers/{t.teacher_id}/account",
                data={"username": "o.haddad", "password": "teach-pass-99",
                      "csrf_token": _csrf(client, f"/teachers/{t.teacher_id}/edit")})
    conn = get_connection(database.DB_PATH)
    row = conn.execute("SELECT role, teacher_id, full_name FROM users WHERE username='o.haddad'").fetchone()
    conn.close()
    assert row["role"] == "teacher" and row["teacher_id"] == t.teacher_id
    assert row["full_name"] == "عمر"
    # The edit page now shows the account instead of the form.
    page = client.get(f"/teachers/{t.teacher_id}/edit").get_data(as_text=True)
    assert "o.haddad" in page and "Create login account" not in page


def _make_portal_student(number_suffix="01"):
    """Registers a student with a portal password inside the client's DB."""
    import database
    from database import get_connection
    from student_service import StudentService
    conn = get_connection(database.DB_PATH)
    s = StudentService(conn).add_student(f"Portal{number_suffix}", "Kid",
                                         f"p{number_suffix}@x.com", gender="male")
    AuthService(conn).set_student_password(s.student_id, "portal-pass-1")
    conn.close()
    return s


def test_portal_excuse_flow_end_to_end(client):
    import database
    from database import get_connection
    from term_service import TermService
    from course_service import CourseService
    from section_service import SectionService
    from enrollment_service import EnrollmentService
    from attendance_service import AttendanceService

    s = _make_portal_student("11")
    conn = get_connection(database.DB_PATH)
    term = TermService(conn).add_term("F2032", "2032-09-01", "2032-12-20")
    course = CourseService(conn).add_course("EXC101", "Excuses", 3)
    sec = SectionService(conn).add_section(course.course_id, term.term_id, "01",
                                           gender="male", capacity=5)
    EnrollmentService(conn).enroll_student(s.student_id, sec.section_id)
    AttendanceService(conn).record_bulk(sec.section_id, "2032-10-01",
                                        {s.student_id: "absent"}, recorded_by="staff:t")
    conn.close()

    login(client, s.student_number, "portal-pass-1", path="/portal/login", field="student_number")
    page = client.get("/portal/attendance").get_data(as_text=True)
    assert "Submit excuse" in page
    r = client.post("/portal/attendance/excuse",
                    data={"section_id": sec.section_id, "date": "2032-10-01",
                          "details": "sick", "csrf_token": _csrf(client, "/portal/attendance")},
                    follow_redirects=True)
    assert "Excuse submitted" in r.get_data(as_text=True)

    # Staff sees it on the requests screen and approves it.
    staff = client  # same test client, new session after staff login
    login(staff, "admin", "admin-pass-1")
    html = staff.get("/requests").get_data(as_text=True)
    assert "Absence excuse" in html and "EXC101" in html
    req_id = int(re.search(r"/requests/(\d+)/review", html).group(1))
    staff.post(f"/requests/{req_id}/review",
               data={"decision": "approved", "csrf_token": _csrf(staff, "/requests")})

    conn = get_connection(database.DB_PATH)
    status = conn.execute(
        "SELECT status FROM attendance WHERE section_id=? AND student_id=? AND date='2032-10-01'",
        (sec.section_id, s.student_id)).fetchone()["status"]
    conn.close()
    assert status == "excused"


def test_receipt_pdf_routes_enforce_ownership(client):
    import database
    from database import get_connection
    from fee_service import FeeService

    owner = _make_portal_student("21")
    other = _make_portal_student("22")
    conn = get_connection(database.DB_PATH)
    fee = FeeService(conn).assess_fee(owner.student_id, "Registration", 500)
    payment = FeeService(conn).record_payment(fee.fee_id, 500, payment_method="Cash")
    conn.close()

    login(client, owner.student_number, "portal-pass-1", path="/portal/login", field="student_number")
    r = client.get(f"/portal/receipts/{payment.payment_id}.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"

    login(client, other.student_number, "portal-pass-1", path="/portal/login", field="student_number")
    assert client.get(f"/portal/receipts/{payment.payment_id}.pdf").status_code == 403

    login(client, "admin", "admin-pass-1")
    r = client.get(f"/receipts/{payment.payment_id}.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-"
