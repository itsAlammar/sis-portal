"""Bilingual (Arabic/English) web interface for the SIS.

Development:  pip install -r requirements.txt && python webapp.py
Production:   SIS_SECRET_KEY=... gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app

Locale is per-session (?lang=ar / ?lang=en). Arabic renders RTL. Every
business rule lives in the service layer; this module is presentation +
authentication + authorization + audit only.
"""

import io
import math
import os
import secrets as _secrets
from datetime import date
from functools import wraps

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for,
)

import i18n
import csv_io
from database import get_connection, initialize_database, get_setting, set_setting
from exceptions import SISError
from audit_service import AuditService
from auth_service import AuthService
from admissions_service import AdmissionsService
from student_service import StudentService
from teacher_service import TeacherService
from course_service import CourseService
from major_service import MajorService
from term_service import TermService
from section_service import SectionService
from enrollment_service import EnrollmentService
from grading_service import GradingService
from gpa_service import GPAService
from fee_service import FeeService
from waitlist_service import WaitlistService
from request_service import RequestService
from mail_service import MailService

app = Flask(__name__)
app.secret_key = os.environ.get("SIS_SECRET_KEY") or _secrets.token_hex(32)
if not os.environ.get("SIS_SECRET_KEY"):
    app.logger.warning("SIS_SECRET_KEY not set -- using a random key for this run only.")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  MAX_CONTENT_LENGTH=4 * 1024 * 1024)

PER_PAGE = 25

STATUS_KIND = {
    "active": "ok", "completed": "ok", "paid": "ok", "open": "ok",
    "graduated": "ok", "waived": "default", "promoted": "default", "approved": "ok",
    "enrolled": "progress", "partial": "progress", "pending": "progress", "closed": "progress",
    "waiting": "progress", "deferred": "progress",
    "suspended": "attention", "withdrawn": "attention", "dropped": "attention",
    "overdue": "attention", "cancelled": "attention", "inactive": "attention",
    "skipped": "attention", "rejected": "attention", "disabled": "attention",
}


# ----------------------------------------------------------------------
# Locale
# ----------------------------------------------------------------------
def locale():
    return i18n.normalize(session.get("lang", i18n.DEFAULT_LOCALE))


@app.route("/lang/<code>")
def set_lang(code):
    session["lang"] = i18n.normalize(code)
    return redirect(request.referrer or url_for("landing"))


def _t_prefixed(prefix, value, loc):
    """Translate a data value (status/kind/fee type) via a prefixed key,
    falling back to the raw value when no translation exists."""
    key = f"{prefix}.{str(value).lower()}"
    return i18n.t(key, loc) if key in i18n.TRANSLATIONS else value


@app.context_processor
def inject_globals():
    loc = locale()
    return {
        "t": lambda key, **kw: i18n.t(key, loc, **kw),
        "ts": lambda s: _t_prefixed("status", s, loc),
        "tk": lambda k: _t_prefixed("kind", k, loc),
        "tf": lambda f: _t_prefixed("feetype", f, loc),
        "locale": loc,
        "dir": i18n.dir_for(loc),
        "status_kind": lambda s: STATUS_KIND.get(s, "default"),
        "current_term": TermService(get_db()).get_current_term(),
        "staff_user": current_staff(),
        "portal_student": _portal_student(),
        "pending_admissions": _safe_count(lambda c: AdmissionsService(c).count_pending()),
        "pending_requests": _safe_count(lambda c: RequestService(c).count_pending()),
        "csrf_token": _csrf_token,
        "lms_enabled": get_setting(get_db(), "lms_enabled", "0") == "1",
    }


def _safe_count(fn):
    try:
        return fn(get_db())
    except SISError:
        return 0


# ----------------------------------------------------------------------
# DB per request
# ----------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = get_connection()
        initialize_database(g.db)
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.errorhandler(SISError)
def handle_sis_error(e):
    flash(str(e), "error")
    return redirect(request.referrer or url_for("landing"))


def _departments(conn):
    return conn.execute("SELECT * FROM departments ORDER BY name").fetchall()


# ----------------------------------------------------------------------
# CSRF
# ----------------------------------------------------------------------
def _csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = _secrets.token_hex(16)
    return session["_csrf_token"]


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf_token", "")
        if not token or not _secrets.compare_digest(token, request.form.get("csrf_token", "")):
            abort(400, description="CSRF token missing or invalid. Reload and try again.")


# ----------------------------------------------------------------------
# Auth / roles
# ----------------------------------------------------------------------
def current_staff():
    uid = session.get("staff_user_id")
    if not uid:
        return None
    row = get_db().execute(
        "SELECT * FROM users WHERE user_id = ? AND status = 'active'", (uid,)
    ).fetchone()
    if row is None:
        session.pop("staff_user_id", None)
        return None
    from models import User
    return User.from_row(row)


def _portal_student():
    sid = session.get("portal_student_id")
    if not sid:
        return None
    try:
        return StudentService(get_db()).get_student(sid)
    except SISError:
        return None


def staff_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_staff()
            if user is None:
                flash(i18n.t("auth.staff_signin", locale()), "error")
                return redirect(url_for("staff_login", next=request.path))
            if roles and user.role not in roles:
                if user.role == "teacher":
                    return redirect(url_for("teach_dashboard"))
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def portal_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("portal_student_id"):
            return redirect(url_for("portal_login"))
        return view(*args, **kwargs)
    return wrapped


def _actor():
    user = current_staff()
    if user:
        return f"staff:{user.username}"
    sid = session.get("portal_student_id")
    if sid:
        try:
            return f"student:{StudentService(get_db()).get_student(sid).student_number}"
        except SISError:
            pass
    return "anonymous"


def audit(action, entity_type=None, entity_id=None, details=""):
    AuditService(get_db()).record(_actor(), action, entity_type, entity_id, details)


