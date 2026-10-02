"""API tests: BR-083-adjacent student directory access (assessment and
membership pickers).

Any academic user (lecturer/administrator) may list students with minimal
identity fields; ordinary students and anonymous callers may not.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import User


class StudentListViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.lecturer = User.objects.create_user(
            "stu-dir-lect@example.test",
            "stu-dir-lect",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "stu-dir-student@example.test",
            "stu-dir-student",
            "Stu",
            "Dent",
            "StrongPass!2026",
        )
        self.admin = User.objects.create_user(
            "stu-dir-admin@example.test",
            "stu-dir-admin",
            "Ad",
            "Min",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )

    def test_requires_authentication(self):
        response = self.client.get(reverse("accounts:student-list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_students_cannot_list_students(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("accounts:student-list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_lecturer_and_admin_can_list_students_with_minimal_fields(self):
        for actor in (self.lecturer, self.admin):
            self.client.force_authenticate(user=actor)
            response = self.client.get(reverse("accounts:student-list"))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["success"])
            rows = response.data["data"]
            usernames = {row["username"] for row in rows}
            # Only role=STUDENT accounts appear, with identity-only fields —
            # no emails or password material leak to the picker consumer.
            self.assertIn("stu-dir-student", usernames)
            self.assertNotIn("stu-dir-lect", usernames)
            self.assertNotIn("stu-dir-admin", usernames)
            for row in rows:
                self.assertEqual(
                    set(row.keys()), {"id", "first_name", "last_name", "username"}
                )
