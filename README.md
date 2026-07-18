# Student Information System

SQLite-backed SIS covering students, teachers, courses, sections,
enrollment, grading, GPA, fee management, role-based staff access, and a
student self-service portal. The service layer is pure Python standard
library; the web interface needs only Flask.

## Requirements
- Core system (CLI + services): Python 3.9+, no dependencies.
- Web interface: `pip install -r requirements.txt` (Flask + gunicorn).
- PDF transcript export: `pip install reportlab` (optional).
- Tests: `pip install -r requirements-dev.txt`, then `python -m pytest`.

## Quick start — terminal (no extra install)
```bash
python seed_demo.py   # optional: loads demo students/teachers/courses/fees
python main.py         # launches the interactive menu
```

## Quick start — web browser
```bash
pip install -r requirements.txt
python seed_demo.py    # optional but recommended: prints demo login credentials
python webapp.py
```
Then open **http://127.0.0.1:5000**. On a fresh (unseeded) database the
staff side takes you to a one-time **/setup** page to create the first
admin account; that page disappears once any account exists.

### Signing in
| Who | Where | How |
|---|---|---|
| Admin / Registrar | `/login` | Username + password. Registrars manage all records; admins additionally manage staff accounts (`/users`). |
| Teacher | `/login` | Same login page; lands on **My sections** (`/teach`) and can enter grades for their own sections only. |
| Student | `/portal/login` | Student number + password. First visit: "Activate your account" — confirm the email on file, choose a password. Forgotten password: registrar clicks *Reset portal password* on the student's page, and the student re-activates. |

`seed_demo.py` creates throwaway demo accounts and prints them
(`admin / admin-demo-123`, a teacher account, and `student-demo-123` for
every seeded student). **Demo credentials are for local exploration only.**

## Security model
- **Authentication everywhere** — every registrar page requires a signed-in
  admin/registrar; teachers are scoped to their own sections; students to
  their own record. Passwords are hashed with PBKDF2-HMAC-SHA256
  (300k iterations, per-password salt), in the standard library.
- **CSRF protection** — every POST form carries a per-session token,
  verified before any handler runs.
- **Secret key from the environment** — set `SIS_SECRET_KEY` (see
  `.env.example`). Without it a random per-run key is used and a warning
  logged: fine locally, not for deployment.
- **No debug mode by default** — `python webapp.py` runs with the Werkzeug
  debugger OFF unless you explicitly set `SIS_DEBUG=1`. Never expose debug
  mode to a network: it allows remote code execution.
- **Audit log** — every state-changing action (grades, payments, waivers,
  enrollment changes, record creation, logins, account changes) is recorded
  append-only with actor, timestamp, and details. Staff view at `/audit`.
- **Session hygiene** — cookies are HttpOnly + SameSite=Lax; session is
  refreshed on every login.

## Operations
```bash
python manage.py create-user <name> <admin|registrar|teacher> [--teacher-id N]
python manage.py reset-password <name>
python manage.py list-users
python manage.py backup            # online snapshot to backups/, keeps newest 30
```
`backup` uses SQLite's backup API, so it is safe while the app is
serving. Schedule it (cron/systemd timer) and copy the `backups/`
directory off the machine.

## Deployment
The dev server (`python webapp.py`) is for localhost only. For anything
reachable by other people:

```bash
export SIS_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app
```

or with Docker (data persists in the `/data` volume):
```bash
docker build -t sis .
docker run -d -p 8000:8000 -v sis-data:/data -e SIS_SECRET_KEY=... sis
```

Put a TLS-terminating reverse proxy (nginx, Caddy, or a cloud load
balancer) in front — the app itself does not speak HTTPS. `SIS_DB_DIR`
controls where `sis.db` lives.

### Scaling path (AWS example)
SQLite (now in WAL mode with a busy timeout) is fine for a small office.
For real concurrent load, the pieces map cleanly to managed services:
`sis.db` → RDS Postgres, the Flask app → ECS/Fargate behind an ALB,
`SIS_SECRET_KEY` → Secrets Manager, logs → CloudWatch, `manage.py backup`
→ RDS automated snapshots. Every service uses plain SQL through
`database.py`, so Postgres migration touches that one module plus the
handful of SQLite-specific pragmas.

