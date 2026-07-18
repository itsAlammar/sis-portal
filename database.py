"""Database layer: connection management and schema definition.

SQLite is used so the whole system runs from a single file with zero
external dependencies. To migrate to Postgres/MySQL later, this is the
only module that needs to change -- every service uses plain SQL with
`?` placeholders.
"""

import os
import sqlite3
from pathlib import Path

# SIS_DB_DIR overrides where sis.db lives (e.g. a mounted volume in Docker);
# by default it sits next to the code, as before.
DB_PATH = Path(os.environ.get("SIS_DB_DIR") or Path(__file__).parent) / "sis.db"

# Standard 4.0 grade scale. Edit here if your institution uses a 5.0 scale
# or different letters -- nothing else in the system needs to change,
# since grade points are always looked up from this table.
GRADE_SCALE = [
    # letter, grade_points, min_percent, max_percent
    ("A",  4.0, 93, 100),
    ("A-", 3.7, 90, 92),
    ("B+", 3.3, 87, 89),
    ("B",  3.0, 83, 86),
    ("B-", 2.7, 80, 82),
    ("C+", 2.3, 77, 79),
    ("C",  2.0, 73, 76),
    ("C-", 1.7, 70, 72),
    ("D+", 1.3, 67, 69),
    ("D",  1.0, 63, 66),
    ("F",  0.0, 0, 62),
    ("W",  0.0, None, None),  # Withdrawn -- excluded from GPA math
    ("I",  0.0, None, None),  # Incomplete -- excluded from GPA math
]

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS grade_scale (
    letter        TEXT PRIMARY KEY,
    grade_points  REAL NOT NULL,
    min_percent   REAL,
    max_percent   REAL
);

CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    student_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number  TEXT UNIQUE NOT NULL,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    phone           TEXT,
    date_of_birth   TEXT,
    gender          TEXT,
    program         TEXT,
    department_id   INTEGER REFERENCES departments(department_id),
    enrollment_date TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    teacher_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_number TEXT UNIQUE NOT NULL,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    phone           TEXT,
    department_id   INTEGER REFERENCES departments(department_id),
    title           TEXT,
    hire_date       TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    course_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code    TEXT UNIQUE NOT NULL,
    title          TEXT NOT NULL,
    credit_hours   INTEGER NOT NULL,
    department_id  INTEGER REFERENCES departments(department_id),
    description    TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS course_prerequisites (
    course_id              INTEGER NOT NULL REFERENCES courses(course_id),
    prerequisite_course_id INTEGER NOT NULL REFERENCES courses(course_id),
    group_id               INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (course_id, prerequisite_course_id)
);

CREATE TABLE IF NOT EXISTS terms (
    term_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    is_current    INTEGER NOT NULL DEFAULT 0,
    add_deadline  TEXT,   -- last date students may register/enroll
    drop_deadline TEXT    -- last date students may drop without penalty
);

CREATE TABLE IF NOT EXISTS sections (
    section_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id      INTEGER NOT NULL REFERENCES courses(course_id),
    term_id        INTEGER NOT NULL REFERENCES terms(term_id),
    section_number TEXT NOT NULL,
    teacher_id     INTEGER REFERENCES teachers(teacher_id),
    room           TEXT,
    days           TEXT,    -- comma-separated: SUN,MON,TUE,WED,THU,FRI,SAT
    start_time     TEXT,    -- "HH:MM" 24h
    end_time       TEXT,    -- "HH:MM" 24h
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
    grade           TEXT REFERENCES grade_scale(letter),
    grade_points    REAL,
    UNIQUE(student_id, section_id)
);

CREATE TABLE IF NOT EXISTS fees (
    fee_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(student_id),
    term_id       INTEGER REFERENCES terms(term_id),
    fee_type      TEXT NOT NULL,
    amount        REAL NOT NULL,
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
    status      TEXT NOT NULL DEFAULT 'waiting',  -- waiting, promoted, cancelled, skipped
    UNIQUE(student_id, section_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'registrar', 'teacher')),
    teacher_id    INTEGER REFERENCES teachers(teacher_id),  -- required when role = teacher
    status        TEXT NOT NULL DEFAULT 'active',           -- active, disabled
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,     -- ISO timestamp
    actor       TEXT NOT NULL,     -- 'staff:username' or 'student:S20250001' or 'system'
    action      TEXT NOT NULL,     -- e.g. grade.assign, fee.waive, enrollment.add
    entity_type TEXT,
    entity_id   INTEGER,
    details     TEXT
);

CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_section ON enrollments(section_id);
CREATE INDEX IF NOT EXISTS idx_sections_course ON sections(course_id);
CREATE INDEX IF NOT EXISTS idx_sections_term ON sections(term_id);
CREATE INDEX IF NOT EXISTS idx_fees_student ON fees(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_fee ON payments(fee_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_section ON waitlist(section_id);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _migrate(conn: sqlite3.Connection) -> None:
    """Safely upgrades a database created by an earlier version of this
    schema. Safe to call every time -- each step checks before acting."""
    simple_column_additions = [
        ("terms", "add_deadline", "TEXT"),
        ("terms", "drop_deadline", "TEXT"),
        ("fees", "waived_reason", "TEXT"),
        ("students", "password_hash", "TEXT"),
    ]
    for table, column, coltype in simple_column_additions:
        if not _column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    # course_prerequisites.group_id needs care: a naive ADD COLUMN with a
    # constant default would silently turn every pre-existing prerequisite
    # into one big "OR" group. Each existing row gets its own group instead,
    # preserving the original "all of these are required" behavior.
    if not _column_exists(conn, "course_prerequisites", "group_id"):
        conn.execute("ALTER TABLE course_prerequisites ADD COLUMN group_id INTEGER")
        rows = conn.execute(
            "SELECT rowid, course_id FROM course_prerequisites ORDER BY course_id, rowid"
        ).fetchall()
        counters = {}
        for row in rows:
            counters[row["course_id"]] = counters.get(row["course_id"], 0) + 1
            conn.execute(
                "UPDATE course_prerequisites SET group_id = ? WHERE rowid = ?",
                (counters[row["course_id"]], row["rowid"]),
            )
        conn.execute("UPDATE course_prerequisites SET group_id = 1 WHERE group_id IS NULL")
    conn.commit()


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    # DB_PATH is looked up at call time (not bound as a default) so tests
    # and tools can repoint it before connecting.
    conn = sqlite3.connect(db_path if db_path is not None else DB_PATH, timeout=15)
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL lets readers proceed while one writer commits; busy_timeout makes
    # concurrent writers wait instead of failing immediately with
    # "database is locked". Enough for a small deployment; move to Postgres
    # for genuinely high concurrency (see README).
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM grade_scale")
    if cur.fetchone()["cnt"] == 0:
        conn.executemany(
            "INSERT INTO grade_scale (letter, grade_points, min_percent, max_percent) "
            "VALUES (?, ?, ?, ?)",
            GRADE_SCALE,
        )
    conn.commit()
