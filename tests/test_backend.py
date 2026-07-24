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


# -- absence excuses --------------------------------------------------------

def test_absence_excuse_approval_sets_excused(world):
    conn = world["conn"]
    from attendance_service import AttendanceService
    from request_service import RequestService
    sid, sec = world["male"].student_id, world["sec_m"].section_id
    EnrollmentService(conn).enroll_student(sid, sec)
    att, reqs = AttendanceService(conn), RequestService(conn)
    att.record_bulk(sec, "2030-10-05", {sid: "absent"}, recorded_by="staff:t")

    req = reqs.submit(sid, "absence_excuse", "ظرف صحي", section_id=sec, date="2030-10-05")
    assert req.section_id == sec and req.date == "2030-10-05"
    # Same absence can't be excused twice while pending/approved.
    with pytest.raises(ValidationError):
        reqs.submit(sid, "absence_excuse", "duplicate", section_id=sec, date="2030-10-05")
    # Section and date are mandatory for this kind.
    with pytest.raises(ValidationError):
        reqs.submit(sid, "absence_excuse", "no date", section_id=sec)

    reqs.review(req.request_id, "approved", "staff:registrar")
    assert att.for_section_date(sec, "2030-10-05")[sid] == "excused"


def test_absence_excuse_rejection_keeps_absent(world):
    conn = world["conn"]
    from attendance_service import AttendanceService
    from request_service import RequestService
    sid, sec = world["male"].student_id, world["sec_m"].section_id
    EnrollmentService(conn).enroll_student(sid, sec)
    att, reqs = AttendanceService(conn), RequestService(conn)
    att.record_bulk(sec, "2030-10-06", {sid: "absent"}, recorded_by="staff:t")
    req = reqs.submit(sid, "absence_excuse", "", section_id=sec, date="2030-10-06")
    reqs.review(req.request_id, "rejected", "staff:registrar")
    assert att.for_section_date(sec, "2030-10-06")[sid] == "absent"
    assert [a["date"] for a in att.student_absences(sid)] == ["2030-10-06"]


# -- flexible per-course grade split ----------------------------------------

def test_flexible_grade_split_per_course(world):
    conn = world["conn"]
    courses, g, en = CourseService(conn), GradingService(conn), EnrollmentService(conn)
    from section_service import SectionService
    flex = courses.add_course("FLX101", "Flexible", 3, coursework_max=40)
    assert flex.coursework_max == 40 and flex.final_max == 60
    sec = SectionService(conn).add_section(flex.course_id, world["term"].term_id, "01",
                                           gender="male", capacity=5)
    en.enroll_student(world["male"].student_id, sec.section_id)

    e = g.assign_breakdown_by_pair(world["male"].student_id, sec.section_id, 35, 55)
    assert e.numeric_mark == 90 and e.coursework_mark == 35 and e.final_mark == 55
    with pytest.raises(ValidationError):
        g.assign_breakdown_by_pair(world["male"].student_id, sec.section_id, 45, 30)

    # Default courses still enforce the 50/50 split.
    en.enroll_student(world["male"].student_id, world["sec_m"].section_id)
    with pytest.raises(ValidationError):
        g.assign_breakdown_by_pair(world["male"].student_id, world["sec_m"].section_id, 55, 40)

    # Split is editable per course and validated.
    assert courses.update_course(flex.course_id, coursework_max=70).coursework_max == 70
    with pytest.raises(ValidationError):
        courses.update_course(flex.course_id, coursework_max=101)


# -- payment receipt PDF ----------------------------------------------------

def test_receipt_pdf_generates(world):
    conn = world["conn"]
    import pdf_reports
    fees = FeeService(conn)
    fee = fees.assess_fee(world["male"].student_id, "Registration", 500)
    payment = fees.record_payment(fee.fee_id, 200, payment_method="Cash")
    buf = pdf_reports.generate_receipt_pdf(conn, payment.payment_id)
    data = buf.read()
    assert data[:5] == b"%PDF-" and len(data) > 500
    row = fees.get_payment(payment.payment_id)
    assert row["student_id"] == world["male"].student_id
    assert row["amount_paid"] == 200


