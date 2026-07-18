"""Business-rule tests for the service layer."""

import pytest

from enrollment_service import EnrollmentService
from grading_service import GradingService
from gpa_service import GPAService
from fee_service import FeeService
from term_service import TermService
from waitlist_service import WaitlistService
from exceptions import (
    DeadlineError, DuplicateEnrollmentError, PaymentError,
    PrerequisiteError, ValidationError,
)


def test_enroll_and_duplicate_rejected(seeded):
    enrollments = EnrollmentService(seeded["conn"])
    enrollments.enroll_student(seeded["alice"].student_id, seeded["sec101"].section_id)
    with pytest.raises(DuplicateEnrollmentError):
        enrollments.enroll_student(seeded["alice"].student_id, seeded["sec101"].section_id)


def test_capacity_overflow_goes_to_waitlist(seeded):
    conn = seeded["conn"]
    enrollments, waitlist = EnrollmentService(conn), WaitlistService(conn)
    sec = seeded["sec101"]  # capacity 2

    enrollments.enroll_student(seeded["alice"].student_id, sec.section_id)
    enrollments.enroll_student(seeded["bob"].student_id, sec.section_id)
    status, _ = enrollments.enroll_or_waitlist(seeded["carol"].student_id, sec.section_id)

    assert status == "waitlisted"
    assert waitlist.get_position(seeded["carol"].student_id, sec.section_id) == 1


def test_drop_promotes_from_waitlist(seeded):
    conn = seeded["conn"]
    enrollments = EnrollmentService(conn)
    sec = seeded["sec101"]

    enrollments.enroll_student(seeded["alice"].student_id, sec.section_id)
    enrollments.enroll_student(seeded["bob"].student_id, sec.section_id)
    enrollments.enroll_or_waitlist(seeded["carol"].student_id, sec.section_id)

    enrollments.drop_student(seeded["alice"].student_id, sec.section_id)

    rows = enrollments.list_student_enrollments(seeded["carol"].student_id)
    assert any(r["section_id"] == sec.section_id and r["status"] == "enrolled" for r in rows)


def test_prerequisite_blocks_until_completed(seeded):
    conn = seeded["conn"]
    enrollments, grading = EnrollmentService(conn), GradingService(conn)
    alice = seeded["alice"]

    with pytest.raises(PrerequisiteError):
        enrollments.enroll_student(alice.student_id, seeded["sec102"].section_id)

    enrollments.enroll_student(alice.student_id, seeded["sec101"].section_id)
    grading.assign_grade_by_pair(alice.student_id, seeded["sec101"].section_id, "B+")
    enrollment = enrollments.enroll_student(alice.student_id, seeded["sec102"].section_id)
    assert enrollment.status == "enrolled"


def test_add_deadline_enforced(seeded):
    conn = seeded["conn"]
    TermService(conn).update_term(seeded["term"].term_id, add_deadline="2030-09-10")
    with pytest.raises(DeadlineError):
        EnrollmentService(conn).enroll_student(
            seeded["alice"].student_id, seeded["sec101"].section_id, as_of="2030-09-11"
        )


def test_drop_deadline_enforced_but_overridable(seeded):
    conn = seeded["conn"]
    enrollments = EnrollmentService(conn)
    enrollments.enroll_student(seeded["alice"].student_id, seeded["sec101"].section_id)
    TermService(conn).update_term(seeded["term"].term_id, drop_deadline="2030-10-01")

    with pytest.raises(DeadlineError):
        enrollments.drop_student(seeded["alice"].student_id, seeded["sec101"].section_id,
                                 as_of="2030-10-02")
    dropped = enrollments.drop_student(seeded["alice"].student_id, seeded["sec101"].section_id,
                                       as_of="2030-10-02", override_deadline=True)
    assert dropped.status == "dropped"


def test_gpa_calculation(seeded):
    conn = seeded["conn"]
    enrollments, grading = EnrollmentService(conn), GradingService(conn)
    alice = seeded["alice"]

    enrollments.enroll_student(alice.student_id, seeded["sec101"].section_id)
    grading.assign_grade_by_pair(alice.student_id, seeded["sec101"].section_id, "A")

    assert GPAService(conn).calculate_cumulative_gpa(alice.student_id) == pytest.approx(4.0)


def test_fee_lifecycle_and_overpayment_blocked(seeded):
    conn = seeded["conn"]
    fees = FeeService(conn)
    alice = seeded["alice"]

    fee = fees.assess_fee(alice.student_id, "Tuition", 1000)
    with pytest.raises(PaymentError):
        fees.record_payment(fee.fee_id, 1500)

    fees.record_payment(fee.fee_id, 400)
    assert fees.get_fee(fee.fee_id).status == "partial"
    fees.record_payment(fee.fee_id, 600)
    assert fees.get_fee(fee.fee_id).status == "paid"
    assert fees.get_student_balance(alice.student_id) == 0


def test_waived_fee_owes_nothing_and_rejects_payment(seeded):
    conn = seeded["conn"]
    fees = FeeService(conn)
    alice = seeded["alice"]

    fee = fees.assess_fee(alice.student_id, "Lab fee", 250)
    fees.waive_fee(fee.fee_id, reason="Scholarship")

    assert fees.get_fee(fee.fee_id).status == "waived"
    assert fees.get_student_balance(alice.student_id) == 0
    with pytest.raises(PaymentError):
        fees.record_payment(fee.fee_id, 50)


def test_invalid_grade_rejected(seeded):
    conn = seeded["conn"]
    EnrollmentService(conn).enroll_student(seeded["alice"].student_id, seeded["sec101"].section_id)
    with pytest.raises(ValidationError):
        GradingService(conn).assign_grade_by_pair(
            seeded["alice"].student_id, seeded["sec101"].section_id, "Z"
        )
