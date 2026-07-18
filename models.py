"""Lightweight dataclasses representing rows from the database.

These are read-only views built from sqlite3.Row objects; writes always go
through the service layer so business rules stay in one place.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Department:
    department_id: int
    code: str
    name: str

    @classmethod
    def from_row(cls, row):
        return cls(row["department_id"], row["code"], row["name"])


@dataclass
class Student:
    student_id: int
    student_number: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    date_of_birth: Optional[str]
    gender: Optional[str]
    program: Optional[str]
    department_id: Optional[int]
    enrollment_date: str
    status: str
    created_at: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def from_row(cls, row):
        return cls(
            row["student_id"], row["student_number"], row["first_name"],
            row["last_name"], row["email"], row["phone"], row["date_of_birth"],
            row["gender"], row["program"], row["department_id"],
            row["enrollment_date"], row["status"], row["created_at"],
        )


@dataclass
class Teacher:
    teacher_id: int
    employee_number: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    department_id: Optional[int]
    title: Optional[str]
    hire_date: Optional[str]
    status: str
    created_at: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def from_row(cls, row):
        return cls(
            row["teacher_id"], row["employee_number"], row["first_name"],
            row["last_name"], row["email"], row["phone"], row["department_id"],
            row["title"], row["hire_date"], row["status"], row["created_at"],
        )


@dataclass
class Course:
    course_id: int
    course_code: str
    title: str
    credit_hours: int
    department_id: Optional[int]
    description: Optional[str]
    status: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["course_id"], row["course_code"], row["title"],
            row["credit_hours"], row["department_id"], row["description"],
            row["status"],
        )


@dataclass
class Term:
    term_id: int
    name: str
    start_date: str
    end_date: str
    is_current: bool
    add_deadline: Optional[str] = None
    drop_deadline: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return cls(
            row["term_id"], row["name"], row["start_date"], row["end_date"],
            bool(row["is_current"]), row["add_deadline"], row["drop_deadline"],
        )


@dataclass
class Section:
    section_id: int
    course_id: int
    term_id: int
    section_number: str
    teacher_id: Optional[int]
    room: Optional[str]
    days: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    capacity: int
    status: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["section_id"], row["course_id"], row["term_id"],
            row["section_number"], row["teacher_id"], row["room"],
            row["days"], row["start_time"], row["end_time"],
            row["capacity"], row["status"],
        )


@dataclass
class Enrollment:
    enrollment_id: int
    student_id: int
    section_id: int
    enrollment_date: str
    status: str
    grade: Optional[str]
    grade_points: Optional[float]

    @classmethod
    def from_row(cls, row):
        return cls(
            row["enrollment_id"], row["student_id"], row["section_id"],
            row["enrollment_date"], row["status"], row["grade"],
            row["grade_points"],
        )


@dataclass
class Fee:
    fee_id: int
    student_id: int
    term_id: Optional[int]
    fee_type: str
    amount: float
    due_date: Optional[str]
    status: str
    created_at: str
    waived_reason: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return cls(
            row["fee_id"], row["student_id"], row["term_id"], row["fee_type"],
            row["amount"], row["due_date"], row["status"], row["created_at"],
            row["waived_reason"],
        )


@dataclass
class Payment:
    payment_id: int
    fee_id: int
    amount_paid: float
    payment_date: str
    payment_method: Optional[str]
    reference_number: Optional[str]

    @classmethod
    def from_row(cls, row):
        return cls(
            row["payment_id"], row["fee_id"], row["amount_paid"],
            row["payment_date"], row["payment_method"], row["reference_number"],
        )


@dataclass
class User:
    user_id: int
    username: str
    password_hash: str
    role: str            # admin, registrar, teacher
    teacher_id: Optional[int]
    status: str          # active, disabled
    created_at: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["user_id"], row["username"], row["password_hash"], row["role"],
            row["teacher_id"], row["status"], row["created_at"],
        )


@dataclass
class WaitlistEntry:
    waitlist_id: int
    student_id: int
    section_id: int
    joined_at: str
    status: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["waitlist_id"], row["student_id"], row["section_id"],
            row["joined_at"], row["status"],
        )
