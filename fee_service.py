"""Financial module: fee assessment, per-course billing, registration
fees with non-Saudi VAT, payments, waivers, and balances.

Rules implemented:
- Each course has a price; enrolling bills a per-course "Tuition" fee.
- A registration fee (amount set by admin in app_settings) is charged
  once per term. VAT is added to the registration fee ONLY for non-Saudi
  students, at the admin-configured rate.
- Payments accept partial amounts; a fee's total is amount + tax_amount.
"""

import sqlite3
from datetime import date
from typing import List, Optional

from database import get_setting
from exceptions import NotFoundError, PaymentError, ValidationError
from models import Fee, Payment


class FeeService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- assessment -------------------------------------------------------
    def assess_fee(
        self, student_id: int, fee_type: str, amount: float,
        term_id: Optional[int] = None, course_id: Optional[int] = None,
        tax_amount: float = 0, due_date: Optional[str] = None,
    ) -> Fee:
        if amount < 0:
            raise ValidationError("Fee amount cannot be negative.")
        if not fee_type.strip():
            raise ValidationError("Fee type is required.")
        cur = self.conn.execute(
            """INSERT INTO fees (student_id, term_id, course_id, fee_type, amount,
                                  tax_amount, due_date, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (student_id, term_id, course_id, fee_type.strip(), amount, tax_amount,
             due_date, date.today().isoformat()),
        )
        self.conn.commit()
        return self.get_fee(cur.lastrowid)

    def bill_course(self, student_id: int, course_id: int, term_id: int,
                    due_date: Optional[str] = None) -> Optional[Fee]:
        """Charge a course's price as tuition. Skips if already billed for
        this student+course+term, and skips zero-price courses."""
        course = self.conn.execute(
            "SELECT course_code, price FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        if course is None or (course["price"] or 0) <= 0:
            return None
        existing = self.conn.execute(
            """SELECT 1 FROM fees WHERE student_id = ? AND course_id = ? AND term_id = ?
               AND fee_type = 'Tuition' AND status != 'waived'""",
            (student_id, course_id, term_id),
        ).fetchone()
        if existing:
            return None
        return self.assess_fee(student_id, "Tuition", course["price"],
                               term_id=term_id, course_id=course_id, due_date=due_date)

    def charge_registration_fee(self, student_id: int, term_id: int,
                                due_date: Optional[str] = None) -> Optional[Fee]:
        """Charge the once-per-term registration fee. VAT is added only for
        non-Saudi students, on this fee only."""
        already = self.conn.execute(
            """SELECT 1 FROM fees WHERE student_id = ? AND term_id = ?
               AND fee_type = 'Registration' AND status != 'waived'""",
            (student_id, term_id),
        ).fetchone()
        if already:
            return None
        amount = float(get_setting(self.conn, "registration_fee", "0") or 0)
        if amount <= 0:
            return None
        student = self.conn.execute(
            "SELECT nationality FROM students WHERE student_id = ?", (student_id,)
        ).fetchone()
        is_saudi = (student and (student["nationality"] or "").strip().lower()
                    in ("saudi", "سعودي", "سعودية"))
        tax = 0.0
        if not is_saudi:
            vat_rate = float(get_setting(self.conn, "vat_rate", "0") or 0)
            tax = round(amount * vat_rate / 100, 2)
        return self.assess_fee(student_id, "Registration", amount, term_id=term_id,
                               tax_amount=tax, due_date=due_date)

    # -- reads ------------------------------------------------------------
    def get_fee(self, fee_id: int) -> Fee:
        row = self.conn.execute("SELECT * FROM fees WHERE fee_id = ?", (fee_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No fee with id {fee_id}.")
        return Fee.from_row(row)

    def list_fees_for_student(self, student_id: int) -> List[Fee]:
        rows = self.conn.execute(
            "SELECT * FROM fees WHERE student_id = ? ORDER BY created_at, fee_id",
            (student_id,),
        ).fetchall()
        return [Fee.from_row(r) for r in rows]

    def get_payment(self, payment_id: int) -> sqlite3.Row:
        """One payment joined with its fee (incl. the fee's owner) for the
        receipt: amount, date, method, fee type/course and student_id."""
        row = self.conn.execute(
            """SELECT p.*, f.student_id, f.fee_type, f.amount AS fee_amount,
                      f.tax_amount, f.course_id, f.term_id, f.status AS fee_status
               FROM payments p JOIN fees f ON f.fee_id = p.fee_id
               WHERE p.payment_id = ?""",
            (payment_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"No payment with id {payment_id}.")
        return row

    def list_payments_for_student(self, student_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            """SELECT p.payment_id, p.payment_date, p.amount_paid, p.payment_method,
                      f.fee_type, c.course_code
               FROM payments p
               JOIN fees f ON f.fee_id = p.fee_id
               LEFT JOIN courses c ON c.course_id = f.course_id
               WHERE f.student_id = ?
               ORDER BY p.payment_date DESC, p.payment_id DESC""",
            (student_id,),
        ).fetchall()

    def get_total_paid(self, fee_id: int) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM payments WHERE fee_id = ?",
            (fee_id,),
        ).fetchone()
        return row["total"]

    def record_payment(
        self, fee_id: int, amount_paid: float, payment_method: str = "",
        reference_number: str = "", payment_date: Optional[str] = None,
    ) -> Payment:
        fee = self.get_fee(fee_id)
        if fee.status == "waived":
            raise PaymentError("This fee has been waived; no payment is owed.")
        if amount_paid <= 0:
            raise PaymentError("Payment amount must be positive.")
        already_paid = self.get_total_paid(fee_id)
        remaining = fee.total - already_paid
        if amount_paid - remaining > 0.01:
            raise PaymentError(
                f"Payment of {amount_paid:.2f} exceeds remaining balance of {remaining:.2f}."
            )
        payment_date = payment_date or date.today().isoformat()
        cur = self.conn.execute(
            """INSERT INTO payments (fee_id, amount_paid, payment_date, payment_method, reference_number)
               VALUES (?, ?, ?, ?, ?)""",
            (fee_id, amount_paid, payment_date, payment_method, reference_number),
        )
        new_total = already_paid + amount_paid
        new_status = "paid" if fee.total - new_total <= 0.01 else "partial"
        self.conn.execute("UPDATE fees SET status = ? WHERE fee_id = ?", (new_status, fee_id))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM payments WHERE payment_id = ?", (cur.lastrowid,)
        ).fetchone()
        return Payment.from_row(row)

    def get_student_balance(self, student_id: int) -> float:
        fees = self.list_fees_for_student(student_id)
        owed = sum(f.total for f in fees if f.status != "waived")
        paid = sum(self.get_total_paid(f.fee_id) for f in fees if f.status != "waived")
        return round(owed - paid, 2)

    def get_fee_statement(self, student_id: int) -> List[dict]:
        """Itemized statement; each line notes the related course code
        (for the per-course billing detail on the payment screen)."""
        statement = []
        for fee in self.list_fees_for_student(student_id):
            paid = self.get_total_paid(fee.fee_id)
            balance = 0.0 if fee.status == "waived" else round(fee.total - paid, 2)
            course_code = None
            if fee.course_id:
                row = self.conn.execute(
                    "SELECT course_code FROM courses WHERE course_id = ?", (fee.course_id,)
                ).fetchone()
                course_code = row["course_code"] if row else None
            statement.append({"fee": fee, "paid": paid, "balance": balance,
                              "course_code": course_code})
        return statement

    _OUTSTANDING_WHERE = """
        FROM fees f
        JOIN students s ON s.student_id = f.student_id
        LEFT JOIN courses c ON c.course_id = f.course_id
        LEFT JOIN terms t ON t.term_id = f.term_id
        WHERE f.status != 'waived'
          AND (f.amount + f.tax_amount)
              - COALESCE((SELECT SUM(p.amount_paid) FROM payments p
                          WHERE p.fee_id = f.fee_id), 0) > 0.005
          AND (? = '' OR s.student_number LIKE ? OR s.name_ar LIKE ?
               OR (s.first_name || ' ' || s.last_name) LIKE ?)
    """

    def count_outstanding(self, q: str = "") -> int:
        q = q.strip()
        like = f"%{q}%"
        return self.conn.execute(
            "SELECT COUNT(*) AS c " + self._OUTSTANDING_WHERE, (q, like, like, like)
        ).fetchone()["c"]

    def list_outstanding(self, q: str = "", limit: int = 50, offset: int = 0) -> List[sqlite3.Row]:
        """Unpaid / partially paid invoices across all students, newest first,
        with student identity, course code, term name and paid-so-far."""
        q = q.strip()
        like = f"%{q}%"
        return self.conn.execute(
            """SELECT f.fee_id, f.created_at, f.fee_type, f.amount, f.tax_amount,
                      s.student_id, s.student_number,
                      s.first_name || ' ' || s.last_name AS student_name,
                      s.name_ar AS student_name_ar,
                      c.course_code, t.name AS term_name, t.name_ar AS term_name_ar,
                      COALESCE((SELECT SUM(p.amount_paid) FROM payments p
                                WHERE p.fee_id = f.fee_id), 0) AS paid
            """ + self._OUTSTANDING_WHERE +
            " ORDER BY f.created_at DESC, f.fee_id DESC LIMIT ? OFFSET ?",
            (q, like, like, like, limit, offset),
        ).fetchall()

    def waive_fee(self, fee_id: int, reason: str = "") -> Fee:
        self.get_fee(fee_id)
        self.conn.execute(
            "UPDATE fees SET status = 'waived', waived_reason = ? WHERE fee_id = ?",
            (reason.strip() or None, fee_id),
        )
        self.conn.commit()
        return self.get_fee(fee_id)

    def mark_overdue_fees(self, as_of: Optional[str] = None) -> int:
        as_of = as_of or date.today().isoformat()
        cur = self.conn.execute(
            """UPDATE fees SET status = 'overdue'
               WHERE status = 'pending' AND due_date IS NOT NULL AND due_date < ?""",
            (as_of,),
        )
        self.conn.commit()
        return cur.rowcount
