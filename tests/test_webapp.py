"""End-to-end web tests: route protection, CSRF, role scoping, audit."""


def test_registrar_routes_require_login(webapp):
    client = webapp["client"]
    for path in ["/registrar", "/students", "/sections", "/audit"]:
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_staff_login_and_dashboard(webapp):
    response = webapp["login"]("reggie", "registrar-pw")
    assert response.headers["Location"].endswith("/registrar")
    assert webapp["client"].get("/students").status_code == 200


def test_bad_password_rejected(webapp):
    response = webapp["login"]("reggie", "totally-wrong")
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data


def test_post_without_csrf_token_is_rejected(webapp):
    webapp["login"]("reggie", "registrar-pw")
    response = webapp["client"].post("/students/add", data={
        "first_name": "Evil", "last_name": "Request", "email": "evil@x.com",
    })
    assert response.status_code == 400


def test_teacher_cannot_open_registrar_pages(webapp):
    webapp["login"]("tina", "teacher-pw-1")
    response = webapp["client"].get("/students")
    assert response.status_code == 302
    assert "/teach" in response.headers["Location"]


def test_teacher_sees_own_section_but_not_others(webapp):
    webapp["login"]("tina", "teacher-pw-1")
    client = webapp["client"]
    own = webapp["own_section"].section_id
    other = webapp["other_section"].section_id
    assert client.get(f"/teach/sections/{own}").status_code == 200
    assert client.get(f"/teach/sections/{other}").status_code == 403


def test_teacher_grades_own_section_and_audit_records_it(webapp):
    client, conn = webapp["client"], webapp["conn"]
    student, section = webapp["student"], webapp["own_section"]

    conn.execute(
        "INSERT INTO enrollments (student_id, section_id, enrollment_date, status) "
        "VALUES (?, ?, '2030-09-02', 'enrolled')",
        (student.student_id, section.section_id),
    )
    conn.commit()

    webapp["login"]("tina", "teacher-pw-1")
    token = webapp["csrf"](f"/teach/sections/{section.section_id}")
    response = client.post(f"/teach/sections/{section.section_id}/grades", data={
        f"grade_{student.student_id}": "A-", "csrf_token": token,
    })
    assert response.status_code == 302

    grade = conn.execute(
        "SELECT grade FROM enrollments WHERE student_id = ? AND section_id = ?",
        (student.student_id, section.section_id),
    ).fetchone()["grade"]
    assert grade == "A-"

    entry = conn.execute(
        "SELECT * FROM audit_log WHERE action = 'grade.assign' ORDER BY audit_id DESC"
    ).fetchone()
    assert entry is not None
    assert entry["actor"] == "staff:tina"


def test_portal_activation_and_login(webapp):
    client, student = webapp["client"], webapp["student"]

    token = webapp["csrf"]("/portal/login?mode=activate")
    response = client.post("/portal/login", data={
        "mode": "activate", "student_number": student.student_number,
        "email": student.email, "password": "portal-pass-9",
        "confirm_password": "portal-pass-9", "csrf_token": token,
    })
    assert response.headers["Location"].endswith("/portal")

    with client.session_transaction() as session:
        session.pop("portal_student_id", None)

    token = webapp["csrf"]("/portal/login")
    response = client.post("/portal/login", data={
        "mode": "login", "student_number": student.student_number,
        "password": "portal-pass-9", "csrf_token": token,
    })
    assert response.headers["Location"].endswith("/portal")

    response = client.post("/portal/login", data={
        "mode": "login", "student_number": student.student_number,
        "password": "wrong-password", "csrf_token": token,
    })
    assert b"Invalid student number or password" in response.data


def test_admin_creates_user_via_ui(webapp):
    webapp["login"]("boss", "admin-pass-1")
    client = webapp["client"]

    token = webapp["csrf"]("/users")
    response = client.post("/users/add", data={
        "username": "newstaff", "password": "fresh-password", "role": "registrar",
        "csrf_token": token,
    })
    assert response.status_code == 302

    row = webapp["conn"].execute(
        "SELECT role FROM users WHERE username = 'newstaff'"
    ).fetchone()
    assert row["role"] == "registrar"


def test_registrar_cannot_manage_users(webapp):
    webapp["login"]("reggie", "registrar-pw")
    assert webapp["client"].get("/users").status_code == 403


def test_first_run_setup_only_when_no_users(webapp):
    # Users exist in this fixture, so /setup must bounce to /login.
    response = webapp["client"].get("/setup")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_pagination_clamps_page(webapp):
    webapp["login"]("reggie", "registrar-pw")
    assert webapp["client"].get("/students?page=999").status_code == 200
    assert webapp["client"].get("/students?page=-5").status_code == 200