def paginate(total):
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    return page, pages, PER_PAGE, (page - 1) * PER_PAGE


@app.template_global()
def url_for_page(p):
    args = request.args.to_dict()
    args["page"] = p
    return url_for(request.endpoint, **(request.view_args or {}), **args)


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


# ======================================================================
# Landing & auth
# ======================================================================
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/setup", methods=["GET", "POST"])
def staff_setup():
    auth = AuthService(get_db())
    if auth.list_users():
        return redirect(url_for("staff_login"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw != request.form.get("confirm_password", ""):
            flash("Passwords do not match.", "error")
        else:
            try:
                user = auth.create_user(request.form.get("username", ""), pw, "admin")
                session.clear()
                session["staff_user_id"] = user.user_id
                audit("user.create", "user", user.user_id, "initial admin")
                return redirect(url_for("dashboard"))
            except SISError as e:
                flash(str(e), "error")
    return render_template("staff_setup.html")


@app.route("/login", methods=["GET", "POST"])
def staff_login():
    auth = AuthService(get_db())
    if not auth.list_users():
        return redirect(url_for("staff_setup"))
    if request.method == "POST":
        user = auth.authenticate(request.form.get("username", ""), request.form.get("password", ""))
        if user:
            session.pop("staff_user_id", None)
            session["staff_user_id"] = user.user_id
            audit("auth.login", "user", user.user_id)
            target = _safe_next(request.form.get("next"))
            if user.role == "teacher":
                return redirect(target or url_for("teach_dashboard"))
            if user.role == "accounting":
                return redirect(target or url_for("financial_overview"))
            return redirect(target or url_for("dashboard"))
        audit("auth.login_failed", "user", None, request.form.get("username", ""))
        flash(i18n.t("auth.invalid", locale()), "error")
    return render_template("staff_login.html", next=request.args.get("next", ""))


@app.route("/logout", methods=["POST"])
def staff_logout():
    user = current_staff()
    if user:
        audit("auth.logout", "user", user.user_id)
    session.pop("staff_user_id", None)
    return redirect(url_for("landing"))


# ======================================================================
# Admissions (public application + staff review)
# ======================================================================
@app.route("/apply", methods=["GET", "POST"])
def apply():
    conn = get_db()
    majors = MajorService(conn).list_majors()
    if request.method == "POST":
        f = request.form
        try:
            AdmissionsService(conn).submit_application(
                national_id=f.get("national_id", ""), first_name=f.get("first_name", ""),
                second_name=f.get("second_name", ""), third_name=f.get("third_name", ""),
                last_name=f.get("last_name", ""), name_ar=f.get("name_ar", ""),
                email=f.get("email", ""), phone=f.get("phone", ""),
                date_of_birth=f.get("date_of_birth", ""), gender=f.get("gender", ""),
                nationality=f.get("nationality", ""),
                major_id=int(f["major_id"]) if f.get("major_id") else None,
            )
            audit("admission.submit", "application", None, f.get("national_id", ""))
            flash(i18n.t("adm.submitted", locale()), "success")
            return redirect(url_for("landing"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("apply.html", majors=majors)


@app.route("/admissions")
@staff_required("admin", "registrar")
def admissions_list():
    conn = get_db()
    status = request.args.get("status", "pending")
    apps = AdmissionsService(conn).list_applications(status=None if status == "all" else status)
    majors = {m.major_id: m for m in MajorService(conn).list_majors(status=None)}
    return render_template("admissions.html", applications=apps, majors=majors, status=status)


def _major_name(conn, major_id):
    if not major_id:
        return None
    try:
        return MajorService(conn).get_major(major_id).name(locale())
    except SISError:
        return None


@app.route("/admissions/<int:application_id>/approve", methods=["POST"])
@staff_required("admin", "registrar")
def admissions_approve(application_id):
    conn = get_db()
    try:
        student = AdmissionsService(conn).approve(application_id, reviewer=_actor())
        # Charge registration fee on admission.
        current = TermService(conn).get_current_term()
        if current:
            FeeService(conn).charge_registration_fee(student.student_id, current.term_id)
        audit("admission.approve", "student", student.student_id, student.student_number)
        flash(f"{i18n.t('status.approved', locale())} — {student.student_number}", "success")
        # Acceptance email (automatic if enabled in Settings).
        if get_setting(conn, "auto_email_on_approval", "1") == "1":
            status = MailService(conn).send_acceptance(
                student, _major_name(conn, student.major_id))
            audit("email.acceptance", "student", student.student_id, status)
            flash(i18n.t(f"mail.{status}", locale()), "success" if status != "failed" else "error")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("admissions_list"))


@app.route("/admissions/<int:application_id>/email", methods=["POST"])
@staff_required("admin", "registrar")
def admissions_send_email(application_id):
    """Manual (re)send of the acceptance email for an approved application."""
    conn = get_db()
    app_row = AdmissionsService(conn).get_application(application_id)
    if app_row.status != "approved" or not app_row.student_id:
        flash("Application is not approved yet.", "error")
        return redirect(url_for("admissions_list"))
    student = StudentService(conn).get_student(app_row.student_id)
    status = MailService(conn).send_acceptance(student, _major_name(conn, student.major_id))
    audit("email.acceptance", "student", student.student_id, f"manual {status}")
    flash(i18n.t(f"mail.{status}", locale()), "success" if status != "failed" else "error")
    return redirect(url_for("admissions_list", status="all"))


@app.route("/emails")
@staff_required("admin")
def emails_log():
    svc = MailService(get_db())
    page, pages, limit, offset = paginate(svc.count())
    return render_template("emails_log.html", entries=svc.list_log(limit=limit, offset=offset),
                           page=page, pages=pages)


@app.route("/admissions/<int:application_id>/reject", methods=["POST"])
@staff_required("admin", "registrar")
def admissions_reject(application_id):
    try:
        AdmissionsService(get_db()).reject(application_id, reviewer=_actor(),
                                            note=request.form.get("note", ""))
        audit("admission.reject", "application", application_id)
        flash("Application rejected.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("admissions_list"))


# ======================================================================
# Registrar dashboard
# ======================================================================
@app.route("/registrar")
@staff_required("admin", "registrar")
def dashboard():
    conn = get_db()
    current = TermService(conn).get_current_term()
    total_fees = conn.execute("SELECT COALESCE(SUM(amount+tax_amount),0) t FROM fees WHERE status!='waived'").fetchone()["t"]
    total_paid = conn.execute("SELECT COALESCE(SUM(amount_paid),0) t FROM payments").fetchone()["t"]
    stats = {
        "active_students": StudentService(conn).count_students(status="active"),
        "teachers": TeacherService(conn).count_teachers(status="active"),
        "courses": CourseService(conn).count_courses(),
        "majors": len(MajorService(conn).list_majors(status=None)),
        "pending_admissions": AdmissionsService(conn).count_pending(),
        "outstanding_balance": round(total_fees - total_paid, 2),
    }
    return render_template("dashboard.html", stats=stats, current=current)


# ======================================================================
# Students
# ======================================================================
@app.route("/students")
@staff_required("admin", "registrar")
def students_list():
    conn = get_db()
    query = request.args.get("q", "").strip()
    svc = StudentService(conn)
    if query:
        students, page, pages = svc.search_students(query), 1, 1
    else:
        page, pages, limit, offset = paginate(svc.count_students())
        students = svc.list_students(limit=limit, offset=offset)
    majors = {m.major_id: m for m in MajorService(conn).list_majors(status=None)}
    return render_template("students_list.html", students=students, query=query,
                           page=page, pages=pages, majors=majors)


@app.route("/students/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def students_add():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        try:
            s = StudentService(conn).add_student(
                first_name=f["first_name"], second_name=f.get("second_name", ""),
                third_name=f.get("third_name", ""), last_name=f["last_name"],
                name_ar=f.get("name_ar", ""), national_id=f.get("national_id") or None,
                email=f["email"], phone=f.get("phone", ""),
                date_of_birth=f.get("date_of_birth", ""), gender=f.get("gender", "male"),
                nationality=f.get("nationality", "Saudi"),
                major_id=int(f["major_id"]) if f.get("major_id") else None,
                advisor_id=int(f["advisor_id"]) if f.get("advisor_id") else None,
            )
            audit("student.create", "student", s.student_id, s.student_number)
            flash(f"Student {s.student_number} added.", "success")
            return redirect(url_for("students_detail", student_id=s.student_id))
        except SISError as e:
            flash(str(e), "error")
    return render_template("student_form.html", majors=MajorService(conn).list_majors(status=None),
                           teachers=TeacherService(conn).list_teachers(status="active"),
                           today=date.today().isoformat())


@app.route("/students/<int:student_id>")
@staff_required("admin", "registrar")
def students_detail(student_id):
    conn = get_db()
    students, enrollments, gpa = StudentService(conn), EnrollmentService(conn), GPAService(conn)
    fees, terms, sections, courses = FeeService(conn), TermService(conn), SectionService(conn), CourseService(conn)
    student = students.get_student(student_id)
    rows = enrollments.list_student_enrollments(student_id)
    by_term = {}
    for row in rows:
        by_term.setdefault(row["term_id"], []).append(row)
    transcript = []
    for term_id, trows in sorted(by_term.items()):
        transcript.append((terms.get_term(term_id), trows, gpa.calculate_term_gpa(student_id, term_id)))
    cum = gpa.calculate_cumulative_gpa(student_id)
    major = MajorService(conn).get_major(student.major_id) if student.major_id else None
    advisor = TeacherService(conn).get_teacher(student.advisor_id) if student.advisor_id else None
    return render_template(
        "student_detail.html", student=student, transcript_terms=transcript,
        cum_gpa=cum, standing=gpa.get_academic_standing(cum, locale()),
        earned_hours=gpa.get_earned_credit_hours(student_id),
        remaining_hours=gpa.get_remaining_credit_hours(student_id),
        fee_statement=fees.get_fee_statement(student_id), balance=fees.get_student_balance(student_id),
        major=major, advisor=advisor,
        teachers=TeacherService(conn).list_teachers(status="active"),
        majors=MajorService(conn).list_majors(status=None),
    )


@app.route("/students/<int:student_id>/status", methods=["POST"])
@staff_required("admin", "registrar")
def students_set_status(student_id):
    try:
        StudentService(get_db()).set_status(student_id, request.form["status"])
        audit("student.status", "student", student_id, request.form["status"])
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/<int:student_id>/advisor", methods=["POST"])
@staff_required("admin", "registrar")
def students_set_advisor(student_id):
    advisor_id = int(request.form["advisor_id"]) if request.form.get("advisor_id") else None
    StudentService(get_db()).set_advisor(student_id, advisor_id)
    audit("student.advisor", "student", student_id, str(advisor_id))
    flash(i18n.t("flash.saved", locale()), "success")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/<int:student_id>/portal-reset", methods=["POST"])
@staff_required("admin", "registrar")
def students_portal_reset(student_id):
    conn = get_db()
    student = StudentService(conn).get_student(student_id)
    AuthService(conn).set_student_password(student_id, student.national_id or None)
    audit("student.portal_reset", "student", student_id)
    flash(i18n.t("flash.saved", locale()), "success")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/import", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def students_import():
    conn = get_db()
    if request.method == "POST":
        upload = request.files.get("csv_file")
        if not upload or not upload.filename:
            flash("Please choose a CSV file.", "error")
            return redirect(url_for("students_import"))
        text = io.StringIO(upload.stream.read().decode("utf-8-sig"))
        ok, errors = csv_io.import_students(conn, text)
        if ok:
            audit("student.import", "student", None, f"{len(ok)} imported")
            flash(f"Imported {len(ok)} student(s).", "success")
        if errors:
            flash(f"{len(errors)} row(s) failed: " + " | ".join(errors[:5]), "error")
        return redirect(url_for("students_list"))
    return render_template("import_form.html", entity="students",
                           template_url=url_for("students_import_template"))


@app.route("/students/export.csv")
@staff_required("admin", "registrar")
def students_export():
    buf = io.BytesIO(csv_io.export_students(get_db()).encode("utf-8-sig"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="students.csv")


@app.route("/students/import/template.csv")
@staff_required("admin", "registrar")
def students_import_template():
    buf = io.BytesIO(csv_io.students_template().encode("utf-8"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="students_template.csv")


# ======================================================================
# Teachers
# ======================================================================
@app.route("/teachers")
@staff_required("admin", "registrar")
def teachers_list():
    conn = get_db()
    svc = TeacherService(conn)
    page, pages, limit, offset = paginate(svc.count_teachers())
    return render_template("teachers_list.html", teachers=svc.list_teachers(limit=limit, offset=offset),
                           page=page, pages=pages)


@app.route("/teachers/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def teachers_add():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        try:
            t = TeacherService(conn).add_teacher(
                first_name=f["first_name"], last_name=f["last_name"], email=f["email"],
                name_ar=f.get("name_ar", ""), gender=f.get("gender", "male"),
                phone=f.get("phone", ""), title=f.get("title", ""),
                department_id=int(f["department_id"]) if f.get("department_id") else None,
            )
            audit("teacher.create", "teacher", t.teacher_id, t.employee_number)
            flash(i18n.t("flash.saved", locale()), "success")
            return redirect(url_for("teachers_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("teacher_form.html", departments=_departments(conn),
                           today=date.today().isoformat())


@app.route("/teachers/export.csv")
@staff_required("admin", "registrar")
def teachers_export():
    buf = io.BytesIO(csv_io.export_teachers(get_db()).encode("utf-8-sig"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="teachers.csv")


@app.route("/teachers/import", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def teachers_import():
    conn = get_db()
    if request.method == "POST":
        upload = request.files.get("csv_file")
        if not upload or not upload.filename:
            flash("Please choose a CSV file.", "error")
            return redirect(url_for("teachers_import"))
        text = io.StringIO(upload.stream.read().decode("utf-8-sig"))
        ok, errors = csv_io.import_teachers(conn, text)
        if ok:
            flash(f"Imported {len(ok)} teacher(s).", "success")
        if errors:
            flash(f"{len(errors)} row(s) failed: " + " | ".join(errors[:5]), "error")
        return redirect(url_for("teachers_list"))
    return render_template("import_form.html", entity="teachers",
                           template_url=url_for("teachers_import_template"))


@app.route("/teachers/import/template.csv")
@staff_required("admin", "registrar")
def teachers_import_template():
    buf = io.BytesIO(csv_io.teachers_template().encode("utf-8"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="teachers_template.csv")


# ======================================================================
# Courses
# ======================================================================
@app.route("/courses")
@staff_required("admin", "registrar")
def courses_list():
    conn = get_db()
    svc = CourseService(conn)
    page, pages, limit, offset = paginate(svc.count_courses())
    return render_template("courses_list.html", courses=svc.list_courses(limit=limit, offset=offset),
                           page=page, pages=pages)


@app.route("/courses/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def courses_add():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        try:
            c = CourseService(conn).add_course(
                course_code=f["course_code"], title=f["title"], title_ar=f.get("title_ar", ""),
                credit_hours=int(f["credit_hours"]), price=float(f.get("price") or 0),
                department_id=int(f["department_id"]) if f.get("department_id") else None,
                major_id=int(f["major_id"]) if f.get("major_id") else None,
                description=f.get("description", ""),
            )
            audit("course.create", "course", c.course_id, c.course_code)
            flash(f"Course {c.course_code} added.", "success")
            return redirect(url_for("courses_detail", course_id=c.course_id))
        except SISError as e:
            flash(str(e), "error")
    return render_template("course_form.html", departments=_departments(conn),
                           majors=MajorService(conn).list_majors(status=None))


@app.route("/courses/<int:course_id>")
@staff_required("admin", "registrar")
def courses_detail(course_id):
    conn = get_db()
    courses = CourseService(conn)
    course = courses.get_course(course_id)
    return render_template("course_detail.html", course=course,
                           prerequisite_groups=courses.get_prerequisite_groups(course_id),
                           all_courses=courses.list_courses(),
                           assigned=courses.get_teachers(course_id),
                           teachers=TeacherService(conn).list_teachers(status="active"))


@app.route("/courses/<int:course_id>/teacher", methods=["POST"])
@staff_required("admin", "registrar")
def courses_assign_teacher(course_id):
    CourseService(get_db()).assign_teacher(course_id, int(request.form["teacher_id"]))
    audit("course.teacher_add", "course", course_id, request.form["teacher_id"])
    flash(i18n.t("flash.saved", locale()), "success")
    return redirect(url_for("courses_detail", course_id=course_id))


@app.route("/courses/<int:course_id>/teacher/<int:teacher_id>/remove", methods=["POST"])
@staff_required("admin", "registrar")
def courses_remove_teacher(course_id, teacher_id):
    CourseService(get_db()).remove_teacher(course_id, teacher_id)
    return redirect(url_for("courses_detail", course_id=course_id))


@app.route("/courses/<int:course_id>/prerequisites", methods=["POST"])
@staff_required("admin", "registrar")
def courses_add_prereq(course_id):
    try:
        CourseService(get_db()).add_prerequisite(course_id, int(request.form["prerequisite_course_id"]))
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("courses_detail", course_id=course_id))


@app.route("/courses/export.csv")
@staff_required("admin", "registrar")
def courses_export():
    buf = io.BytesIO(csv_io.export_courses(get_db()).encode("utf-8-sig"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="courses.csv")


@app.route("/courses/import", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def courses_import():
    conn = get_db()
    if request.method == "POST":
        upload = request.files.get("csv_file")
        if not upload or not upload.filename:
            flash("Please choose a CSV file.", "error")
            return redirect(url_for("courses_import"))
        text = io.StringIO(upload.stream.read().decode("utf-8-sig"))
        ok, errors = csv_io.import_courses(conn, text)
        if ok:
            flash(f"Imported {len(ok)} course(s).", "success")
        if errors:
            flash(f"{len(errors)} row(s) failed: " + " | ".join(errors[:5]), "error")
        return redirect(url_for("courses_list"))
    return render_template("import_form.html", entity="courses",
                           template_url=url_for("courses_import_template"))


@app.route("/courses/import/template.csv")
@staff_required("admin", "registrar")
def courses_import_template():
    buf = io.BytesIO(csv_io.courses_template().encode("utf-8"))
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="courses_template.csv")


# ======================================================================
# Majors
# ======================================================================
@app.route("/majors")
@staff_required("admin", "registrar")
def majors_list():
    conn = get_db()
    return render_template("majors_list.html", majors=MajorService(conn).list_majors(status=None),
                           departments=_departments(conn))


@app.route("/majors/add", methods=["POST"])
@staff_required("admin", "registrar")
def majors_add():
    f = request.form
    try:
        m = MajorService(get_db()).add_major(
            code=f["code"], name_en=f["name_en"], name_ar=f["name_ar"],
            required_credit_hours=int(f.get("required_credit_hours") or 120),
            department_id=int(f["department_id"]) if f.get("department_id") else None,
            gender=f.get("gender", "any"),
        )
        audit("major.create", "major", m.major_id, m.code)
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("majors_list"))


# ======================================================================
# Terms & academic years
# ======================================================================
@app.route("/terms")
@staff_required("admin", "registrar")
def terms_list():
    conn = get_db()
    return render_template("terms_list.html", terms=TermService(conn).list_terms(),
                           years=TermService(conn).list_years())


@app.route("/terms/add", methods=["POST"])
@staff_required("admin", "registrar")
def terms_add():
    conn = get_db()
    f = request.form
    try:
        year = None
        if f.get("year_name"):
            year = TermService(conn).get_or_create_year(f["year_name"]).year_id
        TermService(conn).add_term(
            f["name"], f["start_date"], f["end_date"], name_ar=f.get("name_ar", ""),
            academic_year_id=year, kind=f.get("kind", "regular"),
            add_deadline=f.get("add_deadline") or None, drop_deadline=f.get("drop_deadline") or None,
            grades_deadline=f.get("grades_deadline") or None,
        )
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("terms_list"))


@app.route("/terms/<int:term_id>/set-current", methods=["POST"])
@staff_required("admin", "registrar")
def terms_set_current(term_id):
    TermService(get_db()).set_current_term(term_id)
    audit("term.set_current", "term", term_id)
    flash(i18n.t("flash.saved", locale()), "success")
    return redirect(url_for("terms_list"))


# ======================================================================
# Sections
# ======================================================================
@app.route("/sections")
@staff_required("admin", "registrar")
def sections_list():
    conn = get_db()
    sections, courses, teachers, terms = SectionService(conn), CourseService(conn), TeacherService(conn), TermService(conn)
    term_id = request.args.get("term_id", type=int)
    page, pages, limit, offset = paginate(sections.count_sections(term_id=term_id))
    rows = []
    for sec in sections.list_sections(term_id=term_id, limit=limit, offset=offset):
        rows.append({"section": sec, "course": courses.get_course(sec.course_id),
                     "teacher": teachers.get_teacher(sec.teacher_id) if sec.teacher_id else None,
                     "enrolled": sections.get_enrolled_count(sec.section_id)})
    return render_template("sections_list.html", sections=rows, terms=terms.list_terms(),
                           selected_term_id=term_id, page=page, pages=pages)


@app.route("/sections/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def sections_add():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        try:
            sec = SectionService(conn).add_section(
                course_id=int(f["course_id"]), term_id=int(f["term_id"]),
                section_number=f["section_number"], gender=f.get("gender", "male"),
                teacher_id=int(f["teacher_id"]) if f.get("teacher_id") else None,
                room=f.get("room", ""), days=",".join(f.getlist("days")),
                start_time=f.get("start_time", ""), end_time=f.get("end_time", ""),
                capacity=int(f["capacity"]),
            )
            audit("section.create", "section", sec.section_id, f"#{sec.section_number}")
            flash(i18n.t("flash.saved", locale()), "success")
            return redirect(url_for("sections_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("section_form.html", courses=CourseService(conn).list_courses(),
                           terms=TermService(conn).list_terms(),
                           teachers=TeacherService(conn).list_teachers(status="active"))


@app.route("/sections/<int:section_id>")
@staff_required("admin", "registrar")
def sections_detail(section_id):
    conn = get_db()
    sections, courses, teachers, students = SectionService(conn), CourseService(conn), TeacherService(conn), StudentService(conn)
    section = sections.get_section(section_id)
    course = courses.get_course(section.course_id)
    roster = sections.get_roster(section_id)
    enrolled_ids = {r["student_id"] for r in roster}
    # Only same-gender active students may be added.
    eligible = [s for s in students.list_students(status="active")
                if s.student_id not in enrolled_ids and s.gender == section.gender]
    return render_template("section_detail.html", section=section, course=course,
                           teacher=teachers.get_teacher(section.teacher_id) if section.teacher_id else None,
                           teachers_all=teachers.list_teachers(status="active"),
                           roster=roster, eligible_students=eligible,
                           waitlist_entries=WaitlistService(conn).list_for_section(section_id))


@app.route("/sections/<int:section_id>/teacher", methods=["POST"])
@staff_required("admin", "registrar")
def sections_set_teacher(section_id):
    """Reassign the section's teacher; it moves to the new teacher's
    portal immediately (the portal reads live from sections.teacher_id)."""
    conn = get_db()
    teacher_id = int(request.form["teacher_id"])
    SectionService(conn).update_section(section_id, teacher_id=teacher_id)
    audit("section.teacher", "section", section_id, f"teacher_id={teacher_id}")
    flash(i18n.t("flash.saved", locale()), "success")
    return redirect(url_for("sections_detail", section_id=section_id))


@app.route("/sections/<int:section_id>/enroll", methods=["POST"])
@staff_required("admin", "registrar")
def sections_enroll_student(section_id):
    conn = get_db()
    student_id = int(request.form["student_id"])
    try:
        status, _ = EnrollmentService(conn).enroll_or_waitlist(student_id, section_id)
        section = SectionService(conn).get_section(section_id)
        if status == "enrolled":
            current = TermService(conn).get_current_term()
            FeeService(conn).bill_course(student_id, section.course_id, section.term_id)
        audit(f"enrollment.{status}", "section", section_id, f"student_id={student_id}")
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("sections_detail", section_id=section_id))


@app.route("/sections/<int:section_id>/drop/<int:student_id>", methods=["POST"])
@staff_required("admin", "registrar")
def sections_drop_student(section_id, student_id):
    try:
        EnrollmentService(get_db()).drop_student(student_id, section_id)
        audit("enrollment.drop", "section", section_id, f"student_id={student_id}")
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("sections_detail", section_id=section_id))


@app.route("/sections/<int:section_id>/grades", methods=["POST"])
@staff_required("admin", "registrar")
def sections_submit_grades(section_id):
    _apply_grades(section_id)
    return redirect(url_for("sections_detail", section_id=section_id))


def _apply_grades(section_id, enforce_deadline=False):
    """Reads grade_<id> (total) or cw_<id>+fin_<id> (coursework/final
    breakdown) fields. A filled breakdown wins over the total field.
    With enforce_deadline (teacher side) nothing is saved after the term's
    grades deadline; registrar/admin can still correct grades."""
    grading = GradingService(get_db())
    if enforce_deadline:
        try:
            grading.check_editing_open(section_id)
        except SISError as e:
            flash(str(e), "error")
            return
    updated, errors = 0, []
    student_ids = {int(k.split("_", 1)[1]) for k in request.form
                   if k.startswith(("grade_", "cw_", "fin_"))}
    for sid in student_ids:
        cw = request.form.get(f"cw_{sid}", "").strip()
        fin = request.form.get(f"fin_{sid}", "").strip()
        total = request.form.get(f"grade_{sid}", "").strip()
        try:
            if cw and fin:
                grading.assign_breakdown_by_pair(sid, section_id, float(cw), float(fin))
                audit("grade.assign", "section", section_id,
                      f"student_id={sid} cw={cw} final={fin}")
                updated += 1
            elif total:
                grading.assign_grade_by_pair(sid, section_id, total)
                audit("grade.assign", "section", section_id, f"student_id={sid} mark={total}")
                updated += 1
        except (SISError, ValueError) as e:
            errors.append(str(e))
    if updated:
        flash(f"Saved {updated} grade(s).", "success")
    if errors:
        flash("; ".join(errors), "error")


# ======================================================================
# Teacher portal
# ======================================================================
def _own_section_or_403(section_id):
    section = SectionService(get_db()).get_section(section_id)
    if section.teacher_id != current_staff().teacher_id:
        abort(403)
    return section


@app.route("/teach")
@staff_required("teacher")
def teach_dashboard():
    conn = get_db()
    user = current_staff()
    sections, courses, terms = SectionService(conn), CourseService(conn), TermService(conn)
    rows = []
    for sec in sections.list_sections(teacher_id=user.teacher_id):
        rows.append({"section": sec, "course": courses.get_course(sec.course_id),
                     "term": terms.get_term(sec.term_id),
                     "enrolled": sections.get_enrolled_count(sec.section_id)})
    return render_template("teach_dashboard.html", sections=rows,
                           teacher=TeacherService(conn).get_teacher(user.teacher_id))


@app.route("/teach/sections/<int:section_id>")
@staff_required("teacher")
def teach_section(section_id):
    conn = get_db()
    section = _own_section_or_403(section_id)
    grading = GradingService(conn)
    return render_template("teach_section.html", section=section,
                           course=CourseService(conn).get_course(section.course_id),
                           term=TermService(conn).get_term(section.term_id),
                           roster=SectionService(conn).get_roster(section_id),
                           locked=grading.editing_locked(section_id),
                           grades_deadline=grading.grades_deadline_for_section(section_id))


@app.route("/teach/sections/<int:section_id>/grades", methods=["POST"])
@staff_required("teacher")
def teach_submit_grades(section_id):
    _own_section_or_403(section_id)
    _apply_grades(section_id, enforce_deadline=True)
    return redirect(url_for("teach_section", section_id=section_id))


@app.route("/teach/sections/<int:section_id>/email", methods=["POST"])
@staff_required("teacher")
def teach_email_section(section_id):
    """Group email from the teacher to every enrolled student in their
    own section (logged per recipient in the email log)."""
    conn = get_db()
    _own_section_or_403(section_id)
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    if not subject or not body:
        flash(i18n.t("common.required_note", locale()), "error")
        return redirect(url_for("teach_section", section_id=section_id))
    rows = conn.execute(
        """SELECT s.email FROM enrollments e
           JOIN students s ON s.student_id = e.student_id
           WHERE e.section_id = ? AND e.status IN ('enrolled', 'completed')""",
        (section_id,),
    ).fetchall()
    mail = MailService(conn)
    for r in rows:
        mail.send(r["email"], subject, body, kind="section_email")
    audit("email.section", "section", section_id, f"{len(rows)} recipients")
    flash(i18n.t("mail.broadcast_done", locale(), n=len(rows)), "success")
    return redirect(url_for("teach_section", section_id=section_id))


# ======================================================================
# Accounting
# ======================================================================
@app.route("/financial")
@staff_required("admin", "accounting")
def financial_overview():
    conn = get_db()
    total = conn.execute("SELECT COALESCE(SUM(amount+tax_amount),0) t FROM fees WHERE status!='waived'").fetchone()["t"]
    paid = conn.execute("SELECT COALESCE(SUM(amount_paid),0) t FROM payments").fetchone()["t"]
    by_type = conn.execute(
        "SELECT fee_type, COALESCE(SUM(amount+tax_amount),0) total FROM fees "
        "WHERE status!='waived' GROUP BY fee_type"
    ).fetchall()
    return render_template("financial.html", total=round(total, 2), paid=round(paid, 2),
                           outstanding=round(total - paid, 2), by_type=by_type)


# ======================================================================
# Users, roles, settings, audit (admin)
# ======================================================================
@app.route("/users")
@staff_required("admin")
def users_list():
    conn = get_db()
    auth, teachers = AuthService(conn), TeacherService(conn)
    rows = [{"user": u, "teacher": teachers.get_teacher(u.teacher_id) if u.teacher_id else None}
            for u in auth.list_users()]
    return render_template("users_list.html", users=rows,
                           teachers=teachers.list_teachers(status="active"))


@app.route("/users/add", methods=["POST"])
@staff_required("admin")
def users_add():
    f = request.form
    try:
        u = AuthService(get_db()).create_user(
            f["username"], f["password"], f["role"],
            teacher_id=int(f["teacher_id"]) if f.get("teacher_id") else None)
        audit("user.create", "user", u.user_id, f"role={u.role}")
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:user_id>/status", methods=["POST"])
@staff_required("admin")
def users_set_status(user_id):
    conn = get_db()
    auth, me = AuthService(conn), current_staff()
    status = request.form.get("status", "")
    try:
        target = auth.get_user(user_id)
        if status == "disabled" and (target.user_id == me.user_id or
                                     (target.role == "admin" and auth.count_admins() <= 1)):
            flash("You can't disable the last active admin (or yourself).", "error")
        else:
            auth.set_user_status(user_id, status)
            audit("user.status", "user", user_id, status)
            flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("users_list"))


@app.route("/settings", methods=["GET", "POST"])
@staff_required("admin")
def settings():
    conn = get_db()
    text_keys = ("registration_fee", "vat_rate", "institution_name_en", "institution_name_ar",
                 "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from",
                 "acceptance_subject", "acceptance_body")
    toggle_keys = ("lms_enabled", "email_enabled", "auto_email_on_approval")
    if request.method == "POST":
        for key in text_keys:
            if key in request.form:
                set_setting(conn, key, request.form[key])
        for key in toggle_keys:
            set_setting(conn, key, "1" if request.form.get(key) else "0")
        audit("settings.update")
        flash(i18n.t("flash.saved", locale()), "success")
        return redirect(url_for("settings"))
    all_keys = text_keys + toggle_keys
    return render_template("settings.html", settings={k: get_setting(conn, k, "") for k in all_keys})


@app.route("/audit")
@staff_required("admin", "registrar")
def audit_log():
    svc = AuditService(get_db())
    page, pages, limit, offset = paginate(svc.count())
    return render_template("audit_log.html", entries=svc.list_entries(limit=limit, offset=offset),
                           page=page, pages=pages)


@app.route("/requests")
@staff_required("admin", "registrar")
def requests_list():
    conn = get_db()
    status = request.args.get("status", "pending")
    rows = RequestService(conn).list_all(status=None if status == "all" else status)
    return render_template("requests_admin.html", requests=rows, status=status)


@app.route("/requests/<int:request_id>/review", methods=["POST"])
@staff_required("admin", "registrar")
def requests_review(request_id):
    try:
        RequestService(get_db()).review(request_id, request.form["decision"], _actor(),
                                        note=request.form.get("note", ""))
        audit("request.review", "request", request_id, request.form["decision"])
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("requests_list"))


@app.route("/lms")
def lms_placeholder():
    return render_template("lms.html")


# ======================================================================
# Student portal
# ======================================================================
@app.route("/portal/login", methods=["GET", "POST"])
def portal_login():
    if request.method == "POST":
        auth = AuthService(get_db())
        num = request.form.get("student_number", "").strip()
        student = auth.authenticate_student(num, request.form.get("password", ""))
        if student:
            session.pop("portal_student_id", None)
            session["portal_student_id"] = student.student_id
            audit("portal.login", "student", student.student_id)
            return redirect(url_for("portal_dashboard"))
        flash(i18n.t("auth.invalid", locale()), "error")
    return render_template("portal_login.html")


@app.route("/portal/logout", methods=["POST"])
def portal_logout():
    session.pop("portal_student_id", None)
    return redirect(url_for("landing"))


@app.route("/portal")
@portal_login_required
def portal_dashboard():
    conn = get_db()
    sid = session["portal_student_id"]
    gpa, fees = GPAService(conn), FeeService(conn)
    cum = gpa.calculate_cumulative_gpa(sid)
    return render_template("portal_dashboard.html", student=StudentService(conn).get_student(sid),
                           cum_gpa=cum, standing=gpa.get_academic_standing(cum, locale()),
                           earned_hours=gpa.get_earned_credit_hours(sid),
                           remaining_hours=gpa.get_remaining_credit_hours(sid),
                           balance=fees.get_student_balance(sid))


@app.route("/portal/registration", methods=["GET", "POST"])
@portal_login_required
def portal_registration():
    conn = get_db()
    sid = session["portal_student_id"]
    student = StudentService(conn).get_student(sid)
    enroll_svc, wl = EnrollmentService(conn), WaitlistService(conn)
    if request.method == "POST":
        action = request.form.get("action", "enroll")
        section_id = int(request.form["section_id"])
        try:
            if action == "drop":
                enroll_svc.drop_student(sid, section_id)
                audit("enrollment.drop", "section", section_id, "self-service")
                flash(i18n.t("flash.saved", locale()), "success")
            else:
                status, _ = enroll_svc.enroll_or_waitlist(sid, section_id)
                if status == "enrolled":
                    sec = SectionService(conn).get_section(section_id)
                    FeeService(conn).bill_course(sid, sec.course_id, sec.term_id)
                audit(f"enrollment.{status}", "section", section_id, "self-service")
                flash(i18n.t("flash.saved", locale()), "success")
        except SISError as e:
            flash(str(e), "error")
        return redirect(url_for("portal_registration"))

    sections, courses, teachers, terms = SectionService(conn), CourseService(conn), TeacherService(conn), TermService(conn)
    my_rows = enroll_svc.list_student_enrollments(sid)
    enrolled_ids = {r["section_id"] for r in my_rows if r["status"] != "dropped"}
    my_courses = [r for r in my_rows if r["status"] == "enrolled"]
    # Only open, same-gender sections the student isn't already in.
    available = []
    for sec in sections.list_sections(gender=student.gender):
        if sec.status != "open" or sec.section_id in enrolled_ids:
            continue
        available.append({"section": sec, "course": courses.get_course(sec.course_id),
                          "term": terms.get_term(sec.term_id),
                          "teacher": teachers.get_teacher(sec.teacher_id) if sec.teacher_id else None,
                          "enrolled": sections.get_enrolled_count(sec.section_id)})
    return render_template("portal_registration.html", available=available,
                           my_courses=my_courses, sections=sections, courses=courses, terms=terms)


@app.route("/portal/grades")
@portal_login_required
def portal_grades():
    conn = get_db()
    sid = session["portal_student_id"]
    terms, gpa = TermService(conn), GPAService(conn)
    term_id = request.args.get("term_id", type=int)
    rows = EnrollmentService(conn).list_student_enrollments(sid, term_id=term_id)
    by_term = {}
    for r in rows:
        by_term.setdefault(r["term_id"], []).append(r)
    blocks = []
    for tid, trows in sorted(by_term.items()):
        blocks.append((terms.get_term(tid), trows, gpa.calculate_term_gpa(sid, tid)))
    # One combined dropdown: "academic year — term".
    years = {y.year_id: y for y in terms.list_years()}
    term_options = []
    for tm in terms.list_terms():
        year = years.get(tm.academic_year_id)
        label = f"{year.name} — {tm.display_name(locale())}" if year else tm.display_name(locale())
        term_options.append((tm.term_id, label))
    cum = gpa.calculate_cumulative_gpa(sid)
    return render_template("portal_grades.html", blocks=blocks, cum_gpa=cum,
                           standing=gpa.get_academic_standing(cum, locale()),
                           term_options=term_options, sel_term=term_id)


@app.route("/portal/financial")
@portal_login_required
def portal_financial():
    conn = get_db()
    sid = session["portal_student_id"]
    fees = FeeService(conn)
    return render_template("portal_financial.html", fee_statement=fees.get_fee_statement(sid),
                           balance=fees.get_student_balance(sid))


@app.route("/portal/financial/<int:fee_id>/pay", methods=["POST"])
@portal_login_required
def portal_pay(fee_id):
    conn = get_db()
    fees = FeeService(conn)
    fee = fees.get_fee(fee_id)
    if fee.student_id != session["portal_student_id"]:
        abort(403)
    try:
        fees.record_payment(fee_id, float(request.form["amount_paid"]), payment_method="Self-service")
        audit("fee.payment", "fee", fee_id, "self-service")
        flash(i18n.t("flash.saved", locale()), "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("portal_financial"))


@app.route("/portal/services", methods=["GET", "POST"])
@portal_login_required
def portal_services():
    conn = get_db()
    sid = session["portal_student_id"]
    svc = RequestService(conn)
    if request.method == "POST":
        try:
            svc.submit(sid, request.form["kind"], request.form.get("details", ""))
            audit("request.submit", "student", sid, request.form["kind"])
            flash(i18n.t("adm.submitted", locale()), "success")
        except SISError as e:
            flash(str(e), "error")
        return redirect(url_for("portal_services"))
    return render_template("portal_services.html", requests=svc.list_for_student(sid),
                           kinds=["deferral", "major_transfer", "exam_deferral", "equivalency",
                                  "financial_aid", "other"])


@app.route("/portal/settings", methods=["GET", "POST"])
@portal_login_required
def portal_settings():
    conn = get_db()
    sid = session["portal_student_id"]
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw and pw == request.form.get("confirm_password", ""):
            AuthService(conn).set_student_password(sid, pw)
            audit("portal.password_change", "student", sid)
            flash(i18n.t("flash.saved", locale()), "success")
        else:
            flash("Passwords empty or do not match.", "error")
        return redirect(url_for("portal_settings"))
    return render_template("portal_settings.html", student=StudentService(conn).get_student(sid))


if __name__ == "__main__":
    app.run(debug=os.environ.get("SIS_DEBUG") == "1")
