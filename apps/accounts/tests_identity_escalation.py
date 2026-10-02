"""Identity-escalation regression tests (BR-001, BR-002, BR-170).

Found by the Phase 0 security audit. Two defects, both about an account
rewriting its own identity:

  1. CRITICAL — `UserSerializer` left `username`, `matricule`, `staffid`,
     `faculty` and `department` writable, and that serializer backs
     `PATCH /accounts/me/`. Because `matricule`/`staffid`/`username` are LOGIN
     IDENTIFIERS, any authenticated user could claim an arbitrary identifier
     and then authenticate with it.

  2. HIGH — `FlexibleLoginBackend` resolved an identifier that matched more
     than one account with `.first()`, authenticating against an arbitrary
     account. The case-insensitive `__iexact` lookup can collide because the
     unique constraints are case-SENSITIVE. It now fails closed. The redundant
     `ModelBackend` fallback, which raised `MultipleObjectsReturned` (a 500) on
     the same input, was removed.
"""

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import User


class ProfileEscalationTests(TestCase):
    """PATCH /accounts/me/ must not let a user rewrite institution identity."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            "esc-student@example.test",
            "esc-student",
            "Esc",
            "Student",
            "StrongPass!2026",
            role=User.Role.STUDENT,
        )

    def test_student_cannot_write_staffid(self):
        """BR-001: staffid is a login identifier, registrar-assigned."""
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"), {"staffid": "LEC999-PWNED"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.staffid)

    def test_student_cannot_write_matricule(self):
        """BR-001: matricule is a login identifier, registrar-assigned."""
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"),
            {"matricule": "FE99-PWNED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.matricule)

    def test_student_cannot_write_username(self):
        """BR-001: username is a login identifier."""
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"),
            {"username": "esc-renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.username, "esc-student")

    def test_student_cannot_write_role(self):
        """BR-002/BR-210: role changes go through change-role only."""
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"),
            {"role": User.Role.ADMINISTRATOR},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)

    def test_student_cannot_write_faculty_or_department(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"),
            {"faculty": str(User.objects.none().values("id").first() or "00000000-0000-0000-0000-000000000000")},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.faculty_id)

    def test_student_can_still_edit_own_name(self):
        """Self-service profile text remains writable — the fix is not a blanket deny."""
        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("accounts:current-user"),
            {"first_name": "Renamed", "last_name": "Person"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Renamed")
        self.assertEqual(self.student.last_name, "Person")


class AmbiguousIdentifierTests(TestCase):
    """An identifier matching >1 account must fail closed, not pick one."""

    def setUp(self):
        cache.clear()
        self.a = User.objects.create_user(
            "amb-a@example.test", "amb-a", "A", "One", "StrongPass!2026"
        )
        self.a.is_email_verified = True
        self.a.role = User.Role.STUDENT
        self.a.matricule = "AMB-001"
        self.a.save()

        self.b = User.objects.create_user(
            "amb-b@example.test", "amb-b", "B", "Two", "StrongPass!2026"
        )
        self.b.is_email_verified = True
        self.b.role = User.Role.STUDENT
        # Case-only difference: permitted by the case-sensitive unique
        # constraints, but matched by the backend's __iexact lookup.
        self.b.matricule = "amb-001"
        self.b.save()

    def test_ambiguous_identifier_is_denied_not_arbitrarily_resolved(self):
        result = authenticate(username="AMB-001", password="StrongPass!2026")
        self.assertIsNone(result, "ambiguous identifier must not authenticate anyone")

    def test_ambiguous_login_does_not_raise(self):
        """Previously ModelBackend raised MultipleObjectsReturned -> HTTP 500."""
        try:
            authenticate(username="amb-001", password="StrongPass!2026")
        except Exception as exc:  # noqa: BLE001 - the point is that none escapes
            self.fail(f"login raised {type(exc).__name__} instead of failing closed")

    def test_unambiguous_logins_still_work(self):
        for user in (self.a, self.b):
            with self.subTest(user=user.email):
                result = authenticate(
                    username=user.email, password="StrongPass!2026"
                )
                self.assertIsNotNone(result)
                self.assertEqual(result.email, user.email)

    def test_login_by_matricule_still_works_when_unambiguous(self):
        unique = User.objects.create_user(
            "amb-c@example.test", "amb-c", "C", "Three", "StrongPass!2026"
        )
        unique.is_email_verified = True
        unique.role = User.Role.STUDENT
        unique.matricule = "AMB-UNIQUE"
        unique.save()
        result = authenticate(username="amb-unique", password="StrongPass!2026")
        self.assertIsNotNone(result)
        self.assertEqual(result.email, "amb-c@example.test")
