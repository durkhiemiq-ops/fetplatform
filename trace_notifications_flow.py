"""Feature 2 (Notifications) traced request/response evidence.

Walks the real DRF view stack for the API §45 inbox endpoints and proves every
wired trigger fans out exactly to the users BR §23 makes eligible:

  * announcement published -> active course enrollment (never the outsider);
  * BR-064 flag raised -> the flagged account;
  * role changed -> the target account;
  * enrollment added -> the student;
  * attendance corrected -> the record's student;
and the two audit-critical behaviours:
  * API §45 endpoints (GET list / PATCH read / POST read-all) with the exact
    §67-trimmed response shape;
  * §25 permission denial — a foreign notification's id returns the not-found
    shape, byte-identical to a uuid that never existed.

Run with the local dev settings (mirrors trace_attendance_flow.py):
    python -u trace_notifications_flow.py
"""

import json
import os
import random
import string
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
import django  # noqa: E402

django.setup()

from rest_framework.test import APIClient  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.academic.models import (  # noqa: E402
    ClassSession,
    Course,
    Department,
    Enrollment,
)
from apps.accounts.models import User  # noqa: E402
from apps.announcements.models import Announcement  # noqa: E402
from apps.attendance.models import (  # noqa: E402
    AttendanceCheckpoint,
    AttendanceRecord,
    AttendanceSession,
)
from apps.notifications.models import Notification  # noqa: E402
from apps.attendance.services.attendance_service import (  # noqa: E402
    correct_attendance,
    flag_suspicious_activity,
)
from apps.accounts.services.auth_service import change_user_role  # noqa: E402
from apps.academic.services.enrollment_service import (  # noqa: E402
    enroll_student_in_course,
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
        print(f"  {label} -> HTTP {response.status_code}")
        print(f"    {json.dumps(body, indent=2, sort_keys=True, default=str)}")
    else:
        print(f"  {label} -> HTTP {response.status_code}")
        print(f"    {json.dumps(body, indent=2, sort_keys=True, default=str)}")


# --------------------------------------------------------------------------
print("=== NOTIFICATIONS FEATURE TRACE (Feature 2) ===")
print()

# ---- Setup ---------------------------------------------------------------
print("Setup: admin, lecturer, enrolled students, outsider, department member")

admin = User.objects.create_user(
    f"admin-{rnd()}@trace.test", f"admin-{rnd()}", "Trace", "Admin",
    "StrongPass!2026", role=User.Role.ADMINISTRATOR,
)
admin.is_email_verified = True
admin.save()
lecturer = User.objects.create_user(
    f"lecturer-{rnd()}@trace.test", f"lecturer-{rnd()}", "Trace", "Lecturer",
    "StrongPass!2026", role=User.Role.LECTURER,
)
lecturer.is_email_verified = True
lecturer.save()
student = User.objects.create_user(
    f"student-{rnd()}@trace.test", f"student-{rnd()}", "Trace", "Student",
    "StrongPass!2026",
)
student.is_email_verified = True
student.save()
peer = User.objects.create_user(
    f"peer-{rnd()}@trace.test", f"peer-{rnd()}", "Trace", "Peer",
    "StrongPass!2026",
)
peer.is_email_verified = True
peer.save()
outsider = User.objects.create_user(
    f"outsider-{rnd()}@trace.test", f"outsider-{rnd()}", "Out", "Sider",
    "StrongPass!2026",
)
outsider.is_email_verified = True
outsider.save()
dept = Department.objects.create(name=f"Dept {rnd().upper()}")
dept_member = User.objects.create_user(
    f"dept-{rnd()}@trace.test", f"dept-{rnd()}", "Dept", "Member",
    "StrongPass!2026", department=dept,
)
dept_member.is_email_verified = True
dept_member.save()

course = Course.objects.create(code=f"NTF{rnd().upper()}", name="Notifications Trace")
for s in (student, peer):
    Enrollment.objects.create(student=s, course=course, is_active=True)
print(f"  course={course.code}  admin={admin.email}")
print(f"  enrolled={student.email} {peer.email}  outsider={outsider.email}")
print()

# --------------------------------------------------------------------------
# PART A — TRIGGER 1: ANNOUNCEMENT PUBLISHED (BR §23) — real HTTP publish
# --------------------------------------------------------------------------
print("PART A — ANNOUNCEMENT PUBLISHED -> ONLY ACTIVE COURSE ENROLLMENT")
admin_client = APIClient()
login = admin_client.post(
    f"{API}/accounts/login/",
    {"email": admin.email, "password": "StrongPass!2026"},
    format="json",
)
show("A1 POST /accounts/login/", login, body_only=True)

created = admin_client.post(
    f"{API}/announcements/",
    {
        "title": "Mid-semester update",
        "body": "Please check the portal.",
        "scope": "course",
        "scope_id": str(course.id),
        "is_important": False,
        "published": True,
    },
    format="json",
)
show("A2 POST /announcements/ (publish immediately)", created)
announcement_id = created.json()["data"]["id"]
print(f"  -> announcement {announcement_id}")

rows = Notification.objects.filter(category="announcement").order_by("recipient__email")
emails = [(n.recipient.email, n.title, n.related_id == str(announcement_id)) for n in rows]
print("  fan-out rows (recipient, title, links to announcement):")
for email, title, linked in emails:
    print(f"    - {email} | {title} | linked={linked}")
print(
    "  ASSERT enrolled students got it, outsider did NOT:",
    {student.email, peer.email} == {e[0] for e in emails}
    and outsider.email not in {e[0] for e in emails},
)
print()

# --------------------------------------------------------------------------
# PART B — STUDENT INBOX: API §45 endpoints, §67 shape
# --------------------------------------------------------------------------
print("PART B — STUDENT INBOX (GET / PATCH read / POST read-all)")
student_client = APIClient()
login = student_client.post(
    f"{API}/accounts/login/",
    {"email": student.email, "password": "StrongPass!2026"},
    format="json",
)
show("B1 POST /accounts/login/", login, body_only=True)

inbox = student_client.get(f"{API}/notifications/")
show("B2 GET /notifications/ (own inbox, trimmed rows)", inbox)
item = inbox.json()["data"][0]
notification_id = item["id"]
print(
    f"  row keys = {sorted(item.keys())}",
    "| EXACT §67 SET:",
    sorted(item.keys()) == sorted(
        ["id", "category", "title", "body", "related_type", "related_id",
         "is_read", "read_at", "created_at"]
    ),
)

unread = student_client.get(f"{API}/notifications/?unread=true")
print("  B3 GET /notifications/?unread=true ->", len(unread.json()["data"]), "rows")

marked = student_client.patch(f"{API}/notifications/{notification_id}/read/", {}, format="json")
show("B4 PATCH /notifications/<id>/read/", marked)

idempotent = student_client.patch(
    f"{API}/notifications/{notification_id}/read/", {}, format="json"
)
print(
    "  B5 PATCH again (idempotent):",
    idempotent.status_code,
    "read_at unchanged:",
    idempotent.json()["data"]["read_at"] == marked.json()["data"]["read_at"],
)

read_all = student_client.post(f"{API}/notifications/read-all/", {}, format="json")
show("B6 POST /notifications/read-all/", read_all)
print()

# --------------------------------------------------------------------------
# PART C — §25 PERMISSION DENIAL (foreign notification == nonexistent)
# --------------------------------------------------------------------------
print("PART C — §25 DENIAL: FOREIGN NOTIFICATION IS THE NOT-FOUND SHAPE")
peer_client = APIClient()
login = peer_client.post(
    f"{API}/accounts/login/",
    {"email": peer.email, "password": "StrongPass!2026"},
    format="json",
)
show("C1 POST /accounts/login/", login, body_only=True)

foreign = peer_client.patch(
    f"{API}/notifications/{notification_id}/read/", {}, format="json"
)
missing = peer_client.patch(
    f"{API}/notifications/00000000-0000-0000-0000-0000000000ff/read/",
    {},
    format="json",
)
show("C2 PATCH /notifications/<student's id>/read/ as peer", foreign)
show("C3 PATCH /notifications/<random uuid>/read/ as peer", missing)
print(
    "  ASSERT byte-identical bodies:",
    foreign.json() == missing.json() and foreign.status_code == missing.status_code == 404,
)
peer_inbox = peer_client.get(f"{API}/notifications/")
print(
    "  C4 peer's own inbox rows (only their announcement):",
    len(peer_inbox.json()["data"]),
)
print()

# --------------------------------------------------------------------------
# PART D — THE OTHER FOUR TRIGGERS (service-level, like the attendance trace's
# direct checkpoint calls; each proof is the recipient set + resulting row)
# --------------------------------------------------------------------------
print("PART D — BR-064 FLAG, ROLE CHANGE, ENROLLMENT, CORRECTION")

flag_suspicious_activity(
    actor_id=student.id,
    reason="repeated_invalid_attendance_scan",
    metadata={"failure_code": "TOKEN_ALREADY_USED", "request_ip": "10.0.0.7"},
)
flag_row = Notification.objects.filter(
    recipient=student, category="attendance_flag"
).latest("created_at")
print(
    f"  D1 flag -> {flag_row.recipient.email} | {flag_row.category} | "
    f"failure_code in body: {'TOKEN_ALREADY_USED' in flag_row.body}"
)

target = User.objects.create_user(
    f"target-{rnd()}@trace.test", f"target-{rnd()}", "Tar", "Get",
    "StrongPass!2026",
)
change_user_role(target, "LECTURER", actor=admin)
role_row = Notification.objects.filter(
    recipient=target, category="role_change"
).latest("created_at")
print(
    f"  D2 role changed -> {role_row.recipient.email} | {role_row.category} | "
    f"details: {role_row.body}"
)

enroll_student_in_course(
    outsider.id,
    course.id,
    EnrollmentModel=Enrollment,
    StudentModel=User,
    CourseModel=Course,
    actor_id=admin.id,
    reason="trace enrollment",
    authorization_checker=lambda **kwargs: True,
)
enroll_row = Notification.objects.filter(
    recipient=outsider, category="enrollment"
).latest("created_at")
print(
    f"  D3 enrollment -> {enroll_row.recipient.email} | {enroll_row.category} | "
    f"details: {enroll_row.body}"
)

class_session = ClassSession.objects.create(
    course=course, lecturer=lecturer, starts_at=timezone.now()
)
session = AttendanceSession.objects.create(
    class_session=class_session,
    lecturer=lecturer,
    status=AttendanceSession.Status.ACTIVE,
    expires_at=timezone.now() + timedelta(seconds=60),
)
checkpoint = AttendanceCheckpoint.objects.create(
    attendance_session=session, student=peer
)
record = AttendanceRecord.objects.create(
    attendance_session=session, student=peer, checkpoint=checkpoint
)
correct_attendance(record=record, lecturer=lecturer, reason="Marked present (trace)")
corr_row = Notification.objects.filter(
    recipient=peer, category="attendance_correction"
).latest("created_at")
print(
    f"  D4 correction -> {corr_row.recipient.email} | {corr_row.category} | "
    f"links to record: {corr_row.related_id == str(record.id)}"
)

# Department-scope announcement reaches the linked member only.
dept_created = admin_client.post(
    f"{API}/announcements/",
    {
        "title": "Department meeting",
        "body": "All staff please attend.",
        "scope": "department",
        "scope_id": str(dept.id),
        "is_important": False,
        "published": True,
    },
    format="json",
)
print(
    "  D5 department announcement -> dept member notified:",
    Notification.objects.filter(
        recipient=dept_member, category="announcement"
    ).exists(),
    "| outsider (no link) notified:",
    Notification.objects.filter(
        recipient=outsider, category="announcement"
    ).exists(),
)
print()

print("=== TRACE COMPLETE ===")
print("Total notification rows written:", Notification.objects.count())