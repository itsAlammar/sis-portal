"""Database engine abstraction: one code path for SQLite (default) and
PostgreSQL (production / AWS RDS).

The whole app is written with plain SQLite-style SQL: ``?`` placeholders,
``row["col"]`` access, ``cursor.lastrowid`` after INSERT, and
``except sqlite3.IntegrityError`` for UNIQUE violations. Rewriting ~250 query
sites would be risky, so instead this module wraps a psycopg2 connection to
behave like a ``sqlite3.Connection`` for exactly those patterns:

* ``?``            -> translated to ``%s``
* ``row["col"]``   -> psycopg2 RealDictRow (dict subclass)
* ``cur.lastrowid``-> INSERTs get ``RETURNING <pk>`` appended automatically
* IntegrityError   -> psycopg2 errors are re-raised as ``sqlite3`` errors

Engine is chosen by the ``DATABASE_URL`` env var: a ``postgresql://`` URL
selects Postgres; anything else (or unset) keeps SQLite. So local dev and the
73-test suite keep running on SQLite untouched, while production points
``DATABASE_URL`` at RDS.
"""

import os
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


DIALECT = "postgres" if is_postgres() else "sqlite"

# Errors that mean "UNIQUE / FK / CHECK violation". Services catch
# sqlite3.IntegrityError; the Postgres wrapper re-raises as that type, so this
# tuple stays sqlite-only but is exported for anyone who prefers to be explicit.
INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

# Tables with an auto-generated integer primary key, mapped to that key's
# column. Used to append RETURNING so cur.lastrowid works on Postgres.
_PK = {
    "departments": "department_id",
    "majors": "major_id",
    "teachers": "teacher_id",
    "students": "student_id",
    "courses": "course_id",
    "curriculum_courses": "curriculum_id",
    "academic_years": "year_id",
    "terms": "term_id",
    "sections": "section_id",
    "enrollments": "enrollment_id",
    "attendance": "attendance_id",
    "email_log": "email_id",
    "admission_applications": "application_id",
    "fees": "fee_id",
    "payments": "payment_id",
    "waitlist": "waitlist_id",
    "service_requests": "request_id",
    "exam_schedule": "exam_id",
    "users": "user_id",
    "audit_log": "audit_id",
}


def to_postgres_schema(schema: str) -> str:
    """Adapt the SQLite CREATE-TABLE script for Postgres."""
    import re
    s = re.sub(r"PRAGMA[^;]*;\s*", "", schema)
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return s


def _translate(sql: str) -> str:
    # No SQL literal contains '?' or a bare '%' in this codebase (LIKE patterns
    # are passed as parameters), so a plain swap is safe.
    return sql.replace("?", "%s")


def _insert_table(sql: str):
    import re
    m = re.match(r'\s*INSERT\s+(?:OR\s+\w+\s+)?INTO\s+"?(\w+)"?', sql, re.IGNORECASE)
    return m.group(1).lower() if m else None


class _Cursor:
    """Thin proxy giving a psycopg2 cursor the sqlite3 surface the app uses."""

    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size is not None else self._cur.fetchmany()

    def __iter__(self):
        return iter(self._cur)


class PgConnection:
    """Wraps a psycopg2 connection to mimic sqlite3.Connection for this app."""

    def __init__(self, dsn: str):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._dict_cursor = psycopg2.extras.RealDictCursor
        self._conn = psycopg2.connect(dsn)
        self.row_factory = None  # accepted for API-compatibility; ignored

    def _run(self, sql, params, many=False):
        cur = self._conn.cursor(cursor_factory=self._dict_cursor)
        try:
            if many:
                cur.executemany(_translate(sql), list(params))
            else:
                cur.execute(_translate(sql), params)
        except self._psycopg2.IntegrityError as e:
            self._conn.rollback()
            raise sqlite3.IntegrityError(str(e)) from e
        except self._psycopg2.Error as e:
            self._conn.rollback()
            raise sqlite3.OperationalError(str(e)) from e
        return cur

    def execute(self, sql, params=()):
        table = _insert_table(sql)
        pk = _PK.get(table) if table else None
        lastrowid = None
        if pk and "RETURNING" not in sql.upper():
            cur = self._conn.cursor(cursor_factory=self._dict_cursor)
            tsql = _translate(sql).rstrip().rstrip(";") + f" RETURNING {pk}"
            try:
                cur.execute(tsql, params)
            except self._psycopg2.IntegrityError as e:
                self._conn.rollback()
                raise sqlite3.IntegrityError(str(e)) from e
            except self._psycopg2.Error as e:
                self._conn.rollback()
                raise sqlite3.OperationalError(str(e)) from e
            row = cur.fetchone() if cur.description else None
            if row is not None:
                lastrowid = row[pk]
            return _Cursor(cur, lastrowid)
        return _Cursor(self._run(sql, params))

    def executemany(self, sql, seq):
        return _Cursor(self._run(sql, seq, many=True))

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute(script)  # psycopg2 runs multiple ';'-separated statements
        return _Cursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


def connect_postgres() -> "PgConnection":
    return PgConnection(DATABASE_URL)