def test_excuse_requires_a_real_recorded_absence(world):
    """Audit fix: a portal user must not be able to raise an excuse for an
    arbitrary section/date they were never marked absent in."""
    conn = world["conn"]
    from request_service import RequestService
    sid, sec = world["male"].student_id, world["sec_m"].section_id
    EnrollmentService(conn).enroll_student(sid, sec)
    with pytest.raises(ValidationError):
        RequestService(conn).submit(sid, "absence_excuse", "fake",
                                    section_id=sec, date="2030-11-11")


# -- exam schedule ----------------------------------------------------------

def test_exam_upsert_and_listings(world):
    conn = world["conn"]
    from exam_service import ExamService
    ex, en = ExamService(conn), EnrollmentService(conn)
    sid = world["male"].student_id
    en.enroll_student(sid, world["sec_m"].section_id)

    ex.set_exam(world["sec_m"].section_id, "final", "2030-12-01", "09:00", "11:00", "H-1")
    # Saving the same section+kind again replaces, never duplicates.
    row = ex.set_exam(world["sec_m"].section_id, "final", "2030-12-02", "10:00", "12:00", "H-2")
    assert row["date"] == "2030-12-02" and row["room"] == "H-2"
    assert len(ex.list_for_term(world["term"].term_id)) == 1

    with pytest.raises(ValidationError):
        ex.set_exam(world["sec_m"].section_id, "quiz", "2030-12-03")
    with pytest.raises(ValidationError):
        ex.set_exam(world["sec_m"].section_id, "final", "  ")

    mine = ex.list_for_student(sid)
    assert [x["exam_id"] for x in mine] == [row["exam_id"]]
    # The teacher of the section sees it too; another teacher doesn't.
    assert len(ex.list_for_teacher(world["t_m"].teacher_id)) == 1
    assert ex.list_for_teacher(world["t_f"].teacher_id) == []

    ex.delete_exam(row["exam_id"])
    assert ex.list_for_term(world["term"].term_id) == []


def test_exam_conflict_detection(world):
    conn = world["conn"]
    from exam_service import ExamService
    from section_service import SectionService
    ex, en = ExamService(conn), EnrollmentService(conn)
    sid = world["male"].student_id
    other = CourseService(conn).add_course("PHY101", "Physics", 3)
    sec_other = SectionService(conn).add_section(other.course_id, world["term"].term_id,
                                                 "01", gender="male", capacity=5)
    en.enroll_student(sid, world["sec_m"].section_id)   # CS101
    en.enroll_student(sid, sec_other.section_id)        # PHY101

    ex.set_exam(world["sec_m"].section_id, "final", "2030-12-10", "09:00", "11:00")
    ex.set_exam(sec_other.section_id, "final", "2030-12-10", "10:00", "12:00")
    assert len(ex.conflicting_exam_ids(sid, world["term"].term_id)) == 2

    # Moving the second exam to a non-overlapping slot clears the conflict.
    ex.set_exam(sec_other.section_id, "final", "2030-12-10", "11:00", "13:00")
    assert ex.conflicting_exam_ids(sid, world["term"].term_id) == set()

    # Missing times = all-day slot -> conflicts with anything that date.
    ex.set_exam(sec_other.section_id, "final", "2030-12-10")
    assert len(ex.conflicting_exam_ids(sid, world["term"].term_id)) == 2


# -- structured curriculum / degree plan ----------------------------------

def test_curriculum_add_list_and_dedupe(world):
    from curriculum_service import CurriculumService
    from exceptions import DuplicateError, ValidationError, NotFoundError
    cur = CurriculumService(world["conn"])
    cur.add_course(world["cs"].major_id, world["cs102"].course_id, level=2, kind="required")
    cur.add_course(world["cs"].major_id, world["cs101"].course_id, level=1, kind="required")
    entries = cur.list_for_major(world["cs"].major_id)
    # Ordered by level: CS101 (level 1) before CS102 (level 2).
    assert [e["course_code"] for e in entries] == ["CS101", "CS102"]
    assert cur.plan_total_hours(world["cs"].major_id) == 6
    with pytest.raises(DuplicateError):
        cur.add_course(world["cs"].major_id, world["cs101"].course_id)
    with pytest.raises(ValidationError):
        cur.add_course(world["cs"].major_id, world["cs102"].course_id, level=99)
    with pytest.raises(NotFoundError):
        cur.add_course(world["cs"].major_id, 99999)


