"""Backend business-rule tests for SIS v2."""

import pytest

from admissions_service import AdmissionsService
from auth_service import AuthService
from course_service import CourseService
from enrollment_service import EnrollmentService
from fee_service import FeeService
from grading_service import GradingService
from gpa_service import GPAService
from student_service import StudentService
from exceptions import DuplicateError, PaymentError, PrerequisiteError, ValidationError


# -- grading & GPA (100-point -> letter -> 5.0) ---------------------------

@pytest.mark.parametrize("mark,letter,points", [
    (96, "A+", 5.00), (92, "A", 4.75), (88, "B+", 4.50), (81, "B", 4.00),
    (77, "C+", 3.50), (72, "C", 3.00), (66, "D+", 2.50), (61, "D", 2.00), (40, "F", 1.00),
])
def test_mark_maps_to_letter_and_points(world, mark, letter, points):
    g = GradingService(world["conn"])
    EnrollmentService(world["conn"]).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    e = g.assign_mark_by_pair(world["male"].student_id, world["sec_m"].section_id, mark)
    assert e.grade == letter
    assert e.grade_points == points
    assert e.numeric_mark == mark


def test_credit_weighted_gpa_on_5_scale(world):
    conn = world["conn"]
    en, g = EnrollmentService(conn), GradingService(conn)
    gpa = GPAService(conn)
    en.enroll_student(world["male"].student_id, world["sec_m"].section_id)
    g.assign_mark_by_pair(world["male"].student_id, world["sec_m"].section_id, 96)  # A+ = 5.0, 3hrs
    assert gpa.calculate_cumulative_gpa(world["male"].student_id) == pytest.approx(5.0)
    assert gpa.get_earned_credit_hours(world["male"].student_id) == 3
    assert gpa.get_remaining_credit_hours(world["male"].student_id) == 117


# -- gender segregation ---------------------------------------------------

def test_student_cannot_enroll_in_other_gender_section(world):
    en = EnrollmentService(world["conn"])
    # female student, male section -> rejected
    with pytest.raises(ValidationError):
        en.enroll_student(world["female"].student_id, world["sec_m"].section_id)
    # female student, female section -> ok
    e = en.enroll_student(world["female"].student_id, world["sec_f"].section_id)
    assert e.status == "enrolled"


def test_registration_only_lists_same_gender_sections(world):
    from section_service import SectionService
    secs = SectionService(world["conn"]).list_sections(gender="female")
    assert all(s.gender == "female" for s in secs)
    assert world["sec_f"].section_id in [s.section_id for s in secs]
    assert world["sec_m"].section_id not in [s.section_id for s in secs]


# -- prerequisites still enforced -----------------------------------------

def test_prerequisite_enforced(world):
    en, g = EnrollmentService(world["conn"]), GradingService(world["conn"])
    with pytest.raises(PrerequisiteError):
        en.enroll_student(world["male"].student_id, world["sec102_m"].section_id)
    en.enroll_student(world["male"].student_id, world["sec_m"].section_id)
    g.assign_mark_by_pair(world["male"].student_id, world["sec_m"].section_id, 90)
    assert en.enroll_student(world["male"].student_id, world["sec102_m"].section_id).status == "enrolled"


# -- national ID validation ----------------------------------------------

@pytest.mark.parametrize("bad", ["123", "12345678901", "abcdefghij", "12345 6789"])
def test_national_id_must_be_10_digits(world, bad):
    with pytest.raises(ValidationError):
        StudentService(world["conn"]).add_student(
            "X", "Y", "x@y.edu", national_id=bad, gender="male")


def test_duplicate_national_id_rejected(world):
    with pytest.raises(DuplicateError):
        StudentService(world["conn"]).add_student(
            "Dup", "Licate", "dup@y.edu", national_id="1111111111", gender="male")


# -- multiple teachers per course ----------------------------------------

def test_course_has_multiple_teachers(world):
    ts = CourseService(world["conn"]).get_teachers(world["cs101"].course_id)
    assert len(ts) == 2


# -- financial: registration fee, non-Saudi VAT, per-course billing -------

def test_registration_fee_taxes_non_saudi_only(world):
    conn = world["conn"]
    fees = FeeService(conn)
    # Saudi male: no VAT
    fees.charge_registration_fee(world["male"].student_id, world["term"].term_id)
    male_fee = fees.list_fees_for_student(world["male"].student_id)[0]
    assert male_fee.fee_type == "Registration"
    assert male_fee.tax_amount == 0

    # Non-Saudi female: 15% VAT on the 500 registration fee
    fees.charge_registration_fee(world["female"].student_id, world["term"].term_id)
    female_fee = fees.list_fees_for_student(world["female"].student_id)[0]
    assert female_fee.tax_amount == pytest.approx(75.0)
    assert female_fee.total == pytest.approx(575.0)


