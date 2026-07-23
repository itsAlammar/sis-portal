"""Database layer: connection management and schema definition.

SQLite by default (single-file, zero-dependency). Every service uses
plain SQL with `?` placeholders, so migrating to Postgres later is
localized to this module. Set SIS_DB_DIR to relocate the file (e.g. a
mounted volume in Docker / an EBS volume on AWS).
"""

import os
import sqlite3
from pathlib import Path

import db

DB_PATH = Path(os.environ.get("SIS_DB_DIR") or Path(__file__).parent) / "sis.db"

# Saudi 5.0 grade scale: numeric mark (/100) -> letter -> grade points.
# This is the common NCAAA-style scale. Edit here to change the whole
# system's grading; nothing else hardcodes these numbers.
#   letter, grade_points(/5), min_percent, max_percent
GRADE_SCALE = [
    ("A+", 5.00, 95, 100),
    ("A",  4.75, 90, 94),
    ("B+", 4.50, 85, 89),
    ("B",  4.00, 80, 84),
    ("C+", 3.50, 75, 79),
    ("C",  3.00, 70, 74),
    ("D+", 2.50, 65, 69),
    ("D",  2.00, 60, 64),
    ("F",  1.00, 0, 59),
    ("W",  0.00, None, None),  # Withdrawn -- excluded from GPA
    ("I",  0.00, None, None),  # Incomplete -- excluded from GPA
]
GPA_SCALE_MAX = 5.0

# Schema convention for NEW tables added from here on (SQLite's ALTER cannot
# retrofit these onto existing tables without a full rebuild, so existing
# tables keep their current shape):
#   - Add CHECK(...) on bounded-value columns (status/gender/kind), the way
#     `users.role` already does below.
#   - Declare explicit ON DELETE on foreign keys: SET NULL for optional refs
#     (e.g. advisor_id, teacher_id), RESTRICT for required ones. Avoid CASCADE
#     on academic records (dropping a term must not silently delete sections /
#     enrollments).
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS grade_scale (
    letter        TEXT PRIMARY KEY,
    grade_points  REAL NOT NULL,
    min_percent   REAL,
    max_percent   REAL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    name_ar       TEXT
);

