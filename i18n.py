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
    "app.name": {"en": "Student Information System", "ar": "نظام معلومات الطلاب"},
    "app.short": {"en": "SIS", "ar": "النظام"},
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
    "nav.my_grades": {"en": "My grades", "ar": "درجاتي"},
    "nav.transcript": {"en": "Transcript", "ar": "السجل الأكاديمي"},
    "nav.other_services": {"en": "Other services", "ar": "خدمات أخرى"},
    "nav.my_sections": {"en": "My sections", "ar": "شُعبي"},
    "nav.degree_audit": {"en": "Degree progress", "ar": "متابعة التخرج"},

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
    "grade.numeric": {"en": "Mark (/100)", "ar": "الدرجة (من ١٠٠)"},
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

    # -- admissions -------------------------------------------------------
    "adm.apply": {"en": "Admission application", "ar": "طلب التحاق"},
    "adm.pending": {"en": "Pending applications", "ar": "الطلبات المعلّقة"},
    "adm.approve_note": {"en": "Approving creates the student and issues a university number.",
                         "ar": "القبول ينشئ الطالب ويصدر الرقم الجامعي."},
    "adm.submitted": {"en": "Application submitted. You'll be notified once reviewed.",
                      "ar": "تم إرسال الطلب. سيتم إشعارك بعد المراجعة."},
    "adm.id_ten_digits": {"en": "National ID must be exactly 10 digits.",
                          "ar": "رقم الهوية يجب أن يكون ١٠ أرقام بالضبط."},

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
