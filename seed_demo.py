"""Populates the database with realistic bilingual sample data so the
system can be explored immediately.

Run directly: `python seed_demo.py`
"""

from database import get_connection, initialize_database, DB_PATH
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
from fee_service import FeeService
from request_service import RequestService


def seed(conn):
    conn.executemany(
        "INSERT INTO departments (code, name, name_ar) VALUES (?, ?, ?)",
        [("CS", "Computer Science", "علوم الحاسب"),
         ("BUS", "Business Administration", "إدارة الأعمال"),
         ("EE", "Electrical Engineering", "الهندسة الكهربائية")],
    )
    conn.commit()
    dept = {r["code"]: r["department_id"] for r in conn.execute("SELECT * FROM departments")}

    majors = MajorService(conn)
    cs_m = majors.add_major("CS-M", "Computer Science", "علوم الحاسب", 132, dept["CS"], "male")
    cs_f = majors.add_major("CS-F", "Computer Science", "علوم الحاسب", 132, dept["CS"], "female")
    bus = majors.add_major("BUS", "Business Administration", "إدارة الأعمال", 126, dept["BUS"], "any")

    terms = TermService(conn)
    year = terms.get_or_create_year("2025-2026", "1447هـ")
    fall = terms.add_term("Fall 2025", "2025-09-01", "2025-12-20", name_ar="الفصل الأول",
                          academic_year_id=year.year_id)
    spring = terms.add_term("Spring 2026", "2026-01-15", "2026-05-10", name_ar="الفصل الثاني",
                            academic_year_id=year.year_id,
                            add_deadline="2026-08-15", drop_deadline="2026-11-01")
    terms.add_term("Summer 2026", "2026-06-01", "2026-07-31", name_ar="الفصل الصيفي",
                   academic_year_id=year.year_id, kind="summer")
    terms.set_current_term(spring.term_id)

    teachers = TeacherService(conn)
    t_m1 = teachers.add_teacher("Omar", "Haddad", "o.haddad@academy.edu", "عمر حداد",
                                gender="male", department_id=dept["CS"], title="Lecturer")
    t_m2 = teachers.add_teacher("Khalid", "Rahman", "k.rahman@academy.edu", "خالد الرحمن",
                                gender="male", department_id=dept["EE"], title="Associate Professor")
    t_f1 = teachers.add_teacher("Sarah", "Al-Amri", "s.alamri@academy.edu", "سارة العمري",
                                gender="female", department_id=dept["CS"], title="Assistant Professor")
    t_f2 = teachers.add_teacher("Layla", "Nasser", "l.nasser@academy.edu", "ليلى ناصر",
                                gender="female", department_id=dept["BUS"], title="Professor")

    courses = CourseService(conn)
    cs101 = courses.add_course("CS101", "Introduction to Programming", 3,
                               title_ar="مقدمة في البرمجة", price=1500,
                               department_id=dept["CS"], major_id=cs_m.major_id)
    cs102 = courses.add_course("CS102", "Data Structures", 3, title_ar="هياكل البيانات",
                               price=1500, department_id=dept["CS"])
    bus101 = courses.add_course("BUS101", "Principles of Management", 3,
                                title_ar="مبادئ الإدارة", price=1200, department_id=dept["BUS"])
    math101 = courses.add_course("MATH101", "Calculus I", 4, title_ar="التفاضل والتكامل ١", price=2000)
    courses.add_prerequisite(cs102.course_id, cs101.course_id)
    # Multiple teachers per course.
    for c, ts in [(cs101, [t_m1, t_f1]), (cs102, [t_m1, t_f1]), (bus101, [t_f2]), (math101, [t_m2])]:
        for t in ts:
            courses.assign_teacher(c.course_id, t.teacher_id)

    sections = SectionService(conn)
    # Gender-segregated sections of the same course.
    sec_cs101_m = sections.add_section(cs101.course_id, spring.term_id, "01",
                                       teacher_id=t_m1.teacher_id, gender="male",
                                       room="B1-201", days="SUN,TUE", start_time="09:00",
                                       end_time="09:50", capacity=25)
    sec_cs101_f = sections.add_section(cs101.course_id, spring.term_id, "02",
                                       teacher_id=t_f1.teacher_id, gender="female",
                                       room="G1-105", days="SUN,TUE", start_time="09:00",
                                       end_time="09:50", capacity=25)
    sec_bus101_m = sections.add_section(bus101.course_id, spring.term_id, "01",
                                        teacher_id=t_m1.teacher_id, gender="male",
                                        room="C3-301", days="MON,WED", start_time="13:00",
                                        end_time="14:15", capacity=40)
    sec_bus101_f = sections.add_section(bus101.course_id, spring.term_id, "02",
                                        teacher_id=t_f2.teacher_id, gender="female",
                                        room="G3-110", days="MON,WED", start_time="13:00",
                                        end_time="14:15", capacity=40)

    students = StudentService(conn)
    fees = FeeService(conn)
    enrollments = EnrollmentService(conn)
    grading = GradingService(conn)

    roster = [
        # first, last, name_ar, gender, nationality, national_id, major
        ("Ahmed", "Al-Qahtani", "أحمد سعد فهد القحطاني", "male", "Saudi", "1010101010", cs_m),
        ("Yousef", "Al-Harbi", "يوسف علي محمد الحربي", "male", "Saudi", "1020202020", cs_m),
        ("Faisal", "Khan", "فيصل إمران أحمد خان", "male", "Non-Saudi", "2030303030", bus),
        ("Noura", "Al-Dosari", "نورة خالد عبدالله الدوسري", "female", "Saudi", "1040404040", cs_f),
        ("Reem", "Al-Shehri", "ريم فهد سعيد الشهري", "female", "Saudi", "1050505050", cs_f),
        ("Sara", "Ali", "سارة محمد علي", "female", "Non-Saudi", "2060606060", bus),
    ]
    created = []
    for fn, ln, ar, g, nat, nid, major in roster:
        advisor = t_f1 if g == "female" else t_m1
        s = students.add_student(
            fn, ln, f"{fn.lower()}.{ln.lower().replace('-', '')}@student.academy.edu",
            name_ar=ar, national_id=nid, gender=g, nationality=nat,
            major_id=major.major_id, advisor_id=advisor.teacher_id,
            department_id=dept["CS"], enrollment_date="2025-09-01",
        )
        created.append(s)
        AuthService(conn).set_student_password(s.student_id, "student-demo-123")
        # Registration fee (VAT auto-added for non-Saudi) + per-course tuition.
        fees.charge_registration_fee(s.student_id, spring.term_id, due_date="2026-01-30")

    # Enroll into the gender-correct section and bill the course.
    enroll_plan = [
        (created[0], sec_cs101_m), (created[1], sec_cs101_m), (created[2], sec_bus101_m),
        (created[3], sec_cs101_f), (created[4], sec_cs101_f), (created[5], sec_bus101_f),
    ]
    marks = [96, 88, 73, 91, 84, 67]
    for (s, sec), mark in zip(enroll_plan, marks):
        enrollments.enroll_student(s.student_id, sec.section_id)
        fees.bill_course(s.student_id, sec.course_id, spring.term_id, due_date="2026-01-30")
        grading.assign_mark_by_pair(s.student_id, sec.section_id, mark)

    # One student pays fully; leave the rest with a balance.
    for entry in fees.get_fee_statement(created[0].student_id):
        if entry["balance"] > 0:
            fees.record_payment(entry["fee"].fee_id, entry["balance"], payment_method="Bank Transfer")

    # A pending admission application awaiting approval.
    AdmissionsService(conn).submit_application(
        national_id="1077707770", first_name="Turki", second_name="Nasser",
        third_name="Saad", last_name="Al-Anazi", name_ar="تركي ناصر سعد العنزي",
        email="turki.new@example.com", phone="0555000111", date_of_birth="2005-03-01",
        gender="male", nationality="Saudi", major_id=cs_m.major_id,
    )
    # A pending service request.
    RequestService(conn).submit(created[1].student_id, "deferral",
                                "أرغب في تأجيل الفصل لظرف صحي.")

    # Staff accounts, one per role.
    auth = AuthService(conn)
    auth.create_user("admin", "admin-demo-123", "admin")
    auth.create_user("registrar", "registrar-demo-123", "registrar")
    auth.create_user("accountant", "accounting-demo-123", "accounting")
    auth.create_user("o.haddad", "teacher-demo-123", "teacher", teacher_id=t_m1.teacher_id)
    auth.create_user("s.alamri", "teacher-demo-123", "teacher", teacher_id=t_f1.teacher_id)

    print(f"Demo data loaded into {DB_PATH}")
    print("Students: 6 (male+female)  Teachers: 4  Courses: 4  Majors: 3  Terms: 3")
    print()
    print("Demo logins (local exploration only):")
    print("  admin / admin-demo-123          registrar / registrar-demo-123")
    print("  accountant / accounting-demo-123 teacher: o.haddad or s.alamri / teacher-demo-123")
    print(f"  student: {created[0].student_number} / student-demo-123 (all seeded students)")


def main():
    conn = get_connection()
    initialize_database(conn)
    if conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"] > 0:
        print(f"Database already has data. Delete {DB_PATH} first for a fresh demo load.")
        return
    seed(conn)


if __name__ == "__main__":
    main()
