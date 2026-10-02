"""Live local demo of the notifications feature (Feature 2).

Requires the dev backend running on 127.0.0.1:8000 (settings_dev) with output
redirected to local.dev.log, e.g.:

    python -u manage.py runserver 127.0.0.1:8000 --settings=config.settings_dev --noreload *> local.dev.log

Walks, over real HTTP, the exact flow a local user goes through:
  register -> login blocked (unverified) -> copy the 6-digit code printed in
  the backend console -> verify -> login -> admin publishes a course
  announcement -> enrolled student sees it in /notifications/.

The OTP code is NOT simulated or deterministic: it is read from the server's
console output, exactly as it would appear in a developer's terminal.
"""

import json
import os
import random
import re
import string
import time

import requests

import django  # noqa: F401  (only used to seed the dev DB before HTTP calls)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
django.setup()

from apps.academic.models import Course, Enrollment  # noqa: E402
from apps.accounts.models import User  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.dev.log")


def rnd(length=6):
    return "".join(random.choices(string.ascii_lowercase, k=length))


def show(label, resp, body_only=False):
    try:
        body = resp.json()
    except Exception:
        body = resp.content[:400].decode(errors="replace")
    print(f"  {label} -> HTTP {resp.status_code}")
    print(f"    {json.dumps(body, indent=2, sort_keys=True, default=str)}")


print("=== LIVE LOCAL DEMO — Feature 2 (Notifications) with READABLE OTP ===")
print()

# ---- wait for the backend -----------------------------------------------
for _ in range(30):
    try:
        requests.get(f"{BASE}/accounts/csrf/", timeout=4)
        break
    except requests.ConnectionError:
        time.sleep(1)
else:
    raise SystemExit("backend not reachable on 127.0.0.1:8000 — start it first")

# ---- seed an admin (dev DB) so an academic can publish --------------------
admin = User.objects.filter(role=User.Role.ADMINISTRATOR, email__endswith="@demo.test").first()
if admin is None:
    admin = User.objects.create_user(
        f"localadmin-{rnd()}@demo.test", f"localadmin-{rnd()}", "Local", "Admin",
        "StrongPass!2026", role=User.Role.ADMINISTRATOR, is_email_verified=True,
    )
print(f"Setup: admin={admin.email} password=StrongPass!2026")
print()

# --------------------------------------------------------------------------
print("STEP 1 — REGISTER (login must be blocked until OTP is entered)")
email = f"demo-{rnd()}@example.test"
register = requests.post(
    f"{BASE}/accounts/register/",
    json={
        "email": email,
        "username": f"demo-{rnd()}",
        "first_name": "Demo",
        "last_name": "User",
        "password": "StrongPass!2026",
    },
    timeout=45,
)
show("  POST /accounts/register/", register)
print()

blocked = requests.post(
    f"{BASE}/accounts/login/",
    json={"identifier": email, "password": "StrongPass!2026"},
    timeout=45,
)
show("  POST /accounts/login/ BEFORE verify (expect 403 ACCOUNT_NOT_VERIFIED)", blocked)
print()

# --------------------------------------------------------------------------
print("STEP 2 — READ THE CODE FROM THE BACKEND CONSOLE (local.dev.log)")
code = None
with open(LOG, "rb") as fh:
    raw = fh.read()
text = ""
for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
    try:
        candidate = raw.decode(enc)
        if "verification code" in candidate:
            text = candidate
            break
    except (UnicodeDecodeError, LookupError):
        continue
match = None
target = f"To: {email}"
idx = text.find(target)
if idx != -1:
    block = text[idx : idx + 2000]
    match = re.search(r"Your verification code is: (\d{6})", block)
if match:
    code = match.group(1)
    print(f"  found in runserver output: code={code}")
    print("  (in a real terminal this is the line that prints under runserver)")
else:
    # Fall back to the latest outbound email capture via the log tail.
    raise SystemExit("no 6-digit code found in local.dev.log yet")
print()

# --------------------------------------------------------------------------
print("STEP 3 — VERIFY WITH THE CODE READ FROM THE CONSOLE")
verified = requests.post(
    f"{BASE}/accounts/verify-email/",
    json={"email": email, "code": code},
    timeout=45,
)
show("  POST /accounts/verify-email/", verified)
login = requests.post(
    f"{BASE}/accounts/login/",
    json={"identifier": email, "password": "StrongPass!2026"},
    timeout=45,
)
show("  POST /accounts/login/ AFTER verify (expect 200)", login)
if login.status_code != 200:
    raise SystemExit("login-after-verify failed — aborting before inbox steps")
student_id = login.json()["data"]["id"]
print()

# --------------------------------------------------------------------------
print("STEP 4 — ADMIN PUBLISHES A COURSE ANNOUNCEMENT (real session + CSRF)")
course = Course.objects.create(code=f"DMO{rnd().upper()}", name="Local Demo Course")
Enrollment.objects.create(student=User.objects.get(id=student_id), course=course, is_active=True)
print(f"  seeded course={course.code} enrollment for {email}")

admin_session = requests.Session()
admin_login = admin_session.post(
    f"{BASE}/accounts/login/",
    json={"identifier": admin.email, "password": "StrongPass!2026"},
    timeout=45,
)
show("  POST /accounts/login/ (admin)", admin_login)
if admin_login.status_code != 200:
    raise SystemExit("admin login failed — aborting before publish")
admin_session.get(f"{BASE}/announcements/", timeout=10)  # ensure csrftoken cookie
csrftoken = admin_session.cookies.get("csrftoken")
publish = admin_session.post(
    f"{BASE}/announcements/",
    json={
        "title": "Local demo announcement",
        "body": "Feature 2 is running on your machine.",
        "scope": "course",
        "scope_id": str(course.id),
        "is_important": False,
        "published": True,
    },
    headers={"X-CSRFToken": csrftoken} if csrftoken else {},
    timeout=45,
)
show("  POST /announcements/ (published=True, fans out via BR §23)", publish)
print()

# --------------------------------------------------------------------------
print("STEP 5 — ENROLLED STUDENT SEES IT IN THE REAL INBOX")
student_session = requests.Session()
student_session.post(
    f"{BASE}/accounts/login/",
    json={"identifier": email, "password": "StrongPass!2026"},
    timeout=45,
)
inbox = student_session.get(f"{BASE}/notifications/", timeout=45)
show("  GET /notifications/ (student inbox)", inbox)
rows = inbox.json()["data"]
if not rows:
    raise SystemExit("inbox empty — announcement did not fan out (see earlier steps)")
row = rows[0]
announcement_id = publish.json()["data"]["id"]
print(
    "  ASSERT announcement in inbox:",
    row["category"] == "announcement"
    and row["body"] == "Local demo announcement"
    and str(row["related_id"]) == str(announcement_id)
    and not row["is_read"],
)
print()
print("=== DEMO COMPLETE ===")
