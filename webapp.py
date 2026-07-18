"""Web interface for the Student Information System.

Development:
    pip install -r requirements.txt
    python webapp.py            # http://127.0.0.1:5000, debugger OFF
Production:
    SIS_SECRET_KEY=... gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app

Three sign-in surfaces share this app:
    /login         admin + registrar (full records) and teachers
    /teach         a teacher's own sections and grade entry
    /portal/login  student self-service, scoped to their own record

This is a thin presentation layer -- every business rule (capacity,
prerequisites, schedule conflicts, GPA math, payment validation) still
lives in the service modules and is unchanged from the CLI. The web
layer adds authentication, authorization, CSRF protection, pagination,
and the audit trail.
"""

import math
import os
import secrets as _secrets
import io
from datetime import date
from functools import wraps

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for,
)

from database import get_connection, initialize_database
from exceptions import SISError
from audit_service import AuditService
from auth_service import AuthService
from student_service import StudentService
from teacher_service import TeacherService
from course_service import CourseService
from term_service import TermService
from section_service import SectionService
from enrollment_service import EnrollmentService
from grading_service import GradingService
from gpa_service import GPAService
from fee_service import FeeService
from waitlist_service import WaitlistService
import bulk_import
import pdf_reports

app = Flask(__name__)

# The session-signing key comes from the environment. Without it, a random
# per-process key is generated: fine for local development (sessions just
# reset on restart) but never a hardcoded secret in source control.
app.secret_key = os.environ.get("SIS_SECRET_KEY") or _secrets.token_hex(32)
if not os.environ.get("SIS_SECRET_KEY"):
    app.logger.warning(
        "SIS_SECRET_KEY is not set -- using a random key for this run only. "
        "Set it in the environment before deploying (sessions won't survive "
        "restarts or work across multiple workers without it)."
    )

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # CSV imports; nothing bigger is expected
)

PER_PAGE = 25

STATUS_KIND = {
    "active": "default", "completed": "default", "paid": "default",
    "open": "default", "graduated": "default", "waived": "default", "promoted": "default",
    "enrolled": "progress", "partial": "progress", "pending": "progress", "closed": "progress",
    "waiting": "progress",
    "suspended": "attention", "withdrawn": "attention", "dropped": "attention",
    "overdue": "attention", "cancelled": "attention", "inactive": "attention", "skipped": "attention",
}
app.jinja_env.globals["status_kind"] = lambda s: STATUS_KIND.get(s, "default")


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


@app.context_processor
def inject_current_term():
    return {"current_term": TermService(get_db()).get_current_term()}


@app.context_processor
def inject_portal_student():
    student_id = session.get("portal_student_id")
    if not student_id:
        return {"portal_student": None}
    try:
        return {"portal_student": StudentService(get_db()).get_student(student_id)}
    except SISError:
        return {"portal_student": None}


@app.errorhandler(SISError)
def handle_sis_error(e):
    flash(str(e), "error")
    return redirect(request.referrer or url_for("landing"))


def _departments(conn):
    return conn.execute("SELECT * FROM departments ORDER BY name").fetchall()


# ----------------------------------------------------------------------
# CSRF protection: every POST form must echo back the per-session token.
# ----------------------------------------------------------------------

def _csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = _secrets.token_hex(16)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = _csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf_token", "")
        supplied = request.form.get("csrf_token", "")
        if not token or not _secrets.compare_digest(token, supplied):
            abort(400, description="CSRF token missing or invalid. Reload the page and try again.")


# ----------------------------------------------------------------------
# Authentication / authorization
# ----------------------------------------------------------------------

