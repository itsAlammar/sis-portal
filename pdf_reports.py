"""PDF transcript export.

Requires reportlab (pip install reportlab) -- the one extra dependency
this feature needs on top of Flask. Everything else in the project stays
pure standard library. The import is deliberately lazy (inside the
function, not at module load time) so the rest of the app still starts
fine if reportlab isn't installed; only this one feature is unavailable.
"""

import io
import sqlite3
from datetime import date

from enrollment_service import EnrollmentService
from gpa_service import GPAService
from student_service import StudentService
from term_service import TermService


def generate_transcript_pdf(conn: sqlite3.Connection, student_id: int) -> io.BytesIO:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as e:
        raise RuntimeError(
            "PDF export needs the 'reportlab' package. Install it with: pip install reportlab"
        ) from e

    INK = colors.HexColor("#1E2A38")
    RULE = colors.HexColor("#CDC6B0")
    OXBLOOD = colors.HexColor("#8B3A2E")

    students = StudentService(conn)
    enrollments = EnrollmentService(conn)
    gpa_service = GPAService(conn)
    terms_svc = TermService(conn)

    student = students.get_student(student_id)
    all_rows = enrollments.list_student_enrollments(student_id)
    by_term = {}
    for row in all_rows:
        by_term.setdefault(row["term_id"], []).append(row)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    eyebrow = ParagraphStyle(
        "Eyebrow", parent=styles["Normal"], textColor=OXBLOOD,
        fontName="Helvetica-Bold", fontSize=9, spaceAfter=2,
    )
    title = ParagraphStyle(
        "TranscriptTitle", parent=styles["Title"], textColor=INK,
        fontSize=20, spaceAfter=10,
    )
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=10, spaceAfter=2)
    term_heading = ParagraphStyle(
        "TermHeading", parent=styles["Heading2"], textColor=INK,
        fontSize=12, spaceBefore=14, spaceAfter=4,
    )
    small_muted = ParagraphStyle(
        "SmallMuted", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#666666"), spaceAfter=10,
    )

    story = [
        Paragraph("OFFICE OF THE REGISTRAR", eyebrow),
        Paragraph("Official Transcript", title),
        Paragraph(f"<b>{student.full_name}</b> &nbsp;&middot;&nbsp; {student.student_number}", meta),
        Paragraph(f"Program: {student.program or 'N/A'} &nbsp;&middot;&nbsp; Status: {student.status}", meta),
        Spacer(1, 14),
    ]

    for term_id, rows in sorted(by_term.items(), key=lambda kv: kv[0]):
        term = terms_svc.get_term(term_id)
        story.append(Paragraph(term.name, term_heading))

        table_data = [["Course", "Title", "Cr", "Grade", "Status"]]
        for r in rows:
            table_data.append([
                r["course_code"], r["title"][:38], str(r["credit_hours"]),
                r["grade"] or "-", r["status"],
            ])
        table = Table(table_data, colWidths=[0.8*inch, 3.0*inch, 0.4*inch, 0.7*inch, 1.0*inch])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

        term_gpa = gpa_service.calculate_term_gpa(student_id, term_id)
        gpa_str = f"{term_gpa:.2f}" if term_gpa is not None else "N/A"
        story.append(Paragraph(f"Term GPA: {gpa_str}", small_muted))

    cum_gpa = gpa_service.calculate_cumulative_gpa(student_id)
    cum_gpa_str = f"{cum_gpa:.2f}" if cum_gpa is not None else "N/A"
    standing = gpa_service.get_academic_standing(cum_gpa)
    earned = gpa_service.get_earned_credit_hours(student_id)

    story.append(Spacer(1, 10))
    summary = Table(
        [
            ["Cumulative GPA", cum_gpa_str],
            ["Academic Standing", standing],
            ["Credit Hours Earned", str(earned)],
        ],
        colWidths=[2.2 * inch, 2.5 * inch],
    )
    summary.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(summary)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generated {date.today().isoformat()} -- Student Information System",
        small_muted,
    ))

    doc.build(story)
    buf.seek(0)
    return buf