def test_curriculum_plan_status_and_prereq_warning(world):
    from curriculum_service import CurriculumService
    conn = world["conn"]
    cur = CurriculumService(conn)
    en, g = EnrollmentService(conn), GradingService(conn)
    sid = world["male"].student_id
    cur.add_course(world["cs"].major_id, world["cs101"].course_id, level=1, kind="required")
    cur.add_course(world["cs"].major_id, world["cs102"].course_id, level=2, kind="required")

    # Nothing done yet: both remaining; CS102 warns because CS101 not completed.
    plan = cur.plan_for_student(sid)
    assert plan["plan_hours"] == 6 and plan["done_hours"] == 0
    flat = {i["course_code"]: i for lvl, items in plan["levels"] for i in items}
    assert flat["CS101"]["status"] == "remaining"
    assert flat["CS102"]["status"] == "remaining"
    assert flat["CS102"]["prereq_warning"] == ["CS101"]

    # Enroll (not graded) -> in_progress.
    en.enroll_student(sid, world["sec_m"].section_id)
    flat = {i["course_code"]: i for lvl, items in cur.plan_for_student(sid)["levels"] for i in items}
    assert flat["CS101"]["status"] == "in_progress"

    # Grade & complete CS101 -> completed, done_hours counts, warning clears.
    g.assign_mark_by_pair(sid, world["sec_m"].section_id, 90)
    plan = cur.plan_for_student(sid)
    assert plan["done_hours"] == 3 and plan["remaining_hours"] == 3
    flat = {i["course_code"]: i for lvl, items in plan["levels"] for i in items}
    assert flat["CS101"]["status"] == "completed"
    assert flat["CS102"]["prereq_warning"] == []


def test_curriculum_plan_none_without_major(world):
    from curriculum_service import CurriculumService
    from student_service import StudentService
    conn = world["conn"]
    s = StudentService(conn).add_student("No", "Major", "nomajor@s.edu",
                                         national_id="3333333333", gender="male")
    assert CurriculumService(conn).plan_for_student(s.student_id) is None


# -- timetable conflict detection & draft generation ----------------------

def _sched(conn, section_id, days, start, end, room=None):
    from section_service import SectionService
    fields = {"days": days, "start_time": start, "end_time": end}
    if room is not None:
        fields["room"] = room
    SectionService(conn).update_section(section_id, **fields)


def test_timetable_teacher_and_room_conflicts(world):
    from timetable_service import TimetableService
    conn = world["conn"]
    tt = TimetableService(conn)
    tid = world["term"].term_id
    # sec_m (t_m) and sec102_m (t_m) overlap -> teacher clash.
    _sched(conn, world["sec_m"].section_id, "SUN,TUE", "09:00", "09:50", room="R1")
    _sched(conn, world["sec102_m"].section_id, "SUN", "09:30", "10:20", room="R2")
    kinds = {c.kind for c in tt.section_conflicts(tid)}
    assert "teacher" in kinds
    assert world["sec_m"].section_id in tt.conflicting_section_ids(tid)

    # sec_f (t_f, different teacher) shares R1 with sec_m at the same time -> room clash.
    _sched(conn, world["sec_f"].section_id, "SUN", "09:00", "09:50", room="R1")
    kinds = {c.kind for c in tt.section_conflicts(tid)}
    assert "room" in kinds

    # Moving sec102_m off the overlap removes the teacher clash.
    _sched(conn, world["sec102_m"].section_id, "MON", "11:00", "11:50", room="R2")
    assert "teacher" not in {c.kind for c in tt.section_conflicts(tid)}


