# Student Information System (SIS) · نظام معلومات الطلاب

Bilingual (Arabic / English) SIS built with Flask + SQLite. Covers
admissions, students, teachers, majors, courses, gender-segregated
sections, enrollment, a 100-point → 5.0 GPA grading system, financials
(per-course billing, registration fee, non-Saudi VAT), role-based staff
access, a student self-service portal, and an audit trail.

الواجهة تدعم العربية والإنجليزية مع تبديل فوري للغة واتجاه RTL.

## Quick start
```bash
pip install -r requirements.txt
python seed_demo.py        # loads bilingual demo data + prints logins
python webapp.py           # http://127.0.0.1:5000
```
Switch language anytime with the **العربية / English** toggle. On an empty
database the staff side opens a one-time `/setup` to create the first admin.

### Demo logins (local only)
| Role | Username / Number | Password |
|---|---|---|
| Admin | `admin` | `admin-demo-123` |
| Registrar | `registrar` | `registrar-demo-123` |
| Accounting | `accountant` | `accounting-demo-123` |
| Teacher | `o.haddad` / `s.alamri` | `teacher-demo-123` |
| Student | `S20250001` … | `student-demo-123` |

## Features
- **Bilingual UI (AR/EN) + RTL** — session locale, one translation
  dictionary (`i18n.py`), every page and form translated.
- **Admissions** — public application (national ID (10 digits), quad name
  AR+EN, DOB, email, mobile, gender, nationality — all required). Nothing
  self-activates: an admin/registrar approves, which creates the student,
  generates the university number, charges the registration fee, and
  enables portal login.
- **Roles** — admin, registrar, teacher, accounting (each with its own
  landing and permissions); managed on the Roles page.
- **Majors (التخصصات)** — per-major graduation credit requirement and
  gender; drives degree-progress tracking.
- **Gender segregation** — sections are single-gender; a student only ever
  sees and can enrol in same-gender sections; teachers carry a gender too.
- **Grading** — marks entered out of 100, mapped to letters (A+…F) and
  **5.0** grade points via the `grade_scale` table; GPA is credit-weighted.
- **Financial** — every course has a price; enrolling bills per-course
  tuition; an admin-set **registration fee** is charged per term, with
  **VAT added for non-Saudi students on the registration fee only**;
  itemized statement and partial payments.
- **Registration portal** — combined enrol + drop on one page, filtered to
  the student's gender; **My grades (درجاتي)** with academic-year & term
  dropdowns; degree progress; financial statement; account settings.
- **Advisor** — each student can be assigned an academic advisor.
- **Multiple teachers per course**; academic years & terms (incl. summer).
- **CSV import _and_ export** for students, teachers, and courses (with
  downloadable templates).
- **Other services (خدمات أخرى)** — students submit deferral, major
  transfer, exam deferral, course equivalency, or financial-aid requests;
  staff review them. (Attendance and exam-room scheduling are represented
  here as request types and are the next modules to build out fully.)
- **Audit log**, **CSRF protection**, PBKDF2 password hashing,
  admin-controlled **settings** (fees, VAT, institution name), and an
  **LMS placeholder** wired for the future separate Learning system.

## Security & deployment
- `SIS_SECRET_KEY` from the environment; debug off unless `SIS_DEBUG=1`.
- Production: `gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app` behind
  TLS. `Dockerfile` mounts data at `/data`; `SIS_DB_DIR` relocates the DB.
- Path to scale on AWS: SQLite → RDS Postgres, app → ECS/Fargate,
  `SIS_SECRET_KEY` → Secrets Manager, logs → CloudWatch. All SQL uses `?`
  placeholders, isolated to `database.py`.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest          # 32 tests: grading/GPA, gender rules, admissions,
                          # financial/VAT, roles, CSRF, i18n, CSV
```
CI runs the suite on every push (`.github/workflows/ci.yml`).

## Notes / next
- The web app is the primary interface for this version. The legacy
  terminal CLI (`main.py`) reflects the earlier data model and is not yet
  updated to v2.
- Dedicated attendance, exam scheduling/rooms, and scholarship modules are
  scaffolded (as service requests) and are the natural next build.
- The LMS is intentionally a **separate future project**; this app only
  exposes a placeholder entry point for it.
