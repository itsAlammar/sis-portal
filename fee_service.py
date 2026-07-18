"""Business logic for tuition/fee assessment and payments."""

import sqlite3
from datetime import date
from typing import List, Optional

from exceptions import NotFoundError, PaymentError, ValidationError
from models import Fee, Payment


class FeeService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def assess_fee(
        self, student_id: int, fee_type: str, amount: float,
        term_id: Optional[int] = None, due_date: Optional[str] = None,
    ) -> Fee:
        if amount <= 0:
            raise ValidationError("Fee amount must be positive.")
        if not fee_type.strip():
            raise ValidationError("Fee type is required.")
        created_at = date.today().isoformat()
        cur = self.conn.execute(
            """INSERT INTO fees (student_id, term_id, fee_type, amount, due_date, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (student_id, term_id, fee_type.strip(), amount, due_date, created_at),
        )
        self.conn.commit()
        return self.get_fee(cur.lastrowid)

    def get_fee(self, fee_id: int) -> Fee:
        row = self.conn.execute("SELECT * FROM fees WHERE fee_id = ?", (fee_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No fee with id {fee_id}.")
        return Fee.from_row(row)

    def list_fees_for_student(self, student_id: int) -> List[Fee]:
        rows = self.conn.execute(
            "SELECT * FROM fees WHERE student_id = ? ORDER BY created_at", (student_id,)
        ).fetchall()
        return [Fee.from_row(r) for r in rows]

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
        remaining = fee.amount - already_paid
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
        new_status = "paid" if fee.amount - new_total <= 0.01 else "partial"
        self.conn.execute("UPDATE fees SET status = ? WHERE fee_id = ?", (new_status, fee_id))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM payments WHERE payment_id = ?", (cur.lastrowid,)
        ).fetchone()
        return Payment.from_row(row)

    def get_student_balance(self, student_id: int) -> float:
        fees = self.list_fees_for_student(student_id)
        total_owed = sum(f.amount for f in fees if f.status != "waived")
        total_paid = sum(self.get_total_paid(f.fee_id) for f in fees if f.status != "waived")
        return round(total_owed - total_paid, 2)

    def get_fee_statement(self, student_id: int) -> List[dict]:
        statement = []
        for fee in self.list_fees_for_student(student_id):
            paid = self.get_total_paid(fee.fee_id)
            balance = 0.0 if fee.status == "waived" else round(fee.amount - paid, 2)
            statement.append({"fee": fee, "paid": paid, "balance": balance})
        return statement

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