CREATE TABLE IF NOT EXISTS majors (
    major_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code                  TEXT UNIQUE NOT NULL,
    name_en               TEXT NOT NULL,
    name_ar               TEXT NOT NULL,
    department_id         INTEGER REFERENCES departments(department_id),
    required_credit_hours INTEGER NOT NULL DEFAULT 120,
    gender                TEXT NOT NULL DEFAULT 'any',   -- male, female, any
    status                TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS teachers (
    teacher_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_number TEXT UNIQUE NOT NULL,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    name_ar         TEXT,
    email           TEXT UNIQUE NOT NULL,
    phone           TEXT,
    gender          TEXT NOT NULL DEFAULT 'male',   -- male, female
    department_id   INTEGER REFERENCES departments(department_id),
    title           TEXT,
    hire_date       TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    student_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number  TEXT UNIQUE NOT NULL,
    national_id     TEXT UNIQUE,                    -- 10 digits
    first_name      TEXT NOT NULL,
    second_name     TEXT,
    third_name      TEXT,
    last_name       TEXT NOT NULL,
    name_ar         TEXT,                           -- full quad name in Arabic
    email           TEXT UNIQUE NOT NULL,
    phone           TEXT,
    date_of_birth   TEXT,
    gender          TEXT NOT NULL DEFAULT 'male',   -- male, female
    nationality     TEXT NOT NULL DEFAULT 'Saudi',
    program         TEXT,
    major_id        INTEGER REFERENCES majors(major_id),
    advisor_id      INTEGER REFERENCES teachers(teacher_id),
    department_id   INTEGER REFERENCES departments(department_id),
    enrollment_date TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    password_hash   TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    course_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code    TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    title_ar       TEXT,
    credit_hours   INTEGER NOT NULL,
    price          REAL NOT NULL DEFAULT 0,
    coursework_max INTEGER NOT NULL DEFAULT 50,   -- coursework portion of the 100 mark; final = remainder
    department_id  INTEGER REFERENCES departments(department_id),
    major_id       INTEGER REFERENCES majors(major_id),
    description    TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS course_teachers (
    course_id  INTEGER NOT NULL REFERENCES courses(course_id),
    teacher_id INTEGER NOT NULL REFERENCES teachers(teacher_id),
    PRIMARY KEY (course_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS course_prerequisites (
    course_id              INTEGER NOT NULL REFERENCES courses(course_id),
    prerequisite_course_id INTEGER NOT NULL REFERENCES courses(course_id),
    group_id               INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (course_id, prerequisite_course_id)
);

CREATE TABLE IF NOT EXISTS curriculum_courses (
    curriculum_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    major_id       INTEGER NOT NULL REFERENCES majors(major_id),
    course_id      INTEGER NOT NULL REFERENCES courses(course_id),
    level          INTEGER NOT NULL DEFAULT 1,        -- suggested level/semester (1..8)
    kind           TEXT NOT NULL DEFAULT 'required',  -- required, elective
    elective_block TEXT,                              -- optional grouping label for electives
    UNIQUE(major_id, course_id)
);

CREATE TABLE IF NOT EXISTS academic_years (
    year_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT UNIQUE NOT NULL,   -- e.g. "2025-2026"
    name_ar   TEXT
);

CREATE TABLE IF NOT EXISTS terms (
    term_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT UNIQUE NOT NULL,
    name_ar          TEXT,
    academic_year_id INTEGER REFERENCES academic_years(year_id),
    kind             TEXT NOT NULL DEFAULT 'regular',  -- regular, summer
    start_date       TEXT NOT NULL,
    end_date         TEXT NOT NULL,
    is_current       INTEGER NOT NULL DEFAULT 0,
    add_deadline     TEXT,
    drop_deadline    TEXT,
    grades_deadline  TEXT    -- after this date grade entry/edit is locked
);

CREATE TABLE IF NOT EXISTS sections (
    section_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id      INTEGER NOT NULL REFERENCES courses(course_id),
    term_id        INTEGER NOT NULL REFERENCES terms(term_id),
    section_number TEXT NOT NULL,
    teacher_id     INTEGER REFERENCES teachers(teacher_id),
    gender         TEXT NOT NULL DEFAULT 'male',   -- male, female (segregated)
    room           TEXT,
    days           TEXT,
    start_time     TEXT,
    end_time       TEXT,
    capacity       INTEGER NOT NULL DEFAULT 30,
    status         TEXT NOT NULL DEFAULT 'open',
    UNIQUE(course_id, term_id, section_number)
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(student_id),
    section_id      INTEGER NOT NULL REFERENCES sections(section_id),
    enrollment_date TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'enrolled',   -- enrolled, dropped, completed
    numeric_mark    REAL,                                -- total /100
    coursework_mark REAL,                                -- optional breakdown: أعمال السنة
    final_mark      REAL,                                -- optional breakdown: الاختبار النهائي
    grade           TEXT REFERENCES grade_scale(letter),
    grade_points    REAL,
    UNIQUE(student_id, section_id)
);

CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id    INTEGER NOT NULL REFERENCES sections(section_id),
    student_id    INTEGER NOT NULL REFERENCES students(student_id),
    date          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'present',  -- present, absent, late, excused
    recorded_by   TEXT,
    UNIQUE(section_id, student_id, date)
);

CREATE TABLE IF NOT EXISTS email_log (
    email_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    to_address TEXT NOT NULL,
    subject    TEXT NOT NULL,
    body       TEXT NOT NULL,
    kind       TEXT,                 -- e.g. admission_acceptance
    status     TEXT NOT NULL,        -- sent, failed, logged (email disabled)
    error      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admission_applications (
    application_id INTEGER PRIMARY KEY AUTOINCREMENT,
    national_id    TEXT NOT NULL,
    first_name     TEXT NOT NULL,
    second_name    TEXT NOT NULL,
    third_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    name_ar        TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT NOT NULL,
    date_of_birth  TEXT NOT NULL,
    gender         TEXT NOT NULL,
    nationality    TEXT NOT NULL,
    major_id       INTEGER REFERENCES majors(major_id),
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending, approved, rejected
    student_id     INTEGER REFERENCES students(student_id),
    review_note    TEXT,
    reviewed_by    TEXT,
    reviewed_at    TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fees (
    fee_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(student_id),
    term_id       INTEGER REFERENCES terms(term_id),
    course_id     INTEGER REFERENCES courses(course_id),   -- per-course billing
    fee_type      TEXT NOT NULL,       -- Tuition, Registration, VAT, ...
    amount        REAL NOT NULL,
    tax_amount    REAL NOT NULL DEFAULT 0,
    due_date      TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, partial, paid, overdue, waived
    waived_reason TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fee_id           INTEGER NOT NULL REFERENCES fees(fee_id),
    amount_paid      REAL NOT NULL,
    payment_date     TEXT NOT NULL,
    payment_method   TEXT,
    reference_number TEXT
);

CREATE TABLE IF NOT EXISTS waitlist (
    waitlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(student_id),
    section_id  INTEGER NOT NULL REFERENCES sections(section_id),
    joined_at   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'waiting',
    UNIQUE(student_id, section_id)
);

CREATE TABLE IF NOT EXISTS service_requests (
    request_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(student_id),
    kind        TEXT NOT NULL,   -- deferral, major_transfer, exam_deferral, equivalency, absence_excuse, other
    section_id  INTEGER REFERENCES sections(section_id),  -- absence_excuse only
    date        TEXT,                                     -- absence_excuse only
    details     TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, rejected
    review_note TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exam_schedule (
    exam_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES sections(section_id),
    kind       TEXT NOT NULL DEFAULT 'final',   -- midterm, final
    date       TEXT NOT NULL,
    start_time TEXT,
    end_time   TEXT,
    room       TEXT,
    UNIQUE(section_id, kind)
);

CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'registrar', 'teacher', 'accounting')),
    teacher_id    INTEGER REFERENCES teachers(teacher_id),
    full_name     TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT,
    entity_id   INTEGER,
    details     TEXT
);

CREATE TABLE IF NOT EXISTS lms_courses (
    lms_course_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT UNIQUE,
    title          TEXT NOT NULL,
    title_ar       TEXT,
    description    TEXT,
    description_ar TEXT,
    category       TEXT,
    teacher_id     INTEGER REFERENCES teachers(teacher_id) ON DELETE SET NULL,
    status         TEXT NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'published', 'archived')),
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_section ON enrollments(section_id);
CREATE INDEX IF NOT EXISTS idx_sections_course ON sections(course_id);
CREATE INDEX IF NOT EXISTS idx_sections_term ON sections(term_id);
CREATE INDEX IF NOT EXISTS idx_fees_student ON fees(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_fee ON payments(fee_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_section ON waitlist(section_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON admission_applications(status);
CREATE INDEX IF NOT EXISTS idx_requests_status ON service_requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_student ON service_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_exams_section ON exam_schedule(section_id);
CREATE INDEX IF NOT EXISTS idx_curriculum_major ON curriculum_courses(major_id);
CREATE INDEX IF NOT EXISTS idx_attendance_section ON attendance(section_id, date);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
"""

# Default admin-controlled settings.
DEFAULT_SETTINGS = {
    "registration_fee": "500",   # flat registration fee (SAR)
    "vat_rate": "15",            # VAT percent, applied to non-Saudi registration fee only
    "institution_name_en": "Academy",
    "institution_name_ar": "الأكاديمية",
    # -- outgoing email (admissions notifications) ------------------------
    "email_enabled": "0",            # 0 = log only, 1 = actually send via SMTP
    "auto_email_on_approval": "1",   # send the acceptance email automatically on approve
    "lms_enabled": "1",              # learning-management module (admin-managed courses)
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "acceptance_subject": "قبولك في {institution} | Your admission to {institution}",
    "acceptance_body": (
        "عزيزي/عزيزتي {name}،\n"
        "نبارك لك قبولك في {institution}.\n"
        "رقمك الجامعي: {student_number}\n"
        "التخصص: {major}\n"
        "كلمة المرور المؤقتة لبوابة الطالب هي رقم هويتك الوطنية.\n\n"
        "Dear {name},\n"
        "Congratulations on your admission to {institution}.\n"
        "University number: {student_number}\n"
        "Major: {major}\n"
        "Your temporary student-portal password is your national ID."
    ),
}


def _column_exists(conn, table, column):
    return any(r["name"] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def _migrate(conn):
    """Forward-compatible column additions for databases created by an
    earlier build. Safe to run every start-up."""
    additions = [
        ("students", "national_id", "TEXT"),
        ("students", "second_name", "TEXT"),
        ("students", "third_name", "TEXT"),
        ("students", "name_ar", "TEXT"),
        ("students", "gender", "TEXT NOT NULL DEFAULT 'male'"),
        ("students", "nationality", "TEXT NOT NULL DEFAULT 'Saudi'"),
        ("students", "major_id", "INTEGER"),
        ("students", "advisor_id", "INTEGER"),
        ("students", "password_hash", "TEXT"),
        ("teachers", "name_ar", "TEXT"),
        ("teachers", "gender", "TEXT NOT NULL DEFAULT 'male'"),
        ("courses", "title_ar", "TEXT"),
        ("courses", "price", "REAL NOT NULL DEFAULT 0"),
        ("courses", "coursework_max", "INTEGER NOT NULL DEFAULT 50"),
        ("courses", "major_id", "INTEGER"),
        ("sections", "gender", "TEXT NOT NULL DEFAULT 'male'"),
        ("terms", "name_ar", "TEXT"),
        ("terms", "academic_year_id", "INTEGER"),
        ("terms", "kind", "TEXT NOT NULL DEFAULT 'regular'"),
        ("terms", "add_deadline", "TEXT"),
        ("terms", "drop_deadline", "TEXT"),
        ("terms", "grades_deadline", "TEXT"),
        ("enrollments", "numeric_mark", "REAL"),
        ("enrollments", "coursework_mark", "REAL"),
        ("enrollments", "final_mark", "REAL"),
        ("fees", "course_id", "INTEGER"),
        ("fees", "tax_amount", "REAL NOT NULL DEFAULT 0"),
        ("fees", "waived_reason", "TEXT"),
        ("users", "full_name", "TEXT"),
        ("service_requests", "section_id", "INTEGER"),
        ("service_requests", "date", "TEXT"),
    ]
    for table, column, coltype in additions:
        if not _column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    conn.commit()


def get_connection(db_path: Path = None):
    """Return a DB connection. Postgres when DATABASE_URL points at it
    (production / AWS RDS), otherwise a local SQLite file. Both expose the
    same sqlite3-style API — see db.py."""
    if db.DIALECT == "postgres":
        return db.connect_postgres()
    conn = sqlite3.connect(db_path if db_path is not None else DB_PATH, timeout=15)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    # Performance tuning (safe with WAL): NORMAL fsync trades a tiny durability
    # window on power loss for far faster writes; the rest reduce disk I/O.
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -16000;")   # ~16MB page cache
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(conn) -> None:
    if db.DIALECT == "postgres":
        conn.executescript(db.to_postgres_schema(SCHEMA))
    else:
        conn.executescript(SCHEMA)
        _migrate(conn)   # forward-add columns for older SQLite files only
    if conn.execute("SELECT COUNT(*) AS c FROM grade_scale").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO grade_scale (letter, grade_points, min_percent, max_percent) "
            "VALUES (?, ?, ?, ?)", GRADE_SCALE,
        )
    upsert = (
        "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT DO NOTHING"
        if db.DIALECT == "postgres"
        else "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)"
    )
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(upsert, (key, value))
    conn.commit()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
