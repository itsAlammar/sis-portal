"""Menu-driven command-line interface for the Student Information System."""

from datetime import date

from exceptions import SISError
from student_service import StudentService
from teacher_service import TeacherService
from course_service import CourseService
from term_service import TermService
from section_service import SectionService
from enrollment_service import EnrollmentService
from grading_service import GradingService
from fee_service import FeeService
from waitlist_service import WaitlistService
import bulk_import
import pdf_reports
import reports


# ----------------------------------------------------------------------
# Input helpers
# ----------------------------------------------------------------------

def prompt(label, default=None, required=True):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            return default
        if not value and not required:
            return ""
        if value:
            return value
        print("This field is required.")


def prompt_int(label, default=None):
    while True:
        raw = prompt(label, default=str(default) if default is not None else None)
        try:
            return int(raw)
        except ValueError:
            print("Please enter a whole number.")


def prompt_float(label, default=None):
    while True:
        raw = prompt(label, default=str(default) if default is not None else None)
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number.")


def prompt_date(label, default=None):
    default = default if default is not None else date.today().isoformat()
    while True:
        raw = prompt(f"{label} (YYYY-MM-DD)", default=default)
        try:
            date.fromisoformat(raw)
            return raw
        except ValueError:
            print("Please enter a date as YYYY-MM-DD.")


def pause():
    input("\nPress Enter to continue...")


def print_header(title):
    print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")


# ----------------------------------------------------------------------
# Student menu
# ----------------------------------------------------------------------