def test_timetable_student_conflict(world):
    from timetable_service import TimetableService
    from section_service import SectionService
    conn = world["conn"]
    en = EnrollmentService(conn)
    tid = world["term"].term_id
    # A prereq-free course/section the male student can join alongside CS101.
    phy = CourseService(conn).add_course("PHY101", "Physics", 3)
    phy_sec = SectionService(conn).add_section(phy.course_id, tid, "01", gender="male", capacity=5)
    _sched(conn, world["sec_m"].section_id, "SUN,TUE", "09:00", "09:50")
    _sched(conn, phy_sec.section_id, "SUN", "09:30", "10:20")
    # override_conflicts lets us construct the clash the report should then flag
    # (normal enrollment would reject the second one).
    en.enroll_student(world["male"].student_id, world["sec_m"].section_id)
    en.enroll_student(world["male"].student_id, phy_sec.section_id, override_conflicts=True)
    conflicts = TimetableService(conn).section_conflicts(tid)
    assert any(c.kind == "student" for c in conflicts)


def test_timetable_draft_avoids_teacher_room_clash(world):
    from timetable_service import TimetableService
    from section_service import SectionService
    conn = world["conn"]
    tt, secs = TimetableService(conn), SectionService(conn)
    tid = world["term"].term_id
    # Three unscheduled male sections, two share teacher t_m -> greedy must
    # separate those in time.
    result = tt.generate_draft(tid)
    assert result["placed"] >= 3 and result["unplaced"] == []
    # No teacher/room clash after the draft.
    kinds = {c.kind for c in tt.section_conflicts(tid)}
    assert "teacher" not in kinds and "room" not in kinds


def test_timetable_draft_respects_fixed_sections(world):
    from timetable_service import TimetableService
    from section_service import SectionService
    conn = world["conn"]
    tt = TimetableService(conn)
    tid = world["term"].term_id
    _sched(conn, world["sec_m"].section_id, "SUN,TUE,THU", "08:00", "08:50")
    result = tt.generate_draft(tid, overwrite_fixed=False)
    assert result["kept"] >= 1
    fixed = SectionService(conn).get_section(world["sec_m"].section_id)
    assert fixed.days == "SUN,TUE,THU" and fixed.start_time == "08:00"
    # No teacher/room clash introduced against the fixed section.
    kinds = {c.kind for c in tt.section_conflicts(tid)}
    assert "teacher" not in kinds and "room" not in kinds


# -- capacity race: concurrent enrollments must not overfill a section -----

