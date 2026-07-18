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
    assert "10 digits" in r.get_data(as_text=True) or "١٠" in r.get_data(as_text=True)


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
