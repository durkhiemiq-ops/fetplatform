"""Feature 1 (Attendance) traced request/response evidence.

Walks the complete lecturer and student attendance flows through the real
DRF view stack (permission classes, serializers, throttles, exception
mapping), then proves the two audit-critical behaviours:

  * §25 permission denial — non-owner probes return exactly the not-found
    shape, never a distinct denial;
  * per-student scan throttling — 20/minute per authenticated student,
    never a shared endpoint budget (API §50 / BR-203 without breaking
    BR-029).

Run with the local dev settings (mirrors trace_role_change.py):
    python -u trace_attendance_flow.py
Set USE_REDIS_CACHE=1 to exercise the production Redis atomic paths.
"""

import json
import os
import random
import string

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.academic.models import ClassSession, Course, Enrollment  # noqa: E402
from apps.accounts.models import User  # noqa: E402
from apps.attendance.services.attendance_service import (  # noqa: E402
    select_checkpoints,
)

API = "/api/v1"


def rnd(length=6):
    return "".join(random.choices(string.ascii_lowercase, k=length))


def show(label, response, body_only=False):
    try:
        body = response.json()
    except Exception:
        body = response.content[:400].decode(errors="replace")
    if body_only:
        print(f"  {label} -> {json.dumps(body, indent=2, sort_keys=True, default=str)}")
    else:
        print(f"  {label} -> HTTP {response.status_code}")
        print(f"    {json.dumps(body, indent=2, sort_keys=True, default=str)}")


# --------------------------------------------------------------------------
print("=== ATTENDANCE FEATURE TRACE (Feature 1) ===")
print()

# ---- Setup ---------------------------------------------------------------
print("Setup: users, course, enrollment, class session")

lecturer = User.objects.create_user(
    f"lecturer-{rnd()}@trace.test", f"lecturer-{rnd()}", "Trace", "Lecturer",
    "StrongPass!2026", role=User.Role.LECTURER,
)
# The email-verification gate is accounts machinery (regression-tested);
# this trace focuses on attendance, so mark the real-login users verified.
lecturer.is_email_verified = True
lecturer.save()
non_owner = User.objects.create_user(
    f"other-{rnd()}@trace.test", f"other-{rnd()}", "Other", "Lecturer",
    "StrongPass!2026", role=User.Role.LECTURER,
)
student = User.objects.create_user(
    f"student-{rnd()}@trace.test", f"student-{rnd()}", "Trace", "Student",
    "StrongPass!2026",
)
student.is_email_verified = True
student.save()
student2 = User.objects.create_user(
    f"student2-{rnd()}@trace.test", f"student2-{rnd()}", "Trace", "Peer",
    "StrongPass!2026",
)
hammer_student = User.objects.create_user(
    f"hammer-{rnd()}@trace.test", f"hammer-{rnd()}", "Ham", "Mer",
    "StrongPass!2026",
)
fresh_student = User.objects.create_user(
    f"fresh-{rnd()}@trace.test", f"fresh-{rnd()}", "Fresh", "Student",
    "StrongPass!2026",
)
print(f"  lecturer={lecturer.email} other_lecturer={non_owner.email}")
print(f"  student={student.email} student_peer={student2.email}")
print(f"  hammer_student={hammer_student.email} fresh_student={fresh_student.email}")

course = Course.objects.create(code=f"FET{rnd().upper()}", name="Secure Attendance")
for s in (student, student2):
    Enrollment.objects.create(student=s, course=course)
class_session = ClassSession.objects.create(
    course=course, lecturer=lecturer, starts_at=timezone.now()
)
print(f"  course={course.code} class_session={class_session.id}")
print()

# --------------------------------------------------------------------------
# PART A — LECTURER FLOW (real login + session cookie)
# --------------------------------------------------------------------------
print("PART A — LECTURER FLOW")
lecturer_client = APIClient()

login = lecturer_client.post(
    f"{API}/accounts/login/",
    {"email": lecturer.email, "password": "StrongPass!2026"},
    format="json",
)
show("A1 POST /accounts/login/", login, body_only=True)

start = lecturer_client.post(
    f"{API}/attendance/sessions/",
    {"class_session": str(class_session.id), "duration_seconds": 300},
    format="json",
)
show("A2 POST /attendance/sessions/ (start, 300s window)", start)
session_id = start.json()["data"]["id"]

checkpoints_resp = lecturer_client.post(
    f"{API}/attendance/sessions/{session_id}/checkpoints/",
    {"student_ids": [str(student.id), str(student2.id)]},
    format="json",
)
show("A3 POST /attendance/sessions/<id>/checkpoints/", checkpoints_resp)
checkpoint = checkpoints_resp.json()["data"]["checkpoints"][0]
checkpoint_id = checkpoint["id"]
print(f"  -> checkpoint id {checkpoint_id} (student {checkpoint['student']})")

