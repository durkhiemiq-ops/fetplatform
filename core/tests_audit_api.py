"""Read-only audit log API: admin-only access, GET-only routes (BR-211).

The console at /admin/audit calls these endpoints. The critical invariants:
ordinary users (anonymous, student, lecturer) cannot list audit records, and
no write operation exists — verified structurally by asserting POST is not
merely forbidden but unrouted (405), so audit immutability does not depend on
a permission check.
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

PASSWORD = "Str0ng!Passphrase99"


class AuditLogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "audit-admin@example.test", "audit-admin", "Au", "Dit", PASSWORD,
            role=User.Role.ADMINISTRATOR, is_email_verified=True,
        )
        cls.student = User.objects.create_user(
            "audit-student@example.test", "audit-student", "Au", "Dent", PASSWORD,
            role=User.Role.STUDENT, is_email_verified=True,
        )
        cls.lecturer = User.objects.create_user(
            "audit-lecturer@example.test", "audit-lecturer", "Au", "Cturer", PASSWORD,
            role=User.Role.LECTURER, is_email_verified=True,
        )
        AuditEvent.objects.create(
            action="role_changed", resource_type="account",
            resource_id=str(cls.student.pk), actor_id=str(cls.admin.pk),
            timestamp=timezone.now(),
        )
        AuditEvent.objects.create(
            action="course_enrolled", resource_type="enrollment",
            resource_id="11", actor_id=str(cls.student.pk),
            timestamp=timezone.now(),
        )

    def _client(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def test_anonymous_cannot_list_audit_events(self):
        # Session auth reports missing credentials as 403, matching the
        # existing anonymous-approval convention.
        self.assertEqual(self._client().get(reverse("audit-log-list")).status_code, 403)

    def test_student_cannot_list_audit_events(self):
        self.assertEqual(
            self._client(self.student).get(reverse("audit-log-list")).status_code, 403
        )

    def test_lecturer_cannot_list_audit_events(self):
        self.assertEqual(
            self._client(self.lecturer).get(reverse("audit-log-list")).status_code, 403
        )

    def test_anonymous_cannot_read_summary(self):
        self.assertEqual(self._client().get(reverse("audit-summary")).status_code, 403)

    def test_admin_lists_newest_first_inside_envelope(self):
        response = self._client(self.admin).get(reverse("audit-log-list"))
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(sorted(body), ["available_actions", "pagination", "results"])
        self.assertEqual(body["pagination"]["total"], 2)
        rows = body["results"]
        first = rows[0]
        # Console row contract: id, created_at, actor identity, action,
        # resource_type, ip_address (null until writers record it).
        self.assertEqual(
            sorted(first),
            ["action", "actor_email", "actor_full_name", "created_at",
             "id", "ip_address", "resource_id", "resource_type"],
        )
        self.assertEqual(first["actor_email"], "audit-student@example.test")
        self.assertIn("course_enrolled", body["available_actions"])
        # No credential material anywhere in the payload.
        self.assertNotIn("password", response.json().__str__().lower().replace("passphrase", ""))

    def test_admin_filters_by_action(self):
        response = self._client(self.admin).get(
            reverse("audit-log-list"), {"action": "role_changed"}
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "role_changed")

    def test_admin_reads_summary_counters(self):
        response = self._client(self.admin).get(reverse("audit-summary"))
        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        self.assertEqual(
            sorted(body),
            ["distinct_actors_24h", "events_24h", "failed_logins_24h", "total_events"],
        )
        self.assertEqual(body["total_events"], 2)
        self.assertGreaterEqual(body["events_24h"], 2)

    def test_audit_log_has_no_write_route(self):
        # BR-211 structurally: POST is unrouted (405), not merely forbidden.
        # If a write route ever appears, it must be a deliberate decision.
        response = self._client(self.admin).post(
            reverse("audit-log-list"), {"action": "forged"}, format="json"
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(AuditEvent.objects.filter(action="forged").exists())
