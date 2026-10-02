from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User


class AccountsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            "student@example.test",
            "student",
            "Stu",
            "Dent",
            "StrongPass!2026",
        )
        self.admin = User.objects.create_user(
            "admin@example.test",
            "admin",
            "Ad",
            "Min",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )

    def test_registration_defaults_to_student_and_rejects_duplicate_email(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "new@example.test",
                "username": "new-user",
                "first_name": "New",
                "last_name": "User",
                "password": "StrongPass!2026",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["role"], User.Role.STUDENT)

        duplicate = self.client.post(
            reverse("accounts:register"),
            {
                "email": "new@example.test",
                "username": "another-user",
                "first_name": "New",
                "last_name": "User",
                "password": "StrongPass!2026",
            },
            format="json",
        )
        # BR-203: duplicate-email failure is indistinguishable from a generic
        # validation failure — same 400 status, same envelope, same code.
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.data["error"]["code"], "INVALID_DATA")

    def test_duplicate_email_is_indistinguishable_from_validation_failure(self):
        # Valid registration payload -> account created.
        first = self.client.post(
            reverse("accounts:register"),
            {
                "email": "taken@example.test",
                "username": "taken-user",
                "first_name": "Take",
                "last_name": "N",
                "password": "StrongPass!2026",
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201)

        # Duplicate email on an otherwise-valid payload.
        duplicate = self.client.post(
            reverse("accounts:register"),
            {
                "email": "taken@example.test",
                "username": "someone-else",
                "first_name": "Some",
                "last_name": "Else",
                "password": "StrongPass!2026",
            },
            format="json",
        )
        # Plain validation failure (short password) on the same endpoint.
        malformed = self.client.post(
            reverse("accounts:register"),
            {
                "email": "unused@example.test",
                "username": "fresh-user",
                "first_name": "Fresh",
                "last_name": "User",
                "password": "short",
            },
            format="json",
        )

        # Same status, same envelope keys, same error code — an observer
        # cannot tell which failure is which.
        self.assertEqual(duplicate.status_code, malformed.status_code)
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(set(duplicate.data.keys()), {"success", "error"})
        self.assertEqual(set(malformed.data.keys()), {"success", "error"})
        self.assertEqual(duplicate.data["success"], malformed.data["success"])
        self.assertEqual(duplicate.data["error"]["code"], malformed.data["error"]["code"])
        self.assertEqual(duplicate.data["error"]["code"], "INVALID_DATA")

    def test_invalid_login_is_rejected(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.student.email, "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"]["code"], "INVALID_CREDENTIALS")

    def test_non_admin_cannot_change_role(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("accounts:change-role"),
            {"user_id": str(self.student.id), "new_role": User.Role.LECTURER},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)

    def test_admin_can_change_another_users_role(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("accounts:change-role"),
            {"user_id": str(self.student.id), "new_role": User.Role.LECTURER},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.LECTURER)
