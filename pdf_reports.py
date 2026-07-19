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

from database import get_setting
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

        table_data = [["Course", "Title", "Cr", "Mark/100", "Grade", "Status"]]
        for r in rows:
            mark = r["numeric_mark"]
            table_data.append([
                r["course_code"], r["title"][:34], str(r["credit_hours"]),
                (f"{mark:.0f}" if mark is not None else "-"),
                r["grade"] or "-", r["status"],
            ])
        table = Table(table_data, colWidths=[0.8*inch, 2.5*inch, 0.4*inch, 0.8*inch, 0.6*inch, 0.9*inch])
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
        gpa_str = f"{term_gpa:.2f} / 5" if term_gpa is not None else "N/A"
        story.append(Paragraph(f"Term GPA: {gpa_str}", small_muted))

    cum_gpa = gpa_service.calculate_cumulative_gpa(student_id)
    cum_gpa_str = f"{cum_gpa:.2f} / 5" if cum_gpa is not None else "N/A"
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


def generate_receipt_pdf(conn: sqlite3.Connection, payment_id: int) -> io.BytesIO:
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

    from fee_service import FeeService

    INK = colors.HexColor("#1E2A38")
    RULE = colors.HexColor("#CDC6B0")
    OXBLOOD = colors.HexColor("#8B3A2E")

    fees = FeeService(conn)
    payment = fees.get_payment(payment_id)
    student = StudentService(conn).get_student(payment["student_id"])
    fee_total = payment["fee_amount"] + payment["tax_amount"]
    paid_to_date = fees.get_total_paid(payment["fee_id"])
    remaining = max(0.0, round(fee_total - paid_to_date, 2))

    description = payment["fee_type"]
    if payment["course_id"]:
        row = conn.execute("SELECT course_code, title FROM courses WHERE course_id = ?",
                           (payment["course_id"],)).fetchone()
        if row:
            description += f" — {row['course_code']} {row['title']}"
    institution = get_setting(conn, "institution_name_en", "") or "SIS Portal"

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
        "ReceiptTitle", parent=styles["Title"], textColor=INK,
        fontSize=20, spaceAfter=10,
    )
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=10, spaceAfter=2)
    small_muted = ParagraphStyle(
        "SmallMuted", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#666666"), spaceAfter=10,
    )

    story = [
        Paragraph(institution.upper(), eyebrow),
        Paragraph("Payment Receipt", title),
        Paragraph(f"Receipt no. <b>R-{payment_id:06d}</b> &nbsp;&middot;&nbsp; "
                  f"Date: {payment['payment_date']}", meta),
        Paragraph(f"Received from: <b>{student.full_name}</b> &nbsp;&middot;&nbsp; "
                  f"{student.student_number}", meta),
        Paragraph(f"Method: {payment['payment_method'] or 'N/A'}"
                  + (f" &nbsp;&middot;&nbsp; Ref: {payment['reference_number']}"
                     if payment["reference_number"] else ""), meta),
        Spacer(1, 16),
    ]

    table = Table(
        [
            ["Description", description],
            ["Fee total (incl. VAT)", f"{fee_total:.2f} SAR"],
            ["This payment", f"{payment['amount_paid']:.2f} SAR"],
            ["Total paid to date", f"{paid_to_date:.2f} SAR"],
            ["Remaining balance", f"{remaining:.2f} SAR"],
        ],
        colWidths=[2.2 * inch, 4.3 * inch],
    )
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, INK),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Generated {date.today().isoformat()} -- {institution} -- "
        "This receipt is system-generated and valid without signature.",
        small_muted,
    ))

    doc.build(story)
    buf.seek(0)
    return buf