def test_concurrent_enroll_respects_capacity(tmp_path):
    """Two threads enrolling different students into a capacity-1 section at
    the same time: exactly one succeeds, the other hits CapacityError, and the
    section never overfills. Guards the BEGIN IMMEDIATE transaction in
    enroll_student against the check-then-insert race."""
    import threading

    from database import get_connection, initialize_database
    from course_service import CourseService
    from major_service import MajorService
    from section_service import SectionService
    from student_service import StudentService
    from term_service import TermService
    from exceptions import CapacityError

    db_path = tmp_path / "conc.db"
    setup = get_connection(db_path)
    initialize_database(setup)
    term = TermService(setup).add_term("Fall", "2030-09-01", "2030-12-20", name_ar="الأول")
    cs = MajorService(setup).add_major("CS", "Computer Science", "علوم الحاسب", 120)
    course = CourseService(setup).add_course("CS101", "Intro", 3, title_ar="مقدمة",
                                             major_id=cs.major_id)
    sec = SectionService(setup).add_section(course.course_id, term.term_id, "01",
                                            gender="male", capacity=1)
    students = StudentService(setup)
    s1 = students.add_student("A", "One", "a1@s.edu", national_id="1111111111",
                              gender="male", major_id=cs.major_id)
    s2 = students.add_student("B", "Two", "b2@s.edu", national_id="2222222222",
                              gender="male", major_id=cs.major_id)
    setup.close()

    results = {}
    barrier = threading.Barrier(2)

    def worker(student_id, key):
        conn = get_connection(db_path)
        try:
            barrier.wait()  # release both threads together
            EnrollmentService(conn).enroll_student(student_id, sec.section_id)
            results[key] = "enrolled"
        except CapacityError:
            results[key] = "capacity"
        finally:
            conn.close()

    threads = [
        threading.Thread(target=worker, args=(s1.student_id, "t1")),
        threading.Thread(target=worker, args=(s2.student_id, "t2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == ["capacity", "enrolled"]

    check = get_connection(db_path)
    count = check.execute(
        "SELECT COUNT(*) AS c FROM enrollments WHERE section_id = ?",
        (sec.section_id,),
    ).fetchone()["c"]
    check.close()
    assert count == 1


# -- LMS courses (الدورات التعليمية) --------------------------------------

def test_lms_course_lifecycle(conn):
    from lms_service import LMSService
    from exceptions import DuplicateError
    svc = LMSService(conn)
    c = svc.add_course(title="Python Basics", title_ar="أساسيات بايثون",
                       code="lms1", category="Programming")
    assert c.status == "draft" and c.code == "LMS1"
    assert c.name("ar") == "أساسيات بايثون" and c.name("en") == "Python Basics"
    assert svc.count() == 1

    svc.set_status(c.lms_course_id, "published")
    assert svc.get_course(c.lms_course_id).status == "published"
    assert len(svc.list_courses(status="published")) == 1
    assert len(svc.list_courses(status="draft")) == 0

    # validation + uniqueness
    with pytest.raises(ValidationError):
        svc.add_course(title="   ")
    with pytest.raises(ValidationError):
        svc.set_status(c.lms_course_id, "bogus")
    with pytest.raises(DuplicateError):
        svc.add_course(title="Other", code="lms1")


# -- Training track: trainees + paid enrollment + completion --------------

def test_training_track_flow(conn):
    from lms_service import LMSService
    from trainee_service import TraineeService
    from lms_enrollment_service import LMSEnrollmentService
    from exceptions import DuplicateError

    lms = LMSService(conn)
    course = lms.add_course(title="Bootcamp", price=300, delivery_mode="hybrid",
                            status="published")
    lms.add_lesson(course.lms_course_id, title="Intro", body="hello")
    assert len(lms.list_lessons(course.lms_course_id)) == 1

    tr = TraineeService(conn)
    t = tr.register(full_name="Sara", email="Sara@X.com", password="secret12")
    assert tr.authenticate("sara@x.com", "secret12").trainee_id == t.trainee_id
    assert tr.authenticate("sara@x.com", "wrong") is None
    with pytest.raises(DuplicateError):
        tr.register(full_name="Dup", email="sara@x.com", password="secret12")

    enr = LMSEnrollmentService(conn)
    e = enr.enroll(t.trainee_id, course.lms_course_id)
    assert e.payment_status == "pending" and e.amount == 300
    with pytest.raises(DuplicateError):
        enr.enroll(t.trainee_id, course.lms_course_id)
    # cannot complete before payment is confirmed
    with pytest.raises(ValidationError):
        enr.complete(e.lms_enrollment_id)
    enr.mark_paid(e.lms_enrollment_id)
    assert enr.complete(e.lms_enrollment_id).is_completed


def test_free_training_course_opens_immediately(conn):
    from lms_service import LMSService
    from trainee_service import TraineeService
    from lms_enrollment_service import LMSEnrollmentService
    course = LMSService(conn).add_course(title="Free", price=0, status="published")
    t = TraineeService(conn).register(full_name="A", email="a@b.com", password="secret12")
    e = LMSEnrollmentService(conn).enroll(t.trainee_id, course.lms_course_id)
    assert e.payment_status == "paid"


def test_cannot_enroll_in_unpublished_course(conn):
    from lms_service import LMSService
    from trainee_service import TraineeService
    from lms_enrollment_service import LMSEnrollmentService
    course = LMSService(conn).add_course(title="Draft", price=100, status="draft")
    t = TraineeService(conn).register(full_name="A", email="a@b.com", password="secret12")
    with pytest.raises(ValidationError):
        LMSEnrollmentService(conn).enroll(t.trainee_id, course.lms_course_id)
