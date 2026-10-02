"""API-contract tests: the academic endpoints the frontend actually calls.

Proves the ACADEMIC_ENDPOINTS sync: authentication is required, the standard
envelope comes back, and display names are resolved server-side so the
course catalogue needs a single request.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academic.models import Course, Department, Faculty
from apps.accounts.models import User


class AcademicApiTests(TestCase):
    def setUp(self):
        # DRF throttle counters share the default cache across tests.
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            "academic-viewer@example.test", "academic-viewer", "Acad", "Emic", "StrongPass!2026"
        )
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(
            name="Computer Science", faculty=self.faculty
        )
        self.course = Course.objects.create(
            code="FET101", name="Secure Attendance", department=self.department
        )

    def test_endpoints_require_authentication(self):
        for route in ("faculty-list", "department-list", "course-list"):
            response = self.client.get(reverse(f"academic:{route}"))
            # DRF's SessionAuthentication sends no WWW-Authenticate header, so
            # anonymous requests are 403 (same as every session-auth endpoint
            # in this codebase), wrapped in the standard envelope.
            self.assertEqual(response.status_code, 403, route)
            self.assertEqual(response.data["error"]["code"], "FORBIDDEN", route)
            self.assertFalse(response.data["success"], route)

    def test_faculty_list_returns_standard_envelope(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("academic:faculty-list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(
            response.data["data"],
            [{"id": str(self.faculty.id), "name": "Engineering"}],
        )

    def test_department_list_resolves_faculty_name(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("academic:department-list"))
        self.assertEqual(response.status_code, 200)
        row = response.data["data"][0]
        self.assertEqual(row["name"], "Computer Science")
        # Pre-render .data holds the UUID object; JSON rendering stringifies it.
        self.assertEqual(str(row["faculty"]), str(self.faculty.id))
        self.assertEqual(row["faculty_name"], "Engineering")

    def test_course_list_resolves_department_and_faculty_names(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("academic:course-list"))
        self.assertEqual(response.status_code, 200)
        row = response.data["data"][0]
        self.assertEqual(row["code"], "FET101")
        self.assertEqual(row["name"], "Secure Attendance")
        self.assertEqual(row["department_name"], "Computer Science")
        self.assertEqual(row["faculty_name"], "Engineering")

    def test_orphan_course_without_department_returns_nulls(self):
        Course.objects.create(code="FET000", name="Unattached Course")
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("academic:course-list"))
        orphan = next(r for r in response.data["data"] if r["code"] == "FET000")
        self.assertIsNone(orphan["department_name"])
        self.assertIsNone(orphan["faculty_name"])