def student_menu(conn):
    svc = StudentService(conn)
    while True:
        print_header("STUDENT MANAGEMENT")
        print("1. Add student\n2. View student\n3. List all students\n"
              "4. Search students\n5. Update student\n6. Change status\n"
              "7. Bulk import from CSV\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                s = svc.add_student(
                    first_name=prompt("First name"),
                    last_name=prompt("Last name"),
                    email=prompt("Email"),
                    phone=prompt("Phone", required=False),
                    date_of_birth=prompt_date("Date of birth", default="2000-01-01"),
                    gender=prompt("Gender", required=False),
                    program=prompt("Program/Major", required=False),
                    enrollment_date=prompt_date("Enrollment date"),
                )
                print(f"\nCreated student {s.student_number}: {s.full_name}")
            elif choice == "2":
                _print_student(svc.get_student(prompt_int("Student ID")))
            elif choice == "3":
                for s in svc.list_students():
                    _print_student_row(s)
            elif choice == "4":
                for s in svc.search_students(prompt("Search term")):
                    _print_student_row(s)
            elif choice == "5":
                sid = prompt_int("Student ID")
                svc.update_student(
                    sid,
                    phone=prompt("New phone (blank to skip)", required=False) or None,
                    program=prompt("New program (blank to skip)", required=False) or None,
                )
                print("Updated.")
            elif choice == "6":
                sid = prompt_int("Student ID")
                svc.set_status(sid, prompt("New status (active/suspended/graduated/withdrawn)"))
                print("Status updated.")
            elif choice == "7":
                path = prompt("Path to CSV file")
                try:
                    with open(path, newline="", encoding="utf-8") as f:
                        successes, errors = bulk_import.import_students_from_csv(conn, f)
                except FileNotFoundError:
                    print(f"\nFile not found: {path}")
                    successes, errors = [], []
                for line in successes:
                    print(line)
                for line in errors:
                    print(f"ERROR - {line}")
                print(f"\n{len(successes)} imported, {len(errors)} failed.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


def _print_student(s):
    print(f"\nID: {s.student_id}  Number: {s.student_number}")
    print(f"Name: {s.full_name}")
    print(f"Email: {s.email}  Phone: {s.phone or '-'}")
    print(f"Program: {s.program or '-'}  Status: {s.status}")
    print(f"Enrolled: {s.enrollment_date}")


def _print_student_row(s):
    print(f"{s.student_id:<5}{s.student_number:<12}{s.full_name:<26}{s.status:<12}{s.email}")


# ----------------------------------------------------------------------
# Teacher menu
# ----------------------------------------------------------------------

def teacher_menu(conn):
    svc = TeacherService(conn)
    while True:
        print_header("TEACHER MANAGEMENT")
        print("1. Add teacher\n2. View teacher\n3. List all teachers\n"
              "4. Search teachers\n5. Update teacher\n6. Change status\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                t = svc.add_teacher(
                    first_name=prompt("First name"),
                    last_name=prompt("Last name"),
                    email=prompt("Email"),
                    phone=prompt("Phone", required=False),
                    title=prompt("Title (e.g. Professor, Lecturer)", required=False),
                    hire_date=prompt_date("Hire date"),
                )
                print(f"\nCreated teacher {t.employee_number}: {t.full_name}")
            elif choice == "2":
                t = svc.get_teacher(prompt_int("Teacher ID"))
                print(f"\n{t.employee_number} - {t.full_name} ({t.title or '-'})")
                print(f"Email: {t.email}  Status: {t.status}")
            elif choice == "3":
                for t in svc.list_teachers():
                    print(f"{t.teacher_id:<5}{t.employee_number:<12}{t.full_name:<26}{t.status:<10}{t.email}")
            elif choice == "4":
                for t in svc.search_teachers(prompt("Search term")):
                    print(f"{t.teacher_id:<5}{t.employee_number:<12}{t.full_name:<26}{t.status:<10}{t.email}")
            elif choice == "5":
                tid = prompt_int("Teacher ID")
                svc.update_teacher(
                    tid,
                    phone=prompt("New phone (blank to skip)", required=False) or None,
                    title=prompt("New title (blank to skip)", required=False) or None,
                )
                print("Updated.")
            elif choice == "6":
                tid = prompt_int("Teacher ID")
                svc.set_status(tid, prompt("New status (active/inactive)"))
                print("Status updated.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Course menu
# ----------------------------------------------------------------------

def course_menu(conn):
    svc = CourseService(conn)
    while True:
        print_header("COURSE MANAGEMENT")
        print("1. Add course\n2. View course\n3. List all courses\n"
              "4. Add prerequisite\n5. Add alternative group (OR)\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                c = svc.add_course(
                    course_code=prompt("Course code (e.g. CS101)"),
                    title=prompt("Title"),
                    credit_hours=prompt_int("Credit hours", default=3),
                    description=prompt("Description", required=False),
                )
                print(f"\nCreated course {c.course_code}: {c.title}")
            elif choice == "2":
                c = svc.get_course(prompt_int("Course ID"))
                print(f"\n{c.course_code} - {c.title} ({c.credit_hours} credit hours)")
                print(f"Description: {c.description or '-'}")
                groups = svc.get_prerequisite_groups(c.course_id)
                if groups:
                    for group in groups:
                        print("  Requires: " + " OR ".join(g.course_code for g in group))
                else:
                    print("Prerequisites: None")
            elif choice == "3":
                for c in svc.list_courses():
                    print(f"{c.course_id:<5}{c.course_code:<10}{c.title:<30}{c.credit_hours}cr")
            elif choice == "4":
                svc.add_prerequisite(prompt_int("Course ID"), prompt_int("Prerequisite course ID"))
                print("Prerequisite added.")
            elif choice == "5":
                cid = prompt_int("Course ID")
                raw = prompt("Alternative course IDs, comma-separated (any ONE satisfies)")
                ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
                svc.add_prerequisite_group(cid, ids)
                print("Alternative group added.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Term menu
# ----------------------------------------------------------------------

def term_menu(conn):
    svc = TermService(conn)
    while True:
        print_header("TERM MANAGEMENT")
        print("1. Add term\n2. List terms\n3. Set current term\n4. Set add/drop deadlines\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                t = svc.add_term(
                    name=prompt("Term name (e.g. Fall 2026)"),
                    start_date=prompt_date("Start date"),
                    end_date=prompt_date("End date"),
                    add_deadline=prompt("Add deadline (YYYY-MM-DD, blank for none)", required=False) or None,
                    drop_deadline=prompt("Drop deadline (YYYY-MM-DD, blank for none)", required=False) or None,
                )
                print(f"\nCreated term: {t.name}")
            elif choice == "2":
                for t in svc.list_terms():
                    marker = " (current)" if t.is_current else ""
                    deadlines = f"  add-by {t.add_deadline or '-'} / drop-by {t.drop_deadline or '-'}"
                    print(f"{t.term_id:<5}{t.name:<16}{t.start_date} to {t.end_date}{marker}{deadlines}")
            elif choice == "3":
                svc.set_current_term(prompt_int("Term ID"))
                print("Current term updated.")
            elif choice == "4":
                tid = prompt_int("Term ID")
                kwargs = {}
                add_dl = prompt("New add deadline (YYYY-MM-DD, blank to skip)", required=False)
                if add_dl:
                    kwargs["add_deadline"] = add_dl
                drop_dl = prompt("New drop deadline (YYYY-MM-DD, blank to skip)", required=False)
                if drop_dl:
                    kwargs["drop_deadline"] = drop_dl
                svc.update_term(tid, **kwargs)
                print("Deadlines updated.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Section menu
# ----------------------------------------------------------------------

def section_menu(conn):
    svc = SectionService(conn)
    courses = CourseService(conn)
    while True:
        print_header("SECTION MANAGEMENT")
        print("1. Add section\n2. List sections\n3. View roster\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                sec = svc.add_section(
                    course_id=prompt_int("Course ID"),
                    term_id=prompt_int("Term ID"),
                    section_number=prompt("Section number (e.g. 01)"),
                    teacher_id=prompt_int("Teacher ID (0 for TBD)", default=0) or None,
                    room=prompt("Room", required=False),
                    days=prompt("Days (comma-separated, e.g. SUN,TUE)", required=False),
                    start_time=prompt("Start time (HH:MM)", required=False),
                    end_time=prompt("End time (HH:MM)", required=False),
                    capacity=prompt_int("Capacity", default=30),
                )
                print(f"\nCreated section {sec.section_number}.")
            elif choice == "2":
                term_id = prompt_int("Filter by term ID (0 for all)", default=0) or None
                for sec in svc.list_sections(term_id=term_id):
                    course = courses.get_course(sec.course_id)
                    count = svc.get_enrolled_count(sec.section_id)
                    print(f"{sec.section_id:<5}{course.course_code:<8}sec {sec.section_number:<5}"
                          f"{count}/{sec.capacity:<5}{sec.days or '-':<12}{sec.status}")
            elif choice == "3":
                print(reports.generate_section_roster_report(conn, prompt_int("Section ID")))
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Enrollment menu
# ----------------------------------------------------------------------

def enrollment_menu(conn):
    svc = EnrollmentService(conn)
    waitlist = WaitlistService(conn)
    while True:
        print_header("ENROLLMENT")
        print("1. Enroll student\n2. Drop student\n3. List student's enrollments\n"
              "4. View section waitlist\n5. Leave a waitlist\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                sid, secid = prompt_int("Student ID"), prompt_int("Section ID")
                try:
                    e = svc.enroll_student(sid, secid)
                    print(f"\nEnrolled. Enrollment ID: {e.enrollment_id}")
                except SISError as capacity_err:
                    if "capacity" in str(capacity_err).lower():
                        if prompt("Section is full. Join the waitlist instead? (y/n)", default="y") == "y":
                            entry = waitlist.join(sid, secid)
                            pos = waitlist.get_position(sid, secid)
                            print(f"\nAdded to waitlist (position {pos}).")
                        else:
                            print("\nNot enrolled.")
                    else:
                        raise
            elif choice == "2":
                svc.drop_student(prompt_int("Student ID"), prompt_int("Section ID"))
                print("\nDropped. If anyone was waitlisted, they've been auto-enrolled.")
            elif choice == "3":
                rows = svc.list_student_enrollments(prompt_int("Student ID"))
                for r in rows:
                    print(f"{r['course_code']:<8}sec {r['section_number']:<5}"
                          f"{r['status']:<12}{r['grade'] or '-'}")
            elif choice == "4":
                section_id = prompt_int("Section ID")
                entries = waitlist.list_for_section(section_id)
                if not entries:
                    print("\nNo one is waitlisted for this section.")
                for e in entries:
                    print(f"#{e['position']:<4}{e['student_number']:<12}{e['first_name']} {e['last_name']}")
            elif choice == "5":
                waitlist.leave(prompt_int("Student ID"), prompt_int("Section ID"))
                print("\nRemoved from waitlist.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Grading menu
# ----------------------------------------------------------------------

def grading_menu(conn):
    svc = GradingService(conn)
    sections = SectionService(conn)
    while True:
        print_header("GRADING")
        print("1. Assign single grade\n2. Grade whole section\n3. View grade scale\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                svc.assign_grade_by_pair(
                    prompt_int("Student ID"), prompt_int("Section ID"), prompt("Letter grade")
                )
                print("\nGrade recorded.")
            elif choice == "2":
                section_id = prompt_int("Section ID")
                for r in sections.get_roster(section_id):
                    if r["status"] != "enrolled":
                        continue
                    grade = prompt(
                        f"Grade for {r['first_name']} {r['last_name']} ({r['student_id']})",
                        required=False,
                    )
                    if grade:
                        svc.assign_grade_by_pair(r["student_id"], section_id, grade)
                print("\nGrades recorded.")
            elif choice == "3":
                for row in svc.get_grade_scale():
                    print(f"{row['letter']:<4}{row['grade_points']}")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Fees menu
# ----------------------------------------------------------------------

def fees_menu(conn):
    svc = FeeService(conn)
    while True:
        print_header("FEES & PAYMENTS")
        print("1. Assess fee\n2. Record payment\n3. View fee statement\n"
              "4. View student balance\n5. Waive a fee\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                f = svc.assess_fee(
                    student_id=prompt_int("Student ID"),
                    fee_type=prompt("Fee type (e.g. Tuition, Lab Fee)"),
                    amount=prompt_float("Amount"),
                    term_id=prompt_int("Term ID (0 if none)", default=0) or None,
                    due_date=prompt_date("Due date"),
                )
                print(f"\nFee assessed. Fee ID: {f.fee_id}")
            elif choice == "2":
                p = svc.record_payment(
                    fee_id=prompt_int("Fee ID"),
                    amount_paid=prompt_float("Amount paid"),
                    payment_method=prompt("Payment method", required=False),
                    reference_number=prompt("Reference number", required=False),
                )
                print(f"\nPayment recorded. Payment ID: {p.payment_id}")
            elif choice == "3":
                print(reports.generate_fee_statement_report(conn, prompt_int("Student ID")))
            elif choice == "4":
                print(f"\nOutstanding balance: {svc.get_student_balance(prompt_int('Student ID')):.2f}")
            elif choice == "5":
                svc.waive_fee(
                    fee_id=prompt_int("Fee ID"),
                    reason=prompt("Reason (optional)", required=False),
                )
                print("\nFee waived.")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        pause()


# ----------------------------------------------------------------------
# Reports menu
# ----------------------------------------------------------------------

def reports_menu(conn):
    while True:
        print_header("REPORTS")
        print("1. Student transcript\n2. Section roster\n3. Fee statement\n"
              "4. Export transcript as PDF\n0. Back")
        choice = prompt("Choose")
        try:
            if choice == "1":
                print(reports.generate_transcript(conn, prompt_int("Student ID")))
            elif choice == "2":
                print(reports.generate_section_roster_report(conn, prompt_int("Section ID")))
            elif choice == "3":
                print(reports.generate_fee_statement_report(conn, prompt_int("Student ID")))
            elif choice == "4":
                sid = prompt_int("Student ID")
                out_path = prompt("Save PDF as", default=f"transcript_{sid}.pdf")
                buf = pdf_reports.generate_transcript_pdf(conn, sid)
                with open(out_path, "wb") as f:
                    f.write(buf.read())
                print(f"\nSaved to {out_path}")
            elif choice == "0":
                return
            else:
                print("Invalid choice.")
        except SISError as e:
            print(f"\nError: {e}")
        except RuntimeError as e:
            print(f"\n{e}")
        pause()


# ----------------------------------------------------------------------
# Main menu
# ----------------------------------------------------------------------

def run_cli(conn):
    menus = {
        "1": ("Student Management", student_menu),
        "2": ("Teacher Management", teacher_menu),
        "3": ("Course Management", course_menu),
        "4": ("Term Management", term_menu),
        "5": ("Section Management", section_menu),
        "6": ("Enrollment", enrollment_menu),
        "7": ("Grading", grading_menu),
        "8": ("Fees & Payments", fees_menu),
        "9": ("Reports", reports_menu),
    }
    while True:
        print_header("STUDENT INFORMATION SYSTEM")
        for key, (label, _) in menus.items():
            print(f"{key}. {label}")
        print("0. Exit")
        choice = input("\nChoose: ").strip()
        if choice == "0":
            print("Goodbye.")
            return
        if choice in menus:
            menus[choice][1](conn)
        else:
            print("Invalid choice.")
