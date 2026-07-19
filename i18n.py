"""Bilingual (Arabic / English) internationalization layer.

A single translation dictionary keyed by short string ids. Each id maps
to {"en": ..., "ar": ...}. Templates call `t("key")` and the active
locale is chosen per-session (?lang=ar / ?lang=en, remembered in the
session cookie). Arabic renders right-to-left; see `dir()` and the
`[dir=rtl]` rules in static/style.css.

Keep ids descriptive and grouped by area. Missing keys fall back to the
id itself so nothing ever crashes on a lookup.
"""

from typing import Dict

SUPPORTED = ("en", "ar")
DEFAULT_LOCALE = "en"

# ----------------------------------------------------------------------
# Translations. Grouped by area for maintainability.
# ----------------------------------------------------------------------
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # -- generic / actions ------------------------------------------------
    "app.name": {"en": "SIS Portal", "ar": "بوابة نظام معلومات الطلاب"},
    "app.short": {"en": "SIS Portal", "ar": "البوابة"},
    "action.save": {"en": "Save", "ar": "حفظ"},
    "action.add": {"en": "Add", "ar": "إضافة"},
    "action.edit": {"en": "Edit", "ar": "تعديل"},
    "action.delete": {"en": "Delete", "ar": "حذف"},
    "action.cancel": {"en": "Cancel", "ar": "إلغاء"},
    "action.update": {"en": "Update", "ar": "تحديث"},
    "action.submit": {"en": "Submit", "ar": "إرسال"},
    "action.search": {"en": "Search", "ar": "بحث"},
    "action.back": {"en": "Back", "ar": "رجوع"},
    "action.approve": {"en": "Approve", "ar": "قبول"},
    "action.reject": {"en": "Reject", "ar": "رفض"},
    "action.export": {"en": "Export CSV", "ar": "تصدير CSV"},
    "action.import": {"en": "Import CSV", "ar": "استيراد CSV"},
    "action.download_template": {"en": "Download template", "ar": "تحميل النموذج"},
    "action.enroll": {"en": "Enroll", "ar": "تسجيل"},
    "action.drop": {"en": "Drop", "ar": "حذف المادة"},
    "action.pay": {"en": "Pay", "ar": "دفع"},
    "action.login": {"en": "Sign in", "ar": "تسجيل الدخول"},
    "action.logout": {"en": "Log out", "ar": "تسجيل الخروج"},
    "action.register": {"en": "Register", "ar": "تسجيل"},
    "common.yes": {"en": "Yes", "ar": "نعم"},
    "common.no": {"en": "No", "ar": "لا"},
    "common.none": {"en": "—", "ar": "—"},
    "common.all": {"en": "All", "ar": "الكل"},
    "common.status": {"en": "Status", "ar": "الحالة"},
    "common.actions": {"en": "Actions", "ar": "إجراءات"},
    "common.name": {"en": "Name", "ar": "الاسم"},
    "common.email": {"en": "Email", "ar": "البريد الإلكتروني"},
    "common.mobile": {"en": "Mobile", "ar": "رقم الجوال"},
    "common.gender": {"en": "Gender", "ar": "الجنس"},
    "common.male": {"en": "Male", "ar": "ذكر"},
    "common.female": {"en": "Female", "ar": "أنثى"},
    "common.nationality": {"en": "Nationality", "ar": "الجنسية"},
    "common.saudi": {"en": "Saudi", "ar": "سعودي"},
    "common.non_saudi": {"en": "Non-Saudi", "ar": "غير سعودي"},
    "common.national_id": {"en": "National ID", "ar": "رقم الهوية"},
    "common.date_of_birth": {"en": "Date of birth", "ar": "تاريخ الميلاد"},
    "common.page_of": {"en": "Page {page} of {pages}", "ar": "صفحة {page} من {pages}"},
    "common.previous": {"en": "← Previous", "ar": "السابق ←"},
    "common.next": {"en": "Next →", "ar": "→ التالي"},
    "common.required_note": {"en": "All fields are required.", "ar": "جميع الحقول إلزامية."},
    "lang.toggle": {"en": "العربية", "ar": "English"},

    # -- navigation -------------------------------------------------------
    "nav.dashboard": {"en": "Dashboard", "ar": "الرئيسية"},
    "nav.students": {"en": "Students", "ar": "الطلاب"},
    "nav.teachers": {"en": "Teachers", "ar": "المعلمون"},
    "nav.courses": {"en": "Courses", "ar": "المقررات"},
    "nav.majors": {"en": "Majors", "ar": "التخصصات"},
    "nav.terms": {"en": "Terms", "ar": "الفصول الدراسية"},
    "nav.sections": {"en": "Sections", "ar": "الشُّعب"},
    "nav.admissions": {"en": "Admissions", "ar": "القبول"},
    "nav.financial": {"en": "Financial", "ar": "الشؤون المالية"},
    "nav.audit": {"en": "Audit log", "ar": "سجل التدقيق"},
    "nav.users": {"en": "Users", "ar": "المستخدمون"},
    "nav.roles": {"en": "Roles", "ar": "الصلاحيات"},
    "nav.settings": {"en": "Account settings", "ar": "إعدادات الحساب"},
    "nav.lms": {"en": "LMS", "ar": "نظام التعلم"},
    "nav.lms_soon": {"en": "Learning system (coming soon)", "ar": "نظام إدارة التعلم (قريباً)"},
    "nav.registration": {"en": "Registration", "ar": "التسجيل"},
    "reg.current": {"en": "My registered courses", "ar": "موادي المسجّلة"},
    "reg.available": {"en": "Available sections", "ar": "الشُّعب المتاحة"},
    "reg.same_gender": {"en": "Only sections matching your gender are shown.",
                        "ar": "تظهر لك شُعب جنسك فقط."},
    "nav.my_grades": {"en": "My grades", "ar": "درجاتي"},
    "nav.transcript": {"en": "Transcript", "ar": "السجل الأكاديمي"},
    "nav.other_services": {"en": "Other services", "ar": "خدمات أخرى"},
    "nav.my_sections": {"en": "My sections", "ar": "شُعبي"},
    "nav.degree_audit": {"en": "Degree progress", "ar": "متابعة التخرج"},

    # -- misc labels swept from templates ---------------------------------
    "course.prereqs": {"en": "Prerequisites", "ar": "المتطلبات السابقة"},
    "common.type": {"en": "Type", "ar": "النوع"},
    "common.details": {"en": "Details", "ar": "التفاصيل"},
    "common.seats": {"en": "Seats", "ar": "المقاعد"},
    "common.when": {"en": "When", "ar": "الوقت"},
    "common.who": {"en": "Who", "ar": "المستخدم"},
    "common.action": {"en": "Action", "ar": "الإجراء"},
    "common.department": {"en": "Department", "ar": "القسم"},
    "term.year": {"en": "Academic year", "ar": "السنة الدراسية"},
    "term.start": {"en": "Start date", "ar": "تاريخ البداية"},
    "term.end": {"en": "End date", "ar": "تاريخ النهاية"},
    "term.set_current": {"en": "Set as current", "ar": "تعيين كفصل حالي"},
    "term.add_deadline": {"en": "Add deadline", "ar": "آخر موعد للإضافة"},
    "term.drop_deadline": {"en": "Drop deadline", "ar": "آخر موعد للحذف"},
    "term.regular": {"en": "Regular", "ar": "فصل اعتيادي"},
    "term.summer": {"en": "Summer", "ar": "فصل صيفي"},
    "section.number": {"en": "Section #", "ar": "رقم الشعبة"},
    "section.capacity": {"en": "Capacity", "ar": "السعة"},
    "section.room": {"en": "Room", "ar": "القاعة"},
    "section.days": {"en": "Days", "ar": "الأيام"},
    "section.start": {"en": "Start time", "ar": "وقت البداية"},
    "section.end": {"en": "End time", "ar": "وقت النهاية"},
    "section.tbd": {"en": "TBD", "ar": "غير محدد"},
    "teacher.title": {"en": "Title", "ar": "اللقب الوظيفي"},
    "user.role": {"en": "Role", "ar": "الدور"},
    "user.enable": {"en": "Enable", "ar": "تفعيل"},
    "user.disable": {"en": "Disable", "ar": "تعطيل"},
    "user.linked_teacher": {"en": "Linked teacher", "ar": "المعلم المرتبط"},
    "user.staff_table": {"en": "Staff & permissions", "ar": "الموظفون وصلاحياتهم"},
    "user.last_admin_guard": {"en": "You can't remove the admin role from the last active admin (or yourself).",
                              "ar": "لا يمكن إزالة صلاحية المدير من آخر مدير نشط (أو من حسابك أنت)."},
    "settings.change_password": {"en": "Change password", "ar": "تغيير كلمة المرور"},
    "settings.institution_en": {"en": "Institution name (EN)", "ar": "اسم المؤسسة (إنجليزي)"},
    "settings.institution_ar": {"en": "Institution name (AR)", "ar": "اسم المؤسسة (عربي)"},
    "menu.account": {"en": "Account", "ar": "حسابي"},

    # -- email / notifications --------------------------------------------
    "nav.emails": {"en": "Messages", "ar": "الرسائل"},
    "mail.sent": {"en": "Acceptance email sent.", "ar": "تم إرسال إيميل القبول."},
    "mail.logged": {"en": "Email recorded (sending is disabled in Settings).",
                    "ar": "سُجّلت الرسالة (الإرسال معطّل من الإعدادات)."},
    "mail.failed": {"en": "Email failed to send — check SMTP settings.",
                    "ar": "فشل إرسال الإيميل — تحقق من إعدادات SMTP."},
    "mail.send_acceptance": {"en": "Send acceptance email", "ar": "إرسال إيميل القبول"},
    "mail.settings": {"en": "Email & notifications", "ar": "الإيميل والإشعارات"},
    "mail.enabled": {"en": "Enable real email sending (SMTP)", "ar": "تفعيل الإرسال الفعلي (SMTP)"},
    "mail.auto_on_approval": {"en": "Send acceptance email automatically on approval",
                              "ar": "إرسال إيميل القبول تلقائياً عند قبول الطالب"},
    "mail.subject": {"en": "Acceptance subject", "ar": "عنوان رسالة القبول"},
    "mail.body": {"en": "Acceptance message (placeholders: {name} {student_number} {major} {national_id} {institution})",
                  "ar": "نص رسالة القبول (المتغيرات: {name} {student_number} {major} {national_id} {institution})"},
    "grade.breakdown": {"en": "Grade breakdown", "ar": "تفاصيل الدرجة"},
    "grade.coursework": {"en": "Coursework (/50)", "ar": "أعمال السنة (من 50)"},
    "grade.final": {"en": "Final exam (/50)", "ar": "الاختبار النهائي (من 50)"},
    "grade.locked_msg": {"en": "Grade editing is locked — the deadline ({date}) has passed.",
                         "ar": "تعديل الدرجات مقفل — انتهى الموعد المحدد ({date})."},
    "grade.open_until": {"en": "Grades can be added or edited until {date}.",
                         "ar": "يمكن إضافة وتعديل الدرجات حتى {date}."},
    "term.grades_deadline": {"en": "Grades lock date", "ar": "تاريخ قفل الدرجات"},
    "mail.section_email": {"en": "Email all students in this section",
                           "ar": "إرسال إيميل لطلاب الشعبة"},
    "mail.subject_line": {"en": "Subject", "ar": "الموضوع"},
    "mail.message": {"en": "Message", "ar": "نص الرسالة"},
    "mail.broadcast_done": {"en": "Message queued for {n} student(s).",
                            "ar": "أُرسلت الرسالة إلى {n} من الطلاب."},
    "att.title": {"en": "Attendance", "ar": "الحضور والغياب"},
    "att.take": {"en": "Take attendance", "ar": "التحضير"},
    "att.date": {"en": "Date", "ar": "التاريخ"},
    "att.present": {"en": "Present", "ar": "حاضر"},
    "att.absent": {"en": "Absent", "ar": "غائب"},
    "att.late": {"en": "Late", "ar": "متأخر"},
    "att.excused": {"en": "Excused", "ar": "بعذر"},
    "att.absences": {"en": "Absences", "ar": "الغيابات"},
    "att.sessions": {"en": "Sessions", "ar": "المحاضرات"},
    "action.download_pdf": {"en": "Download PDF transcript", "ar": "تحميل السجل الأكاديمي PDF"},
    "reg.new_course": {"en": "Register a new course", "ar": "تسجيل مقرر جديد"},
    "fin.view_details": {"en": "Financial details", "ar": "التفاصيل المالية"},
    "fin.total_paid": {"en": "Total paid", "ar": "إجمالي المدفوع"},
    "student.portal_reset": {"en": "Reset portal password", "ar": "إعادة تعيين كلمة مرور البوابة"},
    "search.by_number_or_name": {"en": "Search by number or name",
                                 "ar": "ابحث بالرقم الجامعي أو الاسم"},

    # -- record statuses --------------------------------------------------
    "status.active": {"en": "Active", "ar": "نشط"},
    "status.completed": {"en": "Completed", "ar": "مكتمل"},
    "status.paid": {"en": "Paid", "ar": "مدفوع"},
    "status.open": {"en": "Open", "ar": "مفتوحة"},
    "status.graduated": {"en": "Graduated", "ar": "متخرج"},
    "status.waived": {"en": "Waived", "ar": "معفى"},
    "status.promoted": {"en": "Promoted", "ar": "مرقّى من الانتظار"},
    "status.approved": {"en": "Approved", "ar": "مقبول"},
    "status.enrolled": {"en": "Enrolled", "ar": "مسجّل"},
    "status.partial": {"en": "Partially paid", "ar": "مدفوع جزئياً"},
    "status.pending": {"en": "Pending", "ar": "قيد الانتظار"},
    "status.closed": {"en": "Closed", "ar": "مغلقة"},
    "status.waiting": {"en": "Waiting", "ar": "في الانتظار"},
    "status.deferred": {"en": "Deferred", "ar": "مؤجل"},
    "status.suspended": {"en": "Suspended", "ar": "موقوف"},
    "status.withdrawn": {"en": "Withdrawn", "ar": "منسحب"},
    "status.dropped": {"en": "Dropped", "ar": "محذوفة"},
    "status.overdue": {"en": "Overdue", "ar": "متأخر"},
    "status.cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "status.inactive": {"en": "Inactive", "ar": "غير نشط"},
    "status.skipped": {"en": "Skipped", "ar": "متجاوز"},
    "status.rejected": {"en": "Rejected", "ar": "مرفوض"},
    "status.disabled": {"en": "Disabled", "ar": "معطل"},

    # -- service request kinds --------------------------------------------
    "kind.deferral": {"en": "Term deferral", "ar": "تأجيل فصل دراسي"},
    "kind.major_transfer": {"en": "Major transfer", "ar": "تحويل تخصص"},
    "kind.exam_deferral": {"en": "Exam deferral", "ar": "تأجيل اختبار"},
    "kind.equivalency": {"en": "Course equivalency", "ar": "معادلة مقرر"},
    "kind.financial_aid": {"en": "Financial aid / scholarship", "ar": "دعم مالي / منحة"},
    "kind.other": {"en": "Other", "ar": "أخرى"},

    # -- fee types --------------------------------------------------------
    "feetype.tuition": {"en": "Tuition", "ar": "رسوم دراسية"},
    "feetype.registration": {"en": "Registration fee", "ar": "رسوم التسجيل"},
    "feetype.vat": {"en": "VAT", "ar": "ضريبة القيمة المضافة"},

    # -- roles ------------------------------------------------------------
    "role.admin": {"en": "Admin", "ar": "مدير النظام"},
    "role.registrar": {"en": "Registrar", "ar": "القبول والتسجيل"},
    "role.teacher": {"en": "Teacher", "ar": "معلم"},
    "role.accounting": {"en": "Accounting", "ar": "المحاسبة"},
    "role.advisor": {"en": "Academic advisor", "ar": "المرشد الأكاديمي"},

    # -- landing / auth ---------------------------------------------------
    "landing.registrar_title": {"en": "Registrar & Staff", "ar": "القبول والتسجيل والموظفون"},
    "landing.registrar_desc": {"en": "Administrative access to records.", "ar": "وصول إداري للسجلات."},
    "landing.portal_title": {"en": "Student Portal", "ar": "بوابة الطالب"},
    "landing.portal_desc": {"en": "Self-service for your own record.", "ar": "خدمة ذاتية لسجلك الخاص."},
    "landing.apply_title": {"en": "New student? Apply", "ar": "طالب جديد؟ قدّم الآن"},
    "landing.apply_desc": {"en": "Submit an admission application.", "ar": "قدّم طلب التحاق."},
    "auth.staff_signin": {"en": "Staff sign in", "ar": "دخول الموظفين"},
    "auth.username": {"en": "Username", "ar": "اسم المستخدم"},
    "auth.password": {"en": "Password", "ar": "كلمة المرور"},
    "auth.confirm_password": {"en": "Confirm password", "ar": "تأكيد كلمة المرور"},
    "auth.student_number": {"en": "Student number", "ar": "الرقم الجامعي"},
    "auth.invalid": {"en": "Invalid username or password.", "ar": "اسم المستخدم أو كلمة المرور غير صحيحة."},
    "auth.signed_in_as": {"en": "Signed in as", "ar": "مسجّل الدخول باسم"},

    # -- students ---------------------------------------------------------
    "student.first_name": {"en": "First name", "ar": "الاسم الأول"},
    "student.second_name": {"en": "Second name", "ar": "الاسم الثاني"},
    "student.third_name": {"en": "Third name", "ar": "الاسم الثالث"},
    "student.last_name": {"en": "Last name", "ar": "اسم العائلة"},
    "student.name_ar": {"en": "Full name (Arabic)", "ar": "الاسم الرباعي (عربي)"},
    "student.name_en": {"en": "Full name (English)", "ar": "الاسم الرباعي (إنجليزي)"},
    "student.program": {"en": "Program", "ar": "البرنامج"},
    "student.major": {"en": "Major", "ar": "التخصص"},
    "student.advisor": {"en": "Academic advisor", "ar": "المرشد الأكاديمي"},
    "student.gpa": {"en": "Cumulative GPA", "ar": "المعدل التراكمي"},
    "student.standing": {"en": "Academic standing", "ar": "الوضع الأكاديمي"},
    "student.earned_hours": {"en": "Credit hours earned", "ar": "الساعات المكتسبة"},
    "student.remaining_hours": {"en": "Credit hours remaining", "ar": "الساعات المتبقية"},
    "student.balance": {"en": "Balance due", "ar": "المبلغ المستحق"},
    "student.add": {"en": "Add student", "ar": "إضافة طالب"},

    # -- courses / grades -------------------------------------------------
    "course.code": {"en": "Code", "ar": "الرمز"},
    "course.title": {"en": "Title", "ar": "اسم المقرر"},
    "course.credits": {"en": "Credit hours", "ar": "الساعات"},
    "course.price": {"en": "Price", "ar": "السعر"},
    "course.teachers": {"en": "Teachers", "ar": "المعلمون"},
    "grade.grade": {"en": "Grade", "ar": "الدرجة"},
    "grade.numeric": {"en": "Mark (/100)", "ar": "الدرجة (من 100)"},
    "grade.letter": {"en": "Letter", "ar": "التقدير"},
    "grade.points": {"en": "Points", "ar": "النقاط"},
    "grade.save": {"en": "Save grades", "ar": "حفظ الدرجات"},

    # -- financial --------------------------------------------------------
    "fin.registration_fee": {"en": "Registration fee", "ar": "رسوم التسجيل"},
    "fin.tuition": {"en": "Tuition", "ar": "الرسوم الدراسية"},
    "fin.tax": {"en": "VAT", "ar": "ضريبة القيمة المضافة"},
    "fin.amount": {"en": "Amount", "ar": "المبلغ"},
    "fin.paid": {"en": "Paid", "ar": "المدفوع"},
    "fin.remaining": {"en": "Remaining", "ar": "المتبقي"},
    "fin.per_course": {"en": "Charges by course", "ar": "الرسوم حسب المادة"},
    "fin.pay_now": {"en": "Pay now", "ar": "ادفع الآن"},
    "fin.statement": {"en": "Statement of account", "ar": "كشف الحساب"},
    "fin.outstanding_invoices": {"en": "Outstanding invoices", "ar": "الفواتير المستحقة"},
    "fin.date": {"en": "Date", "ar": "التاريخ"},
    "fin.total": {"en": "Total", "ar": "الإجمالي"},

    # -- admissions -------------------------------------------------------
    "adm.apply": {"en": "Admission application", "ar": "طلب التحاق"},
    "adm.pending": {"en": "Pending applications", "ar": "الطلبات المعلّقة"},
    "adm.approve_note": {"en": "Approving creates the student and issues a university number.",
                         "ar": "القبول ينشئ الطالب ويصدر الرقم الجامعي."},
    "adm.submitted": {"en": "Application submitted. You'll be notified once reviewed.",
                      "ar": "تم إرسال الطلب. سيتم إشعارك بعد المراجعة."},
    "adm.id_ten_digits": {"en": "National ID must be exactly 10 digits.",
                          "ar": "رقم الهوية يجب أن يكون 10 أرقام بالضبط."},

    # -- misc pages -------------------------------------------------------
    "other.title": {"en": "Other services", "ar": "الخدمات الأخرى"},
    "other.desc": {"en": "Deferral, major transfer, and other requests.",
                   "ar": "طلبات التأجيل والتحويل بين التخصصات وغيرها."},
    "soon.badge": {"en": "Coming soon", "ar": "قريباً"},
    "flash.saved": {"en": "Saved.", "ar": "تم الحفظ."},
    "empty.none": {"en": "Nothing here yet.", "ar": "لا يوجد شيء بعد."},
}


def normalize(locale: str) -> str:
    return locale if locale in SUPPORTED else DEFAULT_LOCALE


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs) -> str:
    """Translate `key` into `locale`, formatting any {placeholders}."""
    entry = TRANSLATIONS.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(locale) or entry.get(DEFAULT_LOCALE) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def dir_for(locale: str) -> str:
    return "rtl" if locale == "ar" else "ltr"