def current_staff():
    """The signed-in staff User (admin/registrar/teacher), or None."""
    user_id = session.get("staff_user_id")
    if not user_id:
        return None
    row = get_db().execute(
        "SELECT * FROM users WHERE user_id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    if row is None:
        session.pop("staff_user_id", None)
        return None
    from models import User
    return User.from_row(row)


@app.context_processor
def inject_staff_user():
    return {"staff_user": current_staff()}


def staff_required(*roles):
    """Gate for staff routes. With no arguments any signed-in staff member
    passes; with arguments the user's role must be one of them."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_staff()
            if user is None:
                flash("Please sign in to continue.", "error")
                return redirect(url_for("staff_login", next=request.path))
            if roles and user.role not in roles:
                if user.role == "teacher":
                    flash("That page is for registrar staff.", "error")
                    return redirect(url_for("teach_dashboard"))
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def portal_login_required(view):
    """Gate for /portal/* routes: redirects to the portal login screen if
    no student is signed in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("portal_student_id"):
            flash("Please sign in to continue.", "error")
            return redirect(url_for("portal_login"))
        return view(*args, **kwargs)
    return wrapped


def _actor():
    user = current_staff()
    if user:
        return f"staff:{user.username}"
    student_id = session.get("portal_student_id")
    if student_id:
        try:
            return f"student:{StudentService(get_db()).get_student(student_id).student_number}"
        except SISError:
            pass
    return "anonymous"


def audit(action, entity_type=None, entity_id=None, details=""):
    AuditService(get_db()).record(_actor(), action, entity_type, entity_id, details)


def paginate(total):
    """Reads ?page= from the query string and returns
    (page, pages, limit, offset) clamped to the valid range."""
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    return page, pages, PER_PAGE, (page - 1) * PER_PAGE


@app.template_global()
def url_for_page(p):
    """Current URL with just the page number swapped, keeping filters."""
    args = request.args.to_dict()
    args["page"] = p
    return url_for(request.endpoint, **(request.view_args or {}), **args)


# ----------------------------------------------------------------------
# Landing
# ----------------------------------------------------------------------

@app.route("/")
def landing():
    return render_template("landing.html")


# ----------------------------------------------------------------------
# Staff authentication
# ----------------------------------------------------------------------

def _safe_next(target):
    """Only follow same-site relative redirect targets."""
    return target if target and target.startswith("/") and not target.startswith("//") else None


@app.route("/setup", methods=["GET", "POST"])
def staff_setup():
    """First-run bootstrap: create the initial admin account. Only
    reachable while no staff accounts exist at all."""
    auth = AuthService(get_db())
    if auth.list_users():
        return redirect(url_for("staff_login"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if password != request.form.get("confirm_password", ""):
            flash("Passwords do not match.", "error")
        else:
            try:
                user = auth.create_user(request.form.get("username", ""), password, "admin")
                session.clear()
                session["staff_user_id"] = user.user_id
                audit("user.create", "user", user.user_id, "initial admin (first-run setup)")
                flash("Admin account created. You're signed in.", "success")
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
        username = request.form.get("username", "")
        user = auth.authenticate(username, request.form.get("password", ""))
        if user:
            session.pop("staff_user_id", None)
            session["staff_user_id"] = user.user_id
            audit("auth.login", "user", user.user_id)
            target = _safe_next(request.form.get("next"))
            if user.role == "teacher":
                return redirect(target or url_for("teach_dashboard"))
            return redirect(target or url_for("dashboard"))
        AuditService(get_db()).record(
            "anonymous", "auth.login_failed", "user", None, f"username={username.strip().lower()}"
        )
        flash("Invalid username or password.", "error")
    return render_template("staff_login.html", next=request.args.get("next", ""))


@app.route("/logout", methods=["POST"])
def staff_logout():
    user = current_staff()
    if user:
        audit("auth.logout", "user", user.user_id)
    session.pop("staff_user_id", None)
    return redirect(url_for("landing"))


# ----------------------------------------------------------------------
# User administration (admin only)
# ----------------------------------------------------------------------

@app.route("/users")
@staff_required("admin")
def users_list():
    conn = get_db()
    auth, teachers_svc = AuthService(conn), TeacherService(conn)
    rows = []
    for u in auth.list_users():
        teacher_name = teachers_svc.get_teacher(u.teacher_id).full_name if u.teacher_id else None
        rows.append({"user": u, "teacher_name": teacher_name})
    return render_template(
        "users_list.html", users=rows, teachers=teachers_svc.list_teachers(status="active")
    )


@app.route("/users/add", methods=["POST"])
@staff_required("admin")
def users_add():
    try:
        user = AuthService(get_db()).create_user(
            request.form.get("username", ""),
            request.form.get("password", ""),
            request.form.get("role", ""),
            teacher_id=int(request.form["teacher_id"]) if request.form.get("teacher_id") else None,
        )
        audit("user.create", "user", user.user_id, f"role={user.role}")
        flash(f"User '{user.username}' created.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:user_id>/password", methods=["POST"])
@staff_required("admin")
def users_reset_password(user_id):
    try:
        AuthService(get_db()).set_user_password(user_id, request.form.get("password", ""))
        audit("user.password_reset", "user", user_id)
        flash("Password updated.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:user_id>/status", methods=["POST"])
@staff_required("admin")
def users_set_status(user_id):
    auth = AuthService(get_db())
    me = current_staff()
    status = request.form.get("status", "")
    try:
        target = auth.get_user(user_id)
        if (target.user_id == me.user_id or
                (target.role == "admin" and auth.count_admins() <= 1)) and status == "disabled":
            flash("You can't disable the last active admin (or yourself).", "error")
        else:
            auth.set_user_status(user_id, status)
            audit("user.status", "user", user_id, status)
            flash("User status updated.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("users_list"))


# ----------------------------------------------------------------------
# Audit log (staff)
# ----------------------------------------------------------------------

@app.route("/audit")
@staff_required("admin", "registrar")
def audit_log():
    svc = AuditService(get_db())
    page, pages, limit, offset = paginate(svc.count())
    return render_template(
        "audit_log.html", entries=svc.list_entries(limit=limit, offset=offset),
        page=page, pages=pages,
    )


# ----------------------------------------------------------------------
# Registrar dashboard
# ----------------------------------------------------------------------

@app.route("/registrar")
@staff_required("admin", "registrar")
def dashboard():
    conn = get_db()
    students_svc, teachers_svc = StudentService(conn), TeacherService(conn)
    courses_svc, sections_svc, terms_svc = CourseService(conn), SectionService(conn), TermService(conn)

    current = terms_svc.get_current_term()
    total_fees = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM fees").fetchone()["t"]
    total_paid = conn.execute("SELECT COALESCE(SUM(amount_paid), 0) AS t FROM payments").fetchone()["t"]

    open_sections = term_enrollments = 0
    if current:
        open_sections = len([s for s in sections_svc.list_sections(term_id=current.term_id) if s.status == "open"])
        term_enrollments = conn.execute(
            "SELECT COUNT(*) c FROM enrollments e JOIN sections sec ON sec.section_id = e.section_id "
            "WHERE sec.term_id = ? AND e.status = 'enrolled'",
            (current.term_id,),
        ).fetchone()["c"]

    stats = {
        "active_students": len(students_svc.list_students(status="active")),
        "teachers": len(teachers_svc.list_teachers(status="active")),
        "courses": len(courses_svc.list_courses()),
        "open_sections": open_sections,
        "term_enrollments": term_enrollments,
        "outstanding_balance": total_fees - total_paid,
    }
    return render_template("dashboard.html", stats=stats)


# ----------------------------------------------------------------------
# Students
# ----------------------------------------------------------------------

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
    return render_template(
        "students_list.html", students=students, query=query, page=page, pages=pages
    )


@app.route("/students/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def students_add():
    conn = get_db()
    if request.method == "POST":
        try:
            s = StudentService(conn).add_student(
                first_name=request.form["first_name"],
                last_name=request.form["last_name"],
                email=request.form["email"],
                phone=request.form.get("phone", ""),
                date_of_birth=request.form.get("date_of_birth", ""),
                gender=request.form.get("gender", ""),
                program=request.form.get("program", ""),
                department_id=int(request.form["department_id"]) if request.form.get("department_id") else None,
                enrollment_date=request.form.get("enrollment_date") or None,
            )
            audit("student.create", "student", s.student_id, s.student_number)
            flash(f"Student {s.student_number} added.", "success")
            return redirect(url_for("students_detail", student_id=s.student_id))
        except SISError as e:
            flash(str(e), "error")
    return render_template("student_form.html", departments=_departments(conn), today=date.today().isoformat())


@app.route("/students/import", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def students_import():
    conn = get_db()
    if request.method == "POST":
        upload = request.files.get("csv_file")
        if not upload or not upload.filename:
            flash("Please choose a CSV file to upload.", "error")
            return redirect(url_for("students_import"))
        text_stream = io.StringIO(upload.stream.read().decode("utf-8-sig"))
        successes, errors = bulk_import.import_students_from_csv(conn, text_stream)
        if successes:
            audit("student.bulk_import", "student", None, f"{len(successes)} imported")
            flash(f"Imported {len(successes)} student(s).", "success")
        if errors:
            flash(f"{len(errors)} row(s) failed: " + " | ".join(errors[:5]), "error")
        return redirect(url_for("students_list"))
    return render_template("student_import.html")


@app.route("/students/import/template.csv")
@staff_required("admin", "registrar")
def students_import_template():
    buf = io.BytesIO(bulk_import.csv_template().encode("utf-8"))
    return send_file(
        buf, mimetype="text/csv", as_attachment=True, download_name="student_import_template.csv"
    )


@app.route("/students/<int:student_id>")
@staff_required("admin", "registrar")
def students_detail(student_id):
    conn = get_db()
    students, enrollments, gpa_service = StudentService(conn), EnrollmentService(conn), GPAService(conn)
    fees, terms_svc, sections_svc, courses_svc = FeeService(conn), TermService(conn), SectionService(conn), CourseService(conn)

    student = students.get_student(student_id)
    all_rows = enrollments.list_student_enrollments(student_id)

    by_term = {}
    for row in all_rows:
        by_term.setdefault(row["term_id"], []).append(row)

    transcript_terms = []
    for term_id, rows in sorted(by_term.items(), key=lambda kv: kv[0]):
        term = terms_svc.get_term(term_id)
        transcript_terms.append((term.name, rows, gpa_service.calculate_term_gpa(student_id, term_id)))

    enrolled_section_ids = {row["section_id"] for row in all_rows if row["status"] != "dropped"}
    open_sections = []
    for sec in sections_svc.list_sections():
        if sec.status != "open" or sec.section_id in enrolled_section_ids:
            continue
        course = courses_svc.get_course(sec.course_id)
        term = terms_svc.get_term(sec.term_id)
        open_sections.append({
            "section_id": sec.section_id, "course_code": course.course_code,
            "section_number": sec.section_number, "term_name": term.name,
            "enrolled": sections_svc.get_enrolled_count(sec.section_id), "capacity": sec.capacity,
        })

    return render_template(
        "student_detail.html",
        student=student,
        transcript_terms=transcript_terms,
        cum_gpa=gpa_service.calculate_cumulative_gpa(student_id),
        standing=gpa_service.get_academic_standing(gpa_service.calculate_cumulative_gpa(student_id)),
        earned_hours=gpa_service.get_earned_credit_hours(student_id),
        fee_statement=fees.get_fee_statement(student_id),
        balance=fees.get_student_balance(student_id),
        open_sections=open_sections,
        terms=terms_svc.list_terms(),
    )


@app.route("/students/<int:student_id>/status", methods=["POST"])
@staff_required("admin", "registrar")
def students_set_status(student_id):
    conn = get_db()
    try:
        StudentService(conn).set_status(student_id, request.form["status"])
        audit("student.status", "student", student_id, request.form["status"])
        flash("Status updated.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/<int:student_id>/enroll", methods=["POST"])
@staff_required("admin", "registrar")
def students_enroll(student_id):
    conn = get_db()
    try:
        section_id = int(request.form["section_id"])
        status, result = EnrollmentService(conn).enroll_or_waitlist(student_id, section_id)
        audit(f"enrollment.{status}", "section", section_id, f"student_id={student_id}")
        if status == "enrolled":
            flash("Enrolled successfully.", "success")
        else:
            pos = WaitlistService(conn).get_position(student_id, result.section_id)
            flash(f"Section is full — added to the waitlist (position {pos}).", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/<int:student_id>/fees/assess", methods=["POST"])
@staff_required("admin", "registrar")
def students_assess_fee(student_id):
    conn = get_db()
    try:
        fee = FeeService(conn).assess_fee(
            student_id,
            request.form["fee_type"],
            float(request.form["amount"]),
            term_id=int(request.form["term_id"]) if request.form.get("term_id") else None,
            due_date=request.form.get("due_date") or None,
        )
        audit("fee.assess", "fee", fee.fee_id,
              f"student_id={student_id} {fee.fee_type} {fee.amount:.2f}")
        flash("Fee assessed.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/fees/<int:fee_id>/pay", methods=["POST"])
@staff_required("admin", "registrar")
def fees_pay(fee_id):
    conn = get_db()
    fee = FeeService(conn).get_fee(fee_id)
    try:
        FeeService(conn).record_payment(fee_id, float(request.form["amount_paid"]))
        audit("fee.payment", "fee", fee_id, f"amount={float(request.form['amount_paid']):.2f}")
        flash("Payment recorded.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=fee.student_id))


@app.route("/fees/<int:fee_id>/waive", methods=["POST"])
@staff_required("admin", "registrar")
def fees_waive(fee_id):
    conn = get_db()
    fee = FeeService(conn).get_fee(fee_id)
    try:
        FeeService(conn).waive_fee(fee_id, reason=request.form.get("reason", ""))
        audit("fee.waive", "fee", fee_id, request.form.get("reason", ""))
        flash("Fee waived.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("students_detail", student_id=fee.student_id))


@app.route("/students/<int:student_id>/portal-access/reset", methods=["POST"])
@staff_required("admin", "registrar")
def students_reset_portal_access(student_id):
    conn = get_db()
    student = StudentService(conn).get_student(student_id)
    AuthService(conn).set_student_password(student_id, None)
    audit("student.portal_reset", "student", student_id, student.student_number)
    flash("Portal access reset — the student can re-activate with their "
          "student number and email.", "success")
    return redirect(url_for("students_detail", student_id=student_id))


@app.route("/students/<int:student_id>/transcript.pdf")
@staff_required("admin", "registrar")
def students_transcript_pdf(student_id):
    conn = get_db()
    try:
        buf = pdf_reports.generate_transcript_pdf(conn, student_id)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("students_detail", student_id=student_id))
    student = StudentService(conn).get_student(student_id)
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"transcript_{student.student_number}.pdf",
    )


# ----------------------------------------------------------------------
# Teachers
# ----------------------------------------------------------------------

@app.route("/teachers")
@staff_required("admin", "registrar")
def teachers_list():
    svc = TeacherService(get_db())
    page, pages, limit, offset = paginate(svc.count_teachers())
    return render_template(
        "teachers_list.html", teachers=svc.list_teachers(limit=limit, offset=offset),
        page=page, pages=pages,
    )


@app.route("/teachers/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def teachers_add():
    conn = get_db()
    if request.method == "POST":
        try:
            teacher = TeacherService(conn).add_teacher(
                first_name=request.form["first_name"],
                last_name=request.form["last_name"],
                email=request.form["email"],
                phone=request.form.get("phone", ""),
                department_id=int(request.form["department_id"]) if request.form.get("department_id") else None,
                title=request.form.get("title", ""),
                hire_date=request.form.get("hire_date") or None,
            )
            audit("teacher.create", "teacher", teacher.teacher_id, teacher.employee_number)
            flash("Teacher added.", "success")
            return redirect(url_for("teachers_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("teacher_form.html", departments=_departments(conn), today=date.today().isoformat())


# ----------------------------------------------------------------------
# Courses
# ----------------------------------------------------------------------

@app.route("/courses")
@staff_required("admin", "registrar")
def courses_list():
    svc = CourseService(get_db())
    page, pages, limit, offset = paginate(svc.count_courses())
    return render_template(
        "courses_list.html", courses=svc.list_courses(limit=limit, offset=offset),
        page=page, pages=pages,
    )


@app.route("/courses/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def courses_add():
    conn = get_db()
    if request.method == "POST":
        try:
            course = CourseService(conn).add_course(
                course_code=request.form["course_code"],
                title=request.form["title"],
                credit_hours=int(request.form["credit_hours"]),
                department_id=int(request.form["department_id"]) if request.form.get("department_id") else None,
                description=request.form.get("description", ""),
            )
            audit("course.create", "course", course.course_id, course.course_code)
            flash(f"Course {course.course_code} added.", "success")
            return redirect(url_for("courses_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("course_form.html", departments=_departments(conn))


@app.route("/courses/<int:course_id>")
@staff_required("admin", "registrar")
def courses_detail(course_id):
    courses = CourseService(get_db())
    course = courses.get_course(course_id)
    return render_template(
        "course_detail.html", course=course,
        prerequisite_groups=courses.get_prerequisite_groups(course_id),
        all_courses=courses.list_courses(),
    )


@app.route("/courses/<int:course_id>/prerequisites", methods=["POST"])
@staff_required("admin", "registrar")
def courses_add_prereq(course_id):
    conn = get_db()
    try:
        CourseService(conn).add_prerequisite(course_id, int(request.form["prerequisite_course_id"]))
        audit("course.prerequisite_add", "course", course_id,
              f"prereq_course_id={request.form['prerequisite_course_id']}")
        flash("Prerequisite added.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("courses_detail", course_id=course_id))


@app.route("/courses/<int:course_id>/prerequisite-groups", methods=["POST"])
@staff_required("admin", "registrar")
def courses_add_prereq_group(course_id):
    conn = get_db()
    try:
        ids = [int(x) for x in request.form.getlist("alt_course_ids")]
        CourseService(conn).add_prerequisite_group(course_id, ids)
        audit("course.prerequisite_group_add", "course", course_id, f"alternatives={ids}")
        flash("Alternative group added.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("courses_detail", course_id=course_id))


# ----------------------------------------------------------------------
# Terms
# ----------------------------------------------------------------------

@app.route("/terms")
@staff_required("admin", "registrar")
def terms_list():
    return render_template("terms_list.html", terms=TermService(get_db()).list_terms())


@app.route("/terms/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def terms_add():
    conn = get_db()
    if request.method == "POST":
        try:
            term = TermService(conn).add_term(
                request.form["name"], request.form["start_date"], request.form["end_date"],
                add_deadline=request.form.get("add_deadline") or None,
                drop_deadline=request.form.get("drop_deadline") or None,
            )
            audit("term.create", "term", term.term_id, term.name)
            flash("Term added.", "success")
            return redirect(url_for("terms_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template("term_form.html")


@app.route("/terms/<int:term_id>/set-current", methods=["POST"])
@staff_required("admin", "registrar")
def terms_set_current(term_id):
    conn = get_db()
    try:
        TermService(conn).set_current_term(term_id)
        audit("term.set_current", "term", term_id)
        flash("Current term updated.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("terms_list"))


@app.route("/terms/<int:term_id>/deadlines", methods=["POST"])
@staff_required("admin", "registrar")
def terms_set_deadlines(term_id):
    conn = get_db()
    try:
        TermService(conn).update_term(
            term_id,
            add_deadline=request.form.get("add_deadline", ""),
            drop_deadline=request.form.get("drop_deadline", ""),
        )
        audit("term.deadlines", "term", term_id,
              f"add={request.form.get('add_deadline', '')} drop={request.form.get('drop_deadline', '')}")
        flash("Deadlines updated.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("terms_list"))


# ----------------------------------------------------------------------
# Sections
# ----------------------------------------------------------------------

@app.route("/sections")
@staff_required("admin", "registrar")
def sections_list():
    conn = get_db()
    sections_svc, courses_svc, teachers_svc, terms_svc = (
        SectionService(conn), CourseService(conn), TeacherService(conn), TermService(conn)
    )
    term_id = request.args.get("term_id", type=int)
    page, pages, limit, offset = paginate(sections_svc.count_sections(term_id=term_id))
    rows = []
    for sec in sections_svc.list_sections(term_id=term_id, limit=limit, offset=offset):
        rows.append({
            "section": sec,
            "course_code": courses_svc.get_course(sec.course_id).course_code,
            "teacher_name": teachers_svc.get_teacher(sec.teacher_id).full_name if sec.teacher_id else None,
            "enrolled": sections_svc.get_enrolled_count(sec.section_id),
        })
    return render_template(
        "sections_list.html", sections=rows, terms=terms_svc.list_terms(),
        selected_term_id=term_id, page=page, pages=pages,
    )


@app.route("/sections/add", methods=["GET", "POST"])
@staff_required("admin", "registrar")
def sections_add():
    conn = get_db()
    if request.method == "POST":
        try:
            section = SectionService(conn).add_section(
                course_id=int(request.form["course_id"]),
                term_id=int(request.form["term_id"]),
                section_number=request.form["section_number"],
                teacher_id=int(request.form["teacher_id"]) if request.form.get("teacher_id") else None,
                room=request.form.get("room", ""),
                days=",".join(request.form.getlist("days")),
                start_time=request.form.get("start_time", ""),
                end_time=request.form.get("end_time", ""),
                capacity=int(request.form["capacity"]),
            )
            audit("section.create", "section", section.section_id,
                  f"course_id={section.course_id} term_id={section.term_id} #{section.section_number}")
            flash("Section created.", "success")
            return redirect(url_for("sections_list"))
        except SISError as e:
            flash(str(e), "error")
    return render_template(
        "section_form.html",
        courses=CourseService(conn).list_courses(),
        terms=TermService(conn).list_terms(),
        teachers=TeacherService(conn).list_teachers(),
    )


@app.route("/sections/<int:section_id>")
@staff_required("admin", "registrar")
def sections_detail(section_id):
    conn = get_db()
    sections_svc, courses_svc, teachers_svc, students_svc = (
        SectionService(conn), CourseService(conn), TeacherService(conn), StudentService(conn)
    )
    section = sections_svc.get_section(section_id)
    course = courses_svc.get_course(section.course_id)
    teacher_name = teachers_svc.get_teacher(section.teacher_id).full_name if section.teacher_id else None
    roster = sections_svc.get_roster(section_id)
    enrolled_ids = {r["student_id"] for r in roster}
    eligible_students = [s for s in students_svc.list_students(status="active") if s.student_id not in enrolled_ids]
    waitlist_entries = WaitlistService(conn).list_for_section(section_id)
    return render_template(
        "section_detail.html", section=section, course=course, teacher_name=teacher_name,
        roster=roster, eligible_students=eligible_students, waitlist_entries=waitlist_entries,
    )


@app.route("/sections/<int:section_id>/enroll", methods=["POST"])
@staff_required("admin", "registrar")
def sections_enroll_student(section_id):
    conn = get_db()
    student_id = int(request.form["student_id"])
    try:
        status, result = EnrollmentService(conn).enroll_or_waitlist(student_id, section_id)
        audit(f"enrollment.{status}", "section", section_id, f"student_id={student_id}")
        if status == "enrolled":
            flash("Student enrolled.", "success")
        else:
            pos = WaitlistService(conn).get_position(student_id, section_id)
            flash(f"Section is full — student added to the waitlist (position {pos}).", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("sections_detail", section_id=section_id))


@app.route("/sections/<int:section_id>/waitlist/leave/<int:student_id>", methods=["POST"])
@staff_required("admin", "registrar")
def sections_waitlist_leave(section_id, student_id):
    conn = get_db()
    WaitlistService(conn).leave(student_id, section_id)
    audit("waitlist.leave", "section", section_id, f"student_id={student_id}")
    flash("Removed from waitlist.", "success")
    return redirect(url_for("sections_detail", section_id=section_id))


@app.route("/sections/<int:section_id>/drop/<int:student_id>", methods=["POST"])
@staff_required("admin", "registrar")
def sections_drop_student(section_id, student_id):
    conn = get_db()
    try:
        EnrollmentService(conn).drop_student(student_id, section_id)
        audit("enrollment.drop", "section", section_id, f"student_id={student_id}")
        flash("Student dropped.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("sections_detail", section_id=section_id))


def _apply_grades_from_form(section_id):
    """Shared by the registrar and teacher grade forms: reads grade_<id>
    fields, assigns each grade, audits each change."""
    grading = GradingService(get_db())
    updated, errors = 0, []
    for key, value in request.form.items():
        if key.startswith("grade_") and value.strip():
            student_id = int(key.replace("grade_", ""))
            try:
                grading.assign_grade_by_pair(student_id, section_id, value.strip())
                audit("grade.assign", "section", section_id,
                      f"student_id={student_id} grade={value.strip().upper()}")
                updated += 1
            except SISError as e:
                errors.append(str(e))
    if updated:
        flash(f"Saved {updated} grade(s).", "success")
    if errors:
        flash("; ".join(errors), "error")


@app.route("/sections/<int:section_id>/grades", methods=["POST"])
@staff_required("admin", "registrar")
def sections_submit_grades(section_id):
    _apply_grades_from_form(section_id)
    return redirect(url_for("sections_detail", section_id=section_id))


# ----------------------------------------------------------------------
# Teacher portal -- a signed-in teacher sees only their own sections and
# enters grades for them; everything else stays registrar-only.
# ----------------------------------------------------------------------

def _own_section_or_403(section_id):
    user = current_staff()
    section = SectionService(get_db()).get_section(section_id)
    if section.teacher_id != user.teacher_id:
        abort(403)
    return section


@app.route("/teach")
@staff_required("teacher")
def teach_dashboard():
    conn = get_db()
    user = current_staff()
    sections_svc, courses_svc, terms_svc = SectionService(conn), CourseService(conn), TermService(conn)
    rows = []
    for sec in sections_svc.list_sections(teacher_id=user.teacher_id):
        course = courses_svc.get_course(sec.course_id)
        rows.append({
            "section": sec,
            "course_code": course.course_code,
            "course_title": course.title,
            "term_name": terms_svc.get_term(sec.term_id).name,
            "enrolled": sections_svc.get_enrolled_count(sec.section_id),
        })
    teacher = TeacherService(conn).get_teacher(user.teacher_id)
    return render_template("teach_dashboard.html", sections=rows, teacher=teacher)


@app.route("/teach/sections/<int:section_id>")
@staff_required("teacher")
def teach_section(section_id):
    conn = get_db()
    section = _own_section_or_403(section_id)
    course = CourseService(conn).get_course(section.course_id)
    term = TermService(conn).get_term(section.term_id)
    roster = SectionService(conn).get_roster(section_id)
    return render_template(
        "teach_section.html", section=section, course=course, term=term, roster=roster,
    )


@app.route("/teach/sections/<int:section_id>/grades", methods=["POST"])
@staff_required("teacher")
def teach_submit_grades(section_id):
    _own_section_or_403(section_id)
    _apply_grades_from_form(section_id)
    return redirect(url_for("teach_section", section_id=section_id))


# ----------------------------------------------------------------------
# Student portal -- self-service view scoped to a single signed-in student.
# Every action here reuses the exact same service methods (and therefore
# the exact same business rules) as the registrar side.
# ----------------------------------------------------------------------

@app.route("/portal/login", methods=["GET", "POST"])
def portal_login():
    if request.method == "POST":
        auth = AuthService(get_db())
        student_number = request.form.get("student_number", "").strip()
        mode = request.form.get("mode", "login")

        if mode == "activate":
            # First-time access: prove identity with the email on file,
            # then choose a password. Only possible while none is set.
            password = request.form.get("password", "")
            if password != request.form.get("confirm_password", ""):
                flash("Passwords do not match.", "error")
                return render_template("portal_login.html", mode="activate")
            try:
                student = auth.activate_student(
                    student_number, request.form.get("email", ""), password
                )
            except SISError as e:
                flash(str(e), "error")
                return render_template("portal_login.html", mode="activate")
            if student is None:
                flash("Activation failed. Check your student number and email — "
                      "if your account is already activated, sign in with your "
                      "password or ask the registrar to reset it.", "error")
                return render_template("portal_login.html", mode="activate")
            session.pop("portal_student_id", None)
            session["portal_student_id"] = student.student_id
            audit("portal.activate", "student", student.student_id)
            flash("Your portal account is set up. Welcome!", "success")
            return redirect(url_for("portal_dashboard"))

        student = auth.authenticate_student(student_number, request.form.get("password", ""))
        if student:
            session.pop("portal_student_id", None)
            session["portal_student_id"] = student.student_id
            audit("portal.login", "student", student.student_id)
            return redirect(url_for("portal_dashboard"))
        if auth.student_has_password(student_number) is False:
            flash("This account hasn't been activated yet — use "
                  "\"First time here?\" below to set your password.", "error")
        else:
            flash("Invalid student number or password.", "error")
    return render_template("portal_login.html", mode=request.args.get("mode", "login"))


@app.route("/portal/logout", methods=["POST"])
def portal_logout():
    session.pop("portal_student_id", None)
    return redirect(url_for("landing"))


@app.route("/portal")
@portal_login_required
def portal_dashboard():
    conn = get_db()
    student_id = session["portal_student_id"]
    gpa_service, fees = GPAService(conn), FeeService(conn)
    cum_gpa = gpa_service.calculate_cumulative_gpa(student_id)
    return render_template(
        "portal_dashboard.html",
        student=StudentService(conn).get_student(student_id),
        cum_gpa=cum_gpa,
        standing=gpa_service.get_academic_standing(cum_gpa),
        earned_hours=gpa_service.get_earned_credit_hours(student_id),
        balance=fees.get_student_balance(student_id),
    )


@app.route("/portal/register", methods=["GET", "POST"])
@portal_login_required
def portal_register():
    conn = get_db()
    student_id = session["portal_student_id"]
    enrollment_svc = EnrollmentService(conn)
    waitlist_svc = WaitlistService(conn)

    if request.method == "POST":
        try:
            section_id = int(request.form["section_id"])
            status, result = enrollment_svc.enroll_or_waitlist(student_id, section_id)
            audit(f"enrollment.{status}", "section", section_id, f"student_id={student_id} (self-service)")
            if status == "enrolled":
                flash("You're registered.", "success")
            else:
                pos = waitlist_svc.get_position(student_id, result.section_id)
                flash(f"That section is full — you've been added to the waitlist (position {pos}).", "success")
        except SISError as e:
            flash(str(e), "error")
        return redirect(url_for("portal_register"))

    sections_svc, courses_svc = SectionService(conn), CourseService(conn)
    teachers_svc, terms_svc = TeacherService(conn), TermService(conn)
    enrolled_ids = {
        r["section_id"] for r in enrollment_svc.list_student_enrollments(student_id) if r["status"] != "dropped"
    }
    waitlisted_ids = {w["section_id"] for w in waitlist_svc.list_for_student(student_id)}
    rows = []
    for sec in sections_svc.list_sections():
        if sec.status != "open":
            continue
        rows.append({
            "section": sec,
            "course": courses_svc.get_course(sec.course_id),
            "term_name": terms_svc.get_term(sec.term_id).name,
            "teacher_name": teachers_svc.get_teacher(sec.teacher_id).full_name if sec.teacher_id else "TBD",
            "enrolled": sections_svc.get_enrolled_count(sec.section_id),
            "already_in": sec.section_id in enrolled_ids,
            "waitlisted": sec.section_id in waitlisted_ids,
        })
    return render_template("portal_register.html", sections=rows)


@app.route("/portal/waitlist/leave/<int:section_id>", methods=["POST"])
@portal_login_required
def portal_waitlist_leave(section_id):
    conn = get_db()
    WaitlistService(conn).leave(session["portal_student_id"], section_id)
    audit("waitlist.leave", "section", section_id,
          f"student_id={session['portal_student_id']} (self-service)")
    flash("Removed from waitlist.", "success")
    return redirect(url_for("portal_register"))


@app.route("/portal/my-courses")
@portal_login_required
def portal_my_courses():
    conn = get_db()
    student_id = session["portal_student_id"]
    terms_svc = TermService(conn)
    rows = EnrollmentService(conn).list_student_enrollments(student_id)
    enrollments = [{**dict(r), "term_name": terms_svc.get_term(r["term_id"]).name} for r in rows]
    waitlist_rows = WaitlistService(conn).list_for_student(student_id)
    return render_template("portal_my_courses.html", enrollments=enrollments, waitlist_rows=waitlist_rows)


@app.route("/portal/drop/<int:section_id>", methods=["POST"])
@portal_login_required
def portal_drop(section_id):
    conn = get_db()
    try:
        EnrollmentService(conn).drop_student(session["portal_student_id"], section_id)
        audit("enrollment.drop", "section", section_id,
              f"student_id={session['portal_student_id']} (self-service)")
        flash("Dropped.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("portal_my_courses"))


@app.route("/portal/transcript")
@portal_login_required
def portal_transcript():
    conn = get_db()
    student_id = session["portal_student_id"]
    enrollment_svc, gpa_service, terms_svc = EnrollmentService(conn), GPAService(conn), TermService(conn)

    by_term = {}
    for row in enrollment_svc.list_student_enrollments(student_id):
        by_term.setdefault(row["term_id"], []).append(row)

    transcript_terms = []
    for term_id, rows in sorted(by_term.items(), key=lambda kv: kv[0]):
        transcript_terms.append((
            terms_svc.get_term(term_id).name, rows, gpa_service.calculate_term_gpa(student_id, term_id)
        ))

    cum_gpa = gpa_service.calculate_cumulative_gpa(student_id)
    return render_template(
        "portal_transcript.html",
        transcript_terms=transcript_terms,
        cum_gpa=cum_gpa,
        standing=gpa_service.get_academic_standing(cum_gpa),
        earned_hours=gpa_service.get_earned_credit_hours(student_id),
    )


@app.route("/portal/fees")
@portal_login_required
def portal_fees():
    conn = get_db()
    fees = FeeService(conn)
    student_id = session["portal_student_id"]
    return render_template(
        "portal_fees.html",
        fee_statement=fees.get_fee_statement(student_id),
        balance=fees.get_student_balance(student_id),
    )


@app.route("/portal/fees/<int:fee_id>/pay", methods=["POST"])
@portal_login_required
def portal_pay_fee(fee_id):
    conn = get_db()
    fees = FeeService(conn)
    fee = fees.get_fee(fee_id)
    if fee.student_id != session["portal_student_id"]:
        flash("That fee doesn't belong to your account.", "error")
        return redirect(url_for("portal_fees"))
    try:
        fees.record_payment(fee_id, float(request.form["amount_paid"]), payment_method="Self-service")
        audit("fee.payment", "fee", fee_id,
              f"amount={float(request.form['amount_paid']):.2f} (self-service)")
        flash("Payment recorded.", "success")
    except SISError as e:
        flash(str(e), "error")
    return redirect(url_for("portal_fees"))


@app.route("/portal/transcript.pdf")
@portal_login_required
def portal_transcript_pdf():
    conn = get_db()
    student_id = session["portal_student_id"]
    try:
        buf = pdf_reports.generate_transcript_pdf(conn, student_id)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("portal_transcript"))
    student = StudentService(conn).get_student(student_id)
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"transcript_{student.student_number}.pdf",
    )


if __name__ == "__main__":
    # Development server only. debug is OFF unless explicitly requested via
    # SIS_DEBUG=1 -- the Werkzeug debugger allows remote code execution and
    # must never face a network. For real deployments use a WSGI server:
    #     gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app
    app.run(debug=os.environ.get("SIS_DEBUG") == "1")
