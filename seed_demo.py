"""Populates the database with realistic sample data so the system can be
explored immediately without manual data entry.

Run directly: `python seed_demo.py`
"""

from database import get_connection, initialize_database, DB_PATH
from auth_service import AuthService
from student_service import StudentService
from teacher_service import TeacherService
from course_service import CourseService
from term_service import TermService
from section_service import SectionService
from enrollment_service import EnrollmentService
from grading_service import GradingService
from fee_service import FeeService


def seed(conn):
    conn.executemany(
        "INSERT INTO departments (code, name) VALUES (?, ?)",
        [
            ("CS", "Computer Science"),
            ("BUS", "Business Administration"),
            ("EE", "Electrical Engineering"),
        ],
    )
    conn.commit()
    dept = {r["code"]: r["department_id"] for r in conn.execute("SELECT * FROM departments")}

    terms = TermService(conn)
    fall = terms.add_term("Fall 2025", "2025-09-01", "2025-12-20")
    spring = terms.add_term(
        "Spring 2026", "2026-01-15", "2026-05-10",
        add_deadline="2026-08-15", drop_deadline="2026-11-01",
    )
    terms.set_current_term(spring.term_id)

    teachers = TeacherService(conn)
    t1 = teachers.add_teacher("Sarah", "Al-Amri", "s.alamri@academy.edu",
                               department_id=dept["CS"], title="Assistant Professor",
                               hire_date="2020-08-01")
    t2 = teachers.add_teacher("Omar", "Haddad", "o.haddad@academy.edu",
                               department_id=dept["CS"], title="Lecturer",
                               hire_date="2021-01-15")
    t3 = teachers.add_teacher("Layla", "Nasser", "l.nasser@academy.edu",
                               department_id=dept["BUS"], title="Professor",
                               hire_date="2015-09-01")
    t4 = teachers.add_teacher("Khalid", "Rahman", "k.rahman@academy.edu",
                               department_id=dept["EE"], title="Associate Professor",
                               hire_date="2018-01-10")

    courses = CourseService(conn)
    cs101 = courses.add_course("CS101", "Introduction to Programming", 3,
                                department_id=dept["CS"],
                                description="Fundamentals of programming using Python.")
    cs102 = courses.add_course("CS102", "Data Structures", 3, department_id=dept["CS"])
    cs201 = courses.add_course("CS201", "Database Systems", 3, department_id=dept["CS"])
    bus101 = courses.add_course("BUS101", "Principles of Management", 3, department_id=dept["BUS"])
    ee101 = courses.add_course("EE101", "Circuit Analysis", 4, department_id=dept["EE"])
    math101 = courses.add_course("MATH101", "Calculus I", 4)
    stat101 = courses.add_course("STAT101", "Introduction to Statistics", 3, department_id=dept["CS"])
    math201 = courses.add_course("MATH201", "Discrete Mathematics", 3)
    cs301 = courses.add_course("CS301", "Capstone Seminar", 3, department_id=dept["CS"],
                               description="Team capstone project.")

    courses.add_prerequisite(cs102.course_id, cs101.course_id)
    courses.add_prerequisite(cs201.course_id, cs102.course_id)
    courses.add_prerequisite(cs301.course_id, cs102.course_id)
    courses.add_prerequisite_group(cs301.course_id, [stat101.course_id, math201.course_id])

    sections = SectionService(conn)
    sec_cs101_f = sections.add_section(cs101.course_id, fall.term_id, "01",
                                        teacher_id=t1.teacher_id, room="B1-201",
                                        days="SUN,TUE,THU", start_time="09:00",
                                        end_time="09:50", capacity=25)
    sec_math101_f = sections.add_section(math101.course_id, fall.term_id, "01",
                                          teacher_id=t2.teacher_id, room="A2-105",
                                          days="MON,WED", start_time="11:00",
                                          end_time="12:15", capacity=30)
    sec_cs102_s = sections.add_section(cs102.course_id, spring.term_id, "01",
                                        teacher_id=t1.teacher_id, room="B1-202",
                                        days="SUN,TUE,THU", start_time="09:00",
                                        end_time="09:50", capacity=3)
    sec_bus101_s = sections.add_section(bus101.course_id, spring.term_id, "01",
                                         teacher_id=t3.teacher_id, room="C3-301",
                                         days="MON,WED", start_time="13:00",
                                         end_time="14:15", capacity=40)
    sec_ee101_s = sections.add_section(ee101.course_id, spring.term_id, "01",
                                        teacher_id=t4.teacher_id, room="D1-110",
                                        days="SUN,TUE,THU", start_time="10:00",
                                        end_time="10:50", capacity=20)

    students = StudentService(conn)
    names = [
        ("Ahmed", "Al-Qahtani"), ("Fatimah", "Al-Otaibi"), ("Yousef", "Al-Harbi"),
        ("Noura", "Al-Dosari"), ("Faisal", "Al-Ghamdi"), ("Reem", "Al-Shehri"),
        ("Abdullah", "Al-Mutairi"), ("Sara", "Al-Zahrani"), ("Turki", "Al-Anazi"),
        ("Hessa", "Al-Subaie"),
    ]
    created_students = []
    for i, (fn, ln) in enumerate(names):
        s = students.add_student(
            fn, ln, f"{fn.lower()}.{ln.lower().replace('-', '')}@student.academy.edu",
            program="Computer Science" if i % 2 == 0 else "Business Administration",
            department_id=dept["CS"] if i % 2 == 0 else dept["BUS"],
            enrollment_date="2025-09-01",
        )
        created_students.append(s)

    enrollments = EnrollmentService(conn)
    grading = GradingService(conn)

    fall_grades = ["A", "A-", "B+", "B", "B-", "A", "C+", "B", "A-", "B+"]
    for s, g in zip(created_students, fall_grades):
        enrollments.enroll_student(s.student_id, sec_cs101_f.section_id)
        grading.assign_grade_by_pair(s.student_id, sec_cs101_f.section_id, g)
        enrollments.enroll_student(s.student_id, sec_math101_f.section_id)
        grading.assign_grade_by_pair(s.student_id, sec_math101_f.section_id, g)

    for i, s in enumerate(created_students):
        if i % 2 == 0:
            enrollments.enroll_or_waitlist(s.student_id, sec_cs102_s.section_id)
        else:
            enrollments.enroll_student(s.student_id, sec_bus101_s.section_id)
        if i < 4:
            enrollments.enroll_student(s.student_id, sec_ee101_s.section_id)

    fees = FeeService(conn)
    for i, s in enumerate(created_students):
        f1 = fees.assess_fee(s.student_id, "Tuition", 8000, term_id=fall.term_id, due_date="2025-09-15")
        fees.record_payment(f1.fee_id, 8000, payment_method="Bank Transfer")

        f2 = fees.assess_fee(s.student_id, "Tuition", 8500, term_id=spring.term_id, due_date="2026-01-30")
        if i == 5:
            fees.waive_fee(f2.fee_id, reason="Merit scholarship")
        elif i % 3 == 0:
            fees.record_payment(f2.fee_id, 8500, payment_method="Bank Transfer")
        elif i % 3 == 1:
            fees.record_payment(f2.fee_id, 4000, payment_method="Cash")
        # else: left unpaid, to demonstrate an outstanding balance

    # Demo login accounts. These throwaway passwords are for local
    # exploration only -- never reuse them on a reachable server.
    auth = AuthService(conn)
    auth.create_user("admin", "admin-demo-123", "admin")
    auth.create_user("registrar", "registrar-demo-123", "registrar")
    auth.create_user("s.alamri", "teacher-demo-123", "teacher", teacher_id=t1.teacher_id)
    for s in created_students:
        auth.set_student_password(s.student_id, "student-demo-123")

    print(f"Demo data loaded into {DB_PATH}")
    print(f"Students: {len(created_students)}  Teachers: 4  Courses: 9  Terms: 2  Sections: 5")
    print("Includes: a waitlisted section (CS102), an OR-prerequisite course (CS301), "
          "add/drop deadlines (Spring 2026), and one waived fee.")
    print()
    print("Demo logins (local exploration only):")
    print("  staff    -> admin / admin-demo-123, registrar / registrar-demo-123")
    print("  teacher  -> s.alamri / teacher-demo-123 (Sarah Al-Amri's sections)")
    print(f"  student  -> {created_students[0].student_number} / student-demo-123 "
          "(every seeded student uses this password)")


def main():
    conn = get_connection()
    initialize_database(conn)
    existing = conn.execute("SELECT COUNT(*) AS cnt FROM students").fetchone()["cnt"]
    if existing > 0:
        print(f"Database already has {existing} students. Delete {DB_PATH} first for a fresh demo load.")
        return
    seed(conn)


if __name__ == "__main__":
    main()
