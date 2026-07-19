"""Lightweight dataclasses representing rows from the database.

Read-only views built from sqlite3.Row objects; writes always go through
the service layer so business rules stay in one place. `from_row` uses
`row.keys()` tolerantly so partial/joined rows don't crash.
"""

from dataclasses import dataclass
from typing import Optional


def _g(row, key, default=None):
    """Safe column access for rows that may not include every column."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


@dataclass
class Department:
    department_id: int
    code: str
    name: str
    name_ar: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return cls(row["department_id"], row["code"], row["name"], _g(row, "name_ar"))


@dataclass
class Major:
    major_id: int
    code: str
    name_en: str
    name_ar: str
    department_id: Optional[int]
    required_credit_hours: int
    gender: str
    status: str

    def name(self, locale="en"):
        return self.name_ar if locale == "ar" else self.name_en

    @classmethod
    def from_row(cls, row):
        return cls(
            row["major_id"], row["code"], row["name_en"], row["name_ar"],
            _g(row, "department_id"), _g(row, "required_credit_hours", 120),
            _g(row, "gender", "any"), _g(row, "status", "active"),
        )


@dataclass
class Student:
    student_id: int
    student_number: str
    national_id: Optional[str]
    first_name: str
    second_name: Optional[str]
    third_name: Optional[str]
    last_name: str
    name_ar: Optional[str]
    email: str
    phone: Optional[str]
    date_of_birth: Optional[str]
    gender: str
    nationality: str
    program: Optional[str]
    major_id: Optional[int]
    advisor_id: Optional[int]
    department_id: Optional[int]
    enrollment_date: str
    status: str
    created_at: str

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.second_name, self.third_name, self.last_name]
        return " ".join(p for p in parts if p)

    def display_name(self, locale="en") -> str:
        if locale == "ar" and self.name_ar:
            return self.name_ar
        return self.full_name

    @property
    def is_saudi(self) -> bool:
        return (self.nationality or "").strip().lower() in ("saudi", "سعودي", "سعودية")

    @classmethod
    def from_row(cls, row):
        return cls(
            row["student_id"], row["student_number"], _g(row, "national_id"),
            row["first_name"], _g(row, "second_name"), _g(row, "third_name"),
            row["last_name"], _g(row, "name_ar"), row["email"], _g(row, "phone"),
            _g(row, "date_of_birth"), _g(row, "gender", "male"),
            _g(row, "nationality", "Saudi"), _g(row, "program"), _g(row, "major_id"),
            _g(row, "advisor_id"), _g(row, "department_id"), row["enrollment_date"],
            row["status"], row["created_at"],
        )


@dataclass
class Teacher:
    teacher_id: int
    employee_number: str
    first_name: str
    last_name: str
    name_ar: Optional[str]
    email: str
    phone: Optional[str]
    gender: str
    department_id: Optional[int]
    title: Optional[str]
    hire_date: Optional[str]
    status: str
    created_at: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def display_name(self, locale="en") -> str:
        if locale == "ar" and self.name_ar:
            return self.name_ar
        return self.full_name

    @classmethod
    def from_row(cls, row):
        return cls(
            row["teacher_id"], row["employee_number"], row["first_name"],
            row["last_name"], _g(row, "name_ar"), row["email"], _g(row, "phone"),
            _g(row, "gender", "male"), _g(row, "department_id"), _g(row, "title"),
            _g(row, "hire_date"), row["status"], row["created_at"],
        )


@dataclass
class Course:
    course_id: int
    course_code: str
    title: str
    title_ar: Optional[str]
    credit_hours: int
    price: float
    department_id: Optional[int]
    major_id: Optional[int]
    description: Optional[str]
    status: str

    def display_title(self, locale="en") -> str:
        if locale == "ar" and self.title_ar:
            return self.title_ar
        return self.title

    @classmethod
    def from_row(cls, row):
        return cls(
            row["course_id"], row["course_code"], row["title"], _g(row, "title_ar"),
            row["credit_hours"], _g(row, "price", 0), _g(row, "department_id"),
            _g(row, "major_id"), _g(row, "description"), _g(row, "status", "active"),
        )


@dataclass
class AcademicYear:
    year_id: int
    name: str
    name_ar: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return cls(row["year_id"], row["name"], _g(row, "name_ar"))


@dataclass
class Term:
    term_id: int
    name: str
    name_ar: Optional[str]
    academic_year_id: Optional[int]
    kind: str
    start_date: str
    end_date: str
    is_current: bool
    add_deadline: Optional[str] = None
    drop_deadline: Optional[str] = None
    grades_deadline: Optional[str] = None

    def display_name(self, locale="en") -> str:
        if locale == "ar" and self.name_ar:
            return self.name_ar
        return self.name

    @classmethod
    def from_row(cls, row):
        return cls(
            row["term_id"], row["name"], _g(row, "name_ar"), _g(row, "academic_year_id"),
            _g(row, "kind", "regular"), row["start_date"], row["end_date"],
            bool(row["is_current"]), _g(row, "add_deadline"), _g(row, "drop_deadline"),
            _g(row, "grades_deadline"),
        )


@dataclass
class Section:
    section_id: int
    course_id: int
    term_id: int
    section_number: str
    teacher_id: Optional[int]
    gender: str
    room: Optional[str]
    days: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    capacity: int
    status: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["section_id"], row["course_id"], row["term_id"], row["section_number"],
            _g(row, "teacher_id"), _g(row, "gender", "male"), _g(row, "room"),
            _g(row, "days"), _g(row, "start_time"), _g(row, "end_time"),
            row["capacity"], row["status"],
        )


@dataclass
class Enrollment:
    enrollment_id: int
    student_id: int
    section_id: int
    enrollment_date: str
    status: str
    numeric_mark: Optional[float]
    coursework_mark: Optional[float]
    final_mark: Optional[float]
    grade: Optional[str]
    grade_points: Optional[float]

    @classmethod
    def from_row(cls, row):
        return cls(
            row["enrollment_id"], row["student_id"], row["section_id"],
            row["enrollment_date"], row["status"], _g(row, "numeric_mark"),
            _g(row, "coursework_mark"), _g(row, "final_mark"),
            row["grade"], row["grade_points"],
        )


@dataclass
class AdmissionApplication:
    application_id: int
    national_id: str
    first_name: str
    second_name: str
    third_name: str
    last_name: str
    name_ar: str
    email: str
    phone: str
    date_of_birth: str
    gender: str
    nationality: str
    major_id: Optional[int]
    status: str
    student_id: Optional[int]
    review_note: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    created_at: str

    @property
    def full_name_en(self) -> str:
        return " ".join(p for p in [self.first_name, self.second_name,
                                     self.third_name, self.last_name] if p)

    @classmethod
    def from_row(cls, row):
        return cls(
            row["application_id"], row["national_id"], row["first_name"],
            row["second_name"], row["third_name"], row["last_name"], row["name_ar"],
            row["email"], row["phone"], row["date_of_birth"], row["gender"],
            row["nationality"], _g(row, "major_id"), row["status"], _g(row, "student_id"),
            _g(row, "review_note"), _g(row, "reviewed_by"), _g(row, "reviewed_at"),
            row["created_at"],
        )


@dataclass
class Fee:
    fee_id: int
    student_id: int
    term_id: Optional[int]
    course_id: Optional[int]
    fee_type: str
    amount: float
    tax_amount: float
    due_date: Optional[str]
    status: str
    created_at: str
    waived_reason: Optional[str] = None

    @property
    def total(self) -> float:
        return round(self.amount + self.tax_amount, 2)

    @classmethod
    def from_row(cls, row):
        return cls(
            row["fee_id"], row["student_id"], _g(row, "term_id"), _g(row, "course_id"),
            row["fee_type"], row["amount"], _g(row, "tax_amount", 0), _g(row, "due_date"),
            row["status"], row["created_at"], _g(row, "waived_reason"),
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
            row["payment_date"], _g(row, "payment_method"), _g(row, "reference_number"),
        )


@dataclass
class ServiceRequest:
    request_id: int
    student_id: int
    kind: str
    details: Optional[str]
    status: str
    review_note: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    created_at: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["request_id"], row["student_id"], row["kind"], _g(row, "details"),
            row["status"], _g(row, "review_note"), _g(row, "reviewed_by"),
            _g(row, "reviewed_at"), row["created_at"],
        )


@dataclass
class User:
    user_id: int
    username: str
    password_hash: str
    role: str
    teacher_id: Optional[int]
    status: str
    created_at: str

    @classmethod
    def from_row(cls, row):
        return cls(
            row["user_id"], row["username"], row["password_hash"], row["role"],
            _g(row, "teacher_id"), row["status"], row["created_at"],
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