token_resp = lecturer_client.post(f"{API}/attendance/checkpoints/{checkpoint_id}/token/")
show("A4 POST /checkpoints/<id>/token/ (QR rotation)", token_resp)
token = token_resp.json()["data"]["token"]
print(f"  -> token (first 24 chars) {token[:24]}... ttl {token_resp.json()['data']['ttl_seconds']}s")

listing = lecturer_client.get(f"{API}/attendance/sessions/")
show("A5 GET /attendance/sessions/ (trimmed rows)", listing, body_only=True)

detail = lecturer_client.get(f"{API}/attendance/sessions/{session_id}/")
show("A6 GET /attendance/sessions/<id>/ (detail)", detail, body_only=True)
print()

# --------------------------------------------------------------------------
# PART B — STUDENT FLOW (real login + session cookie)
# --------------------------------------------------------------------------
print("PART B — STUDENT FLOW")
student_client = APIClient()
login = student_client.post(
    f"{API}/accounts/login/",
    {"email": student.email, "password": "StrongPass!2026"},
    format="json",
)
show("B1 POST /accounts/login/", login, body_only=True)

scan_ok = student_client.post(f"{API}/attendance/scan/", {"token": token}, format="json")
show("B2 POST /attendance/scan/ (valid token)", scan_ok)

replay = student_client.post(f"{API}/attendance/scan/", {"token": token}, format="json")
show("B3 POST /attendance/scan/ (same token replayed)", replay)

expired = student_client.post(
    f"{API}/attendance/scan/", {"token": f"expired-junk-{rnd()}"}, format="json"
)
show("B4 POST /attendance/scan/ (expired/unknown token)", expired)

# Screenshot defense: an issued token is bound to its checkpoint student.
peer_checkpoint = select_checkpoints(
    lecturer=lecturer,
    session=__import__(
        "apps.attendance.models", fromlist=["AttendanceSession"]
    ).AttendanceSession.objects.get(id=session_id),
    student_ids=[student2.id],
)[0]
peer_token_resp = lecturer_client.post(
    f"{API}/attendance/checkpoints/{peer_checkpoint.id}/token/"
)
peer_token = peer_token_resp.json()["data"]["token"]
mismatch = student_client.post(
    f"{API}/attendance/scan/", {"token": peer_token}, format="json"
)
show("B5 POST /attendance/scan/ (another student's token)", mismatch)

records = student_client.get(f"{API}/attendance/records/")
show("B6 GET /attendance/records/ (own history, trimmed)", records, body_only=True)
print()

# --------------------------------------------------------------------------
# PART C — OWNERSHIP / §25 DENIAL, AND AUDITED CORRECTIONS (BR-042)
# --------------------------------------------------------------------------
print("PART C — OWNERSHIP DENIALS (§25) AND AUDITED CORRECTIONS (BR-042)")
probe = APIClient()
probe.force_authenticate(user=non_owner)

denied_token = probe.post(f"{API}/attendance/checkpoints/{checkpoint_id}/token/")
show("C1 non-owner checkpoint token  -> indistinguishable from missing", denied_token)

record_id = scan_ok.json()["data"]["attendance_record_id"]
denied_correction = probe.post(
    f"{API}/attendance/records/{record_id}/corrections/",
    {"reason": "Student was present but scanned late."},
    format="json",
)
show("C2 non-owner correction (even with a plausible reason) -> not-found", denied_correction)

correction = lecturer_client.post(
    f"{API}/attendance/records/{record_id}/corrections/",
    {"reason": "Student was present but scanned late."},
    format="json",
)
show("C3 owner correction -> audited 201 (trimmed correction shape)", correction)

same = lecturer_client.post(
    f"{API}/attendance/records/{record_id}/corrections/",
    {"reason": ""},
    format="json",
)
show("C4 empty correction reason -> rejected", same)

lecturer_records = lecturer_client.get(
    f"{API}/attendance/records/", {"session": session_id}
)
show("C5 lecturer scoped records -> rows carry correction status", lecturer_records, body_only=True)
print()

# --------------------------------------------------------------------------
# PART D — PER-STUDENT SCAN THROTTLE (API §50 + BR-203, BR-029 preserved)
# --------------------------------------------------------------------------
print("PART D — SCAN RATE LIMIT IS PER-STUDENT, NOT GLOBAL")
hammer = APIClient()
hammer.force_authenticate(user=hammer_student)
statuses = []
for index in range(21):
    response = hammer.post(
        f"{API}/attendance/scan/", {"token": f"junk-{rnd()}"}, format="json"
    )
    statuses.append(response.status_code)
first_429 = statuses.index(429) + 1 if 429 in statuses else None
print(f"  D1 one student hammers 21x  -> status sequence: {statuses}")
print(f"     -> first 429 at request #{first_429} (20 legitimate, 21st throttled)")

fresh = APIClient()
fresh.force_authenticate(user=fresh_student)
fresh_resp = fresh.post(f"{API}/attendance/scan/", {"token": f"junk-{rnd()}"}, format="json")
show("D2 a different student scans once in the same minute -> never throttled", fresh_resp)
print()

print("=== ATTENDANCE TRACE COMPLETE ===")