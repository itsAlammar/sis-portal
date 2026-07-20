#!/usr/bin/env python3
"""Stop hook: نبّه الوكيل إذا بقيت تغييرات غير محفوظة قبل إنهاء الجلسة.

تصميم آمن: يحجب الإيقاف مرة واحدة فقط عند وجود تغييرات غير محفوظة (uncommitted)،
ثم يسمح بالإيقاف في النداء التالي (stop_hook_active) لمنع أي حلقة لا نهائية.
لا يحجب على «مدفوع/غير مدفوع» — فقط على وجود تعديلات غير محفوظة محليًا — حتى لا
يعلق إن تعذّر الدفع لأسباب شبكية.
"""
import json
import os
import subprocess
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

# تجنّب الحلقة: إن كان هذا النداء ناتجًا عن حجب سابق من نفس الهوك، اسمح بالإيقاف.
if data.get("stop_hook_active"):
    sys.exit(0)

root = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
try:
    dirty = subprocess.run(
        ["git", "-C", root, "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
except Exception:
    sys.exit(0)

if dirty:
    reason = (
        "لديك تغييرات غير محفوظة قبل إنهاء الجلسة. أكمل روتين الحفظ:\n"
        "1) python -m pytest -q (يجب أن تنجح كلها).\n"
        "2) git add -A && git commit ثم git push -u origin main.\n"
        "3) حدّث حالة الجلسة في SESSIONS.md (مكتملة أو جارية + 'توقفنا عند: …').\n"
        "إن كان العمل ناقصًا فاحفظه على main واجعل الحالة «جارية» بدل ترك تغييرات تُفقد."
    )
    print(json.dumps({"decision": "block", "reason": reason}))

sys.exit(0)