def test_per_course_billing_and_overpayment_blocked(world):
    conn = world["conn"]
    fees = FeeService(conn)
    fee = fees.bill_course(world["male"].student_id, world["cs101"].course_id, world["term"].term_id)
    assert fee.fee_type == "Tuition" and fee.amount == 1000
    with pytest.raises(PaymentError):
        fees.record_payment(fee.fee_id, 2000)
    fees.record_payment(fee.fee_id, 1000)
    assert fees.get_fee(fee.fee_id).status == "paid"


def test_registration_fee_charged_once(world):
    fees = FeeService(world["conn"])
    fees.charge_registration_fee(world["male"].student_id, world["term"].term_id)
    assert fees.charge_registration_fee(world["male"].student_id, world["term"].term_id) is None


# -- admissions approval workflow -----------------------------------------

def test_admission_requires_all_fields(world):
    adm = AdmissionsService(world["conn"])
    with pytest.raises(ValidationError):
        adm.submit_application(
            national_id="3333333333", first_name="A", second_name="", third_name="C",
            last_name="D", name_ar="اسم", email="a@b.com", phone="055", date_of_birth="2005-01-01",
            gender="male", nationality="Saudi")


def test_admission_approval_creates_active_student(world):
    conn = world["conn"]
    adm = AdmissionsService(conn)
    app = adm.submit_application(
        national_id="3333333333", first_name="New", second_name="Mid", third_name="Third",
        last_name="Comer", name_ar="طالب جديد كامل", email="new@b.com", phone="0550001112",
        date_of_birth="2005-01-01", gender="male", nationality="Saudi", major_id=world["cs"].major_id)
    assert adm.count_pending() == 1

    student = adm.approve(app.application_id, reviewer="staff:admin")
    assert student.status == "active"
    assert student.national_id == "3333333333"
    assert student.student_number.startswith("S")
    assert adm.count_pending() == 0
    # portal password defaults to national ID
    assert AuthService(conn).authenticate_student(student.student_number, "3333333333") is not None


def test_admission_reject(world):
    conn = world["conn"]
    adm = AdmissionsService(conn)
    app = adm.submit_application(
        national_id="4444444444", first_name="Re", second_name="Ject", third_name="Ed",
        last_name="One", name_ar="طالب مرفوض هنا", email="rej@b.com", phone="0550001113",
        date_of_birth="2005-01-01", gender="female", nationality="Saudi")
    adm.reject(app.application_id, reviewer="staff:admin", note="Incomplete documents")
    assert adm.get_application(app.application_id).status == "rejected"
    assert adm.count_pending() == 0


# -- /50 components and grades deadline -----------------------------------

def test_breakdown_components_are_out_of_50(world):
    conn = world["conn"]
    EnrollmentService(conn).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    g = GradingService(conn)
    with pytest.raises(ValidationError):
        g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 60, 30)
    with pytest.raises(ValidationError):
        g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 30, 55)
    e = g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 50, 50)
    assert e.numeric_mark == 100 and e.grade == "A+"


def test_teacher_can_regrade_before_deadline_then_locked_after(world):
    conn = world["conn"]
    from term_service import TermService
    from exceptions import DeadlineError
    EnrollmentService(conn).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    g = GradingService(conn)

    # Deadline in the future: grade, then edit again freely.
    TermService(conn).update_term(world["term"].term_id, grades_deadline="2030-12-01")
    g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 40, 30)
    assert not g.editing_locked(world["sec_m"].section_id, as_of="2030-11-30")
    e = g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 45, 40)
    assert e.numeric_mark == 85  # edit applied

    # After the deadline: locked.
    assert g.editing_locked(world["sec_m"].section_id, as_of="2030-12-02")
    with pytest.raises(DeadlineError):
        g.check_editing_open(world["sec_m"].section_id, as_of="2030-12-02")


def test_reassigned_section_moves_to_new_teachers_portal(world):
    conn = world["conn"]
    from section_service import SectionService
    sections = SectionService(conn)
    sec = world["sec_m"]
    # Currently belongs to t_m; reassign to t_f.
    assert sec.section_id in [s.section_id for s in sections.list_sections(teacher_id=world["t_m"].teacher_id)]
    sections.update_section(sec.section_id, teacher_id=world["t_f"].teacher_id)
    assert sec.section_id in [s.section_id for s in sections.list_sections(teacher_id=world["t_f"].teacher_id)]
    assert sec.section_id not in [s.section_id for s in sections.list_sections(teacher_id=world["t_m"].teacher_id)]


