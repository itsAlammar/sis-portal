"""Text report generation: transcripts, rosters, fee statements."""

import sqlite3

from course_service import CourseService
from enrollment_service import EnrollmentService
from fee_service import FeeService
from gpa_service import GPAService
from section_service import SectionService
from student_service import StudentService
from teacher_service import TeacherService
from term_service import TermService


def generate_transcript(conn: sqlite3.Connection, student_id: int) -> str:
    students = StudentService(conn)
    enrollments = EnrollmentService(conn)
    gpa_service = GPAService(conn)
    terms = TermService(conn)

    student = students.get_student(student_id)
    all_rows = enrollments.list_student_enrollments(student_id)

    by_term = {}
    for row in all_rows:
        by_term.setdefault(row["term_id"], []).append(row)

    lines = [
        "=" * 64,
        "OFFICIAL TRANSCRIPT",
        "=" * 64,
        f"Student: {student.full_name} ({student.student_number})",
        f"Program: {student.program or 'N/A'}",
        f"Status:  {student.status}",
        "-" * 64,
    ]

    for term_id, rows in sorted(by_term.items(), key=lambda kv: kv[0]):
        term = terms.get_term(term_id)
        lines.append(f"\n{term.name}")
        lines.append(f"{'Code':<10}{'Title':<28}{'Cr':<4}{'Grade':<6}{'Status':<10}")
        for r in rows:
            lines.append(
                f"{r['course_code']:<10}{r['title'][:26]:<28}"
                f"{r['credit_hours']:<4}{(r['grade'] or '-'):<6}{r['status']:<10}"
            )
        term_gpa = gpa_service.calculate_term_gpa(student_id, term_id)
        term_gpa_str = f"{term_gpa:.2f}" if term_gpa is not None else "N/A"
        lines.append(f"Term GPA: {term_gpa_str}")

    cum_gpa = gpa_service.calculate_cumulative_gpa(student_id)
    cum_gpa_str = f"{cum_gpa:.2f}" if cum_gpa is not None else "N/A"
    standing = gpa_service.get_academic_standing(cum_gpa)
    earned = gpa_service.get_earned_credit_hours(student_id)

    lines += [
        "-" * 64,
        f"Cumulative GPA:      {cum_gpa_str}",
        f"Academic Standing:   {standing}",
        f"Credit Hours Earned: {earned}",
        "=" * 64,
    ]
    return "\n".join(lines)


def generate_section_roster_report(conn: sqlite3.Connection, section_id: int) -> str:
    sections = SectionService(conn)
    courses = CourseService(conn)
    teachers = TeacherService(conn)

    section = sections.get_section(section_id)
    course = courses.get_course(section.course_id)
    roster = sections.get_roster(section_id)

    teacher_name = "TBD"
    if section.teacher_id:
        teacher_name = teachers.get_teacher(section.teacher_id).full_name

    lines = [
        "=" * 60,
        f"SECTION ROSTER: {course.course_code} - {section.section_number}",
        "=" * 60,
        f"Course:    {course.title}",
        f"Teacher:   {teacher_name}",
        f"Schedule:  {section.days or 'TBD'} {section.start_time or ''}-{section.end_time or ''}",
        f"Room:      {section.room or 'TBD'}",
        f"Enrolled:  {len(roster)}/{section.capacity}",
        "-" * 60,
        f"{'Student #':<12}{'Name':<26}{'Status':<12}{'Grade':<6}",
    ]
    for r in roster:
        name = f"{r['first_name']} {r['last_name']}"
        lines.append(
            f"{r['student_number']:<12}{name[:24]:<26}{r['status']:<12}{(r['grade'] or '-'):<6}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def generate_fee_statement_report(conn: sqlite3.Connection, student_id: int) -> str:
    students = StudentService(conn)
    fees = FeeService(conn)

    student = students.get_student(student_id)
    statement = fees.get_fee_statement(student_id)

    lines = [
        "=" * 60,
        f"FEE STATEMENT: {student.full_name} ({student.student_number})",
        "=" * 60,
        f"{'Type':<18}{'Amount':<10}{'Paid':<10}{'Balance':<10}{'Status':<10}",
    ]
    for entry in statement:
        fee = entry["fee"]
        lines.append(
            f"{fee.fee_type[:16]:<18}{fee.amount:<10.2f}{entry['paid']:<10.2f}"
            f"{entry['balance']:<10.2f}{fee.status:<10}"
        )
    total_balance = fees.get_student_balance(student_id)
    lines += ["-" * 60, f"TOTAL BALANCE DUE: {total_balance:.2f}", "=" * 60]
    return "\n".join(lines)
