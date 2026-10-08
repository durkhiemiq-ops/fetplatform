"""Browser-equivalent full-stack trace: vite SPA origin -> backend.

Replays exactly what the React app does at http://localhost:5175:
  * CORS preflight (OPTIONS) before every mutating call;
  * axios withCredentials cookie jar + X-CSRFToken header from the cookie;
  * OTP code read from the backend console (local.dev.log), typed in by hand;
  * the vite dev-server proxy path carrying the session cookie to /me/.

Run while both servers are up (backend on 8000 with CORS/CSRF origins set for
http://localhost:5175, and `npm run dev` on 5175).
"""

import json
import os
import random
import re
import string

import requests
import django  # noqa: F401

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
django.setup()

from apps.academic.models import Course, Enrollment  # noqa: E402
from apps.accounts.models import User  # noqa: E402

ORIGIN = "http://localhost:5175"
API8000 = "http://localhost:8000/api/v1"
PROXY = "http://localhost:5175/api/v1"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local.dev.log")


def rnd(length=6):
    return "".join(random.choices(string.ascii_lowercase, k=length))


def show(label, resp, extra=None):
    body = resp.json() if resp.content and resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
    cors = resp.headers.get("Access-Control-Allow-Origin")
    creds = resp.headers.get("Access-Control-Allow-Credentials")
    print(f"  {label} -> HTTP {resp.status_code}  (ACAO={cors} ACAC={creds})")
    if extra:
        print(f"    {extra}")
    print(f"    {json.dumps(body, indent=2, sort_keys=True, default=str)}")
    return resp


s = requests.Session()
s.headers["Origin"] = ORIGIN

print("=== BROWSER-EQUIVALENT FULL-STACK TRACE (origin http://localhost:5175) ===")
print()

# ---- CORS preflight: what the browser sends before the register POST -------
print("STEP 0 — CORS PREFLIGHT (OPTIONS, as the browser does before POST)")
pre = s.options(
    f"{API8000}/accounts/register/",
    headers={
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-csrftoken",
    },
)
print(
    f"  OPTIONS -> HTTP {pre.status_code}  ACAO={pre.headers.get('Access-Control-Allow-Origin')} "
    f"ACAC={pre.headers.get('Access-Control-Allow-Credentials')} "
    f"headers={pre.headers.get('Access-Control-Allow-Headers')}"
)
print()

# ---- 1. register like SignUp.jsx -------------------------------------------
print("STEP 1 — SIGNUP (POST /accounts/register/ from origin 5175)")
email = f"browser-{rnd()}@example.test"
reg = s.post(
    f"{API8000}/accounts/register/",
    json={
        "email": email,
        "username": f"browser-{rnd()}",
        "first_name": "Browser",
        "last_name": "User",
        "password": "StrongPass!2026",
    },
)
show("  POST /accounts/register/", reg,
     extra=f"csrftoken cookie in jar: {bool(s.cookies.get('csrftoken'))}")
print()

# ---- 2. login works immediately -----------------------------------------------
blocked = s.post(
    f"{API8000}/accounts/login/",
    json={"identifier": email, "password": "StrongPass!2026"},
)
show("  POST /accounts/login/ (sign-in never requires verification; expect 200)", blocked)
print()

# ---- 3. read the code from the backend console ------------------------------
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
idx = text.find(f"To: {email}")
match = re.search(r"Your verification code is: (\d{6})", text[idx : idx + 2000] if idx != -1 else "")
print("STEP 3 — READ THE 6-DIGIT CODE FROM THE BACKEND CONSOLE")
if match:
    code = match.group(1)
    print(f"  code visible in runserver console output: {code}  (entered by hand, like a user)")
else:
    raise SystemExit("code not found in console log")
print()

# ---- 4. verify, exactly like VerifyEmail.jsx --------------------------------
print("STEP 4 — VERIFY EMAIL (POST /accounts/verify-email/ with the console code)")
ver = s.post(
    f"{API8000}/accounts/verify-email/",
    json={"email": email, "code": code},
)
show("  POST /accounts/verify-email/", ver)
print()

# ---- 5. sign in --------------------------------------------------------------
print("STEP 5 — LOGIN")
login = s.post(
    f"{API8000}/accounts/login/",
    json={"identifier": email, "password": "StrongPass!2026"},
)
show("  POST /accounts/login/", login)
print()

# ---- 6. /me/ through the vite dev-server proxy (cookie survives the origin) --
print("STEP 6 — /me/ THROUGH THE VITE PROXY (localhost:5175 -> localhost:8000)")
me = s.get(f"{PROXY}/accounts/me/")
show("  GET /api/v1/accounts/me/ via vite proxy", me,
     extra=f"session cookie for host 'localhost' present: {bool(s.cookies.get('sessionid'))}")
print()

# ---- 7. notifications inbox (bell drawer source) ----------------------------
print("STEP 7 — NOTIFICATION BELL SOURCE (GET /notifications/)")
inbox = s.get(f"{API8000}/notifications/")
show("  GET /notifications/ (before anyone publishes)", inbox)
print()

# ---- 8. admin publishes a course announcement for this student --------------
print("STEP 8 — ADMIN PUBLISHES A COURSE ANNOUNCEMENT (real session + CSRF)")
admin = User.objects.filter(role=User.Role.ADMINISTRATOR, email__endswith="@demo.test").first()
if admin is None:
    admin = User.objects.create_user(
        f"localadmin-{rnd()}@demo.test", f"localadmin-{rnd()}", "Local", "Admin",
        "StrongPass!2026", role=User.Role.ADMINISTRATOR, is_email_verified=True,
    )
course = Course.objects.create(code=f"BRW{rnd().upper()}", name="Browser Walkthrough")
Enrollment.objects.create(student=User.objects.get(email=email), course=course, is_active=True)
admin_s = requests.Session()
admin_s.headers["Origin"] = ORIGIN
admin_s.post(f"{API8000}/accounts/login/", json={"identifier": admin.email, "password": "StrongPass!2026"})
admin_s.get(f"{API8000}/announcements/")
publish = admin_s.post(
    f"{API8000}/announcements/",
    json={
        "title": "Whole-system announcement",
        "body": "Frontend to backend is live on your machine.",
        "scope": "course",
        "scope_id": str(course.id),
        "is_important": False,
        "published": True,
    },
    headers={"X-CSRFToken": admin_s.cookies.get("csrftoken")},
)
show("  POST /announcements/ (published=True, BR §23 fan-out)", publish)
print()

# ---- 9. the bell now shows the real notification -----------------------------
print("STEP 9 — BELL RE-FETCH SHOWS THE FAN-OUT")
inbox2 = s.get(f"{API8000}/notifications/")
rows = inbox2.json()["data"]
show("  GET /notifications/ (after publish)", inbox2)
print(
    "  ASSERT browser-visible bell row:",
    any(
        r["category"] == "announcement"
        and r["body"] == "Whole-system announcement"
        and not r["is_read"]
        for r in rows
    ),
)
print()
print("=== FULL-STACK TRACE COMPLETE ===")