def test_section_broadcast_email_logged_per_student(world):
    conn = world["conn"]
    from mail_service import MailService
    EnrollmentService(conn).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    rows = conn.execute(
        """SELECT s.email FROM enrollments e JOIN students s ON s.student_id = e.student_id
           WHERE e.section_id = ? AND e.status IN ('enrolled','completed')""",
        (world["sec_m"].section_id,),
    ).fetchall()
    mail = MailService(conn)
    for r in rows:
        assert mail.send(r["email"], "تنبيه", "الاختبار غداً", kind="section_email") == "logged"
    logged = conn.execute(
        "SELECT COUNT(*) c FROM email_log WHERE kind = 'section_email'"
    ).fetchone()["c"]
    assert logged == len(rows) == 1


def test_attendance_record_and_summaries(world):
    conn = world["conn"]
    from attendance_service import AttendanceService
    EnrollmentService(conn).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    att = AttendanceService(conn)
    att.record_bulk(world["sec_m"].section_id, "2030-10-01",
                    {world["male"].student_id: "absent"}, recorded_by="staff:t")
    att.record_bulk(world["sec_m"].section_id, "2030-10-02",
                    {world["male"].student_id: "present"}, recorded_by="staff:t")
    # overwrite same date
    att.record_bulk(world["sec_m"].section_id, "2030-10-01",
                    {world["male"].student_id: "excused"}, recorded_by="staff:t")
    summary = att.section_summary(world["sec_m"].section_id)[world["male"].student_id]
    assert summary.get("excused") == 1 and summary.get("present") == 1
    assert "absent" not in summary
    rows = att.student_summary(world["male"].student_id)
    assert rows[0]["total"] == 2 and rows[0]["excused"] == 1


def test_pdf_transcript_generates(world):
    conn = world["conn"]
    import pdf_reports
    EnrollmentService(conn).enroll_student(world["male"].student_id, world["sec_m"].section_id)
    GradingService(conn).assign_breakdown_by_pair(
        world["male"].student_id, world["sec_m"].section_id, 45, 45)
    buf = pdf_reports.generate_transcript_pdf(conn, world["male"].student_id)
    data = buf.read()
    assert data[:5] == b"%PDF-" and len(data) > 800


# -- staff role management -------------------------------------------------

def test_update_user_role_and_last_admin_guard(world):
    conn = world["conn"]
    auth = AuthService(conn)
    boss = auth.create_user("boss", "boss-pass-123", "admin", full_name="مدير")
    clerk = auth.create_user("clerk", "clerk-pass-123", "registrar", full_name="موظف")

    # Promote/change a normal user's role, with a new display name.
    updated = auth.update_user(clerk.user_id, "accounting", full_name="موظف مالي")
    assert updated.role == "accounting" and updated.full_name == "موظف مالي"

    # Teacher role requires a linked teacher record.
    with pytest.raises(ValidationError):
        auth.update_user(clerk.user_id, "teacher")
    linked = auth.update_user(clerk.user_id, "teacher", teacher_id=world["t_m"].teacher_id)
    assert linked.teacher_id == world["t_m"].teacher_id
    # Leaving the teacher role clears the link.
    assert auth.update_user(clerk.user_id, "registrar").teacher_id is None

    # The last active admin can never lose the admin role.
    with pytest.raises(ValidationError):
        auth.update_user(boss.user_id, "registrar")
    auth.create_user("boss2", "boss2-pass-123", "admin")
    assert auth.update_user(boss.user_id, "registrar").role == "registrar"


def test_outstanding_invoices_listing(world):
    conn = world["conn"]
    fees = FeeService(conn)
    fee = fees.assess_fee(world["male"].student_id, "Tuition", 500,
                          term_id=world["term"].term_id, course_id=world["cs101"].course_id)
    fees.record_payment(fee.fee_id, 200)
    paid_off = fees.assess_fee(world["female"].student_id, "Registration", 300)
    fees.record_payment(paid_off.fee_id, 300)

    rows = fees.list_outstanding()
    assert fees.count_outstanding() == 1 and len(rows) == 1
    row = rows[0]
    assert row["student_number"] == world["male"].student_number
    assert row["course_code"] == "CS101"
    assert row["paid"] == 200 and row["amount"] + row["tax_amount"] - row["paid"] == 300

    # Search narrows by student number or name; misses return nothing.
    assert fees.count_outstanding(world["male"].student_number) == 1
    assert fees.count_outstanding("علي") == 1
    assert fees.count_outstanding("no-such-student") == 0