## Tests & CI
```bash
pip install -r requirements-dev.txt
python -m pytest
```
Covers the enrollment rule chain (capacity → waitlist, prerequisites,
schedule conflicts, add/drop deadlines, waitlist promotion), grading/GPA,
fee lifecycle including waivers and overpayment rejection, password
hashing, portal activation, route protection per role, CSRF rejection,
and audit logging. GitHub Actions runs the suite on every push
(`.github/workflows/ci.yml`).

## Architecture
| File | Responsibility |
|---|---|
| `database.py` | Schema, connection, migrations, grade-scale seed |
| `models.py` | Read-only dataclasses per entity |
| `exceptions.py` | Domain errors (capacity, prerequisites, duplicates...) |
| `auth_service.py` | Staff accounts, roles, student portal passwords (PBKDF2) |
| `audit_service.py` | Append-only audit trail |
| `student_service.py` / `teacher_service.py` | People management |
| `course_service.py` | Courses + prerequisite graph |
| `term_service.py` | Academic terms/semesters |
| `section_service.py` | Course offerings per term, conflict detection |
| `enrollment_service.py` | Enroll/drop with full validation chain, deadlines, waitlist promotion |
| `waitlist_service.py` | Section waitlist join/leave/position tracking |
| `grading_service.py` | Letter-grade assignment |
| `gpa_service.py` | Term & cumulative GPA, academic standing |
| `fee_service.py` | Fee assessment, partial payments, waivers, balances |
| `bulk_import.py` | CSV student import, shared by CLI and web |
| `pdf_reports.py` | PDF transcript export (needs `reportlab`) |
| `reports.py` | Transcript / roster / fee-statement text reports |
| `cli.py` | Menu-driven terminal interface |
| `manage.py` | Ops commands: user admin, password resets, backups |
| `webapp.py` | Flask routes: registrar, teacher view, student portal |
| `wsgi.py` | Production WSGI entry point |
| `templates/`, `static/` | HTML pages and stylesheet |
| `seed_demo.py` | Sample data + demo accounts generator |
| `tests/` | pytest suite (services, auth, web) |

Every service takes a raw `sqlite3.Connection`, so you can script against
them directly instead of the CLI:

```python
from database import get_connection, initialize_database
from student_service import StudentService

conn = get_connection()
initialize_database(conn)
for s in StudentService(conn).list_students():
    print(s.student_number, s.full_name, s.status)
```

## Business rules enforced
- **Enrollment** blocks: inactive students, closed sections, duplicate
  enrollment, over-capacity sections (offers the waitlist instead),
  missing prerequisites, schedule conflicts, and add/drop deadlines once
  a term's dates have passed.
- **Waitlist**: a full section offers waitlisting instead of a flat
  rejection. Dropping a seat automatically promotes the longest-waiting
  student; if they're no longer eligible (e.g. gone inactive), the next
  person in line is tried automatically.
- **Prerequisites**: support both "all of these" (plain `add_prerequisite`)
  and "any one of these" alternative groups (`add_prerequisite_group`,
  or the "alternative group" form on a course's page).
- **Grading**: 4.0 scale (A–F, plus W/withdrawn and I/incomplete, both
  excluded from GPA). Edit `GRADE_SCALE` in `database.py` for a 5.0 scale
  or different letters — nothing else needs to change.
- **GPA**: credit-hour-weighted, computed per term and cumulatively.
  Standing: Dean's List (≥3.5) · Good Standing (≥2.0) · Probation (≥1.0)
  · Suspension (<1.0).
- **Fees**: partial payments supported; status auto-updates between
  pending/partial/paid; a payment that would exceed the balance is
  rejected; fees can be waived (excluded from balance, blocks further
  payment).
- **Grading permissions**: teachers can grade only sections assigned to
  them; registrars/admins can grade any section. Every grade change is
  audited with who set it.

## Known limits (deliberate, documented)
- **Lists paginate at 25 rows**; search returns unpaginated matches.
- **SQLite** handles a small office fine (WAL + busy timeout are enabled)
  but is not built for heavy concurrent writes — see the scaling path above.
- **Waitlist auto-promotion ignores payment state** — promotion only
  re-runs the standard enrollment validation chain.
- The CLI (`main.py`) is a trusted local tool: it bypasses web auth and
  writes no audit entries. Restrict shell access to the box accordingly.
