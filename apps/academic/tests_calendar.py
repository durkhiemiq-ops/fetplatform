"""Calendar API tests: reads open to authenticated users, writes admin-only."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import ClassSession, Course, Faculty, Semester

from .models import Faculty as _UnusedFaculty  # noqa: F401  (models package sanity)


class CalendarApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.student = User.objects.create_user(
            "calendar-student@example.test", "cal-student", "Cal", "Endar", "StrongPass!2026"
        )
        self.admin = User.objects.create_user(
            "admin@example.test",
            "admin",
            "Ad",
            "Min",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.lecturer = User.objects.create_user(
            "cal-lect@example.test", "cal-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")
        self.session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )

    def test_requires_authentication(self):
        response = self.client.get(reverse("academic:school-year-list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_reads_open_to_students(self):
        self.client.force_authenticate(user=self.student)
        for route in ("school-year-list", "semester-list", "class-list"):
            response = self.client.get(reverse(f"academic:{route}"))
            self.assertEqual(response.status_code, 200, route)
        classes = self.client.get(reverse("academic:class-list")).data["data"]
        self.assertEqual(classes[0]["course_code"], "FET101")
        self.assertEqual(classes[0]["lecturer_name"], "Lect Urer")

    def test_students_cannot_write_calendar(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:school-year-list"),
            {"name": "2030/2031", "start_date": "2030-09-01", "end_date": "2031-07-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_admin_calendar_and_single_current_semester(self):
        self.client.force_authenticate(user=self.admin)
        year_response = self.client.post(
            reverse("academic:school-year-list"),
            {"name": "2025/2026", "start_date": "2025-09-01", "end_date": "2026-07-31"},
            format="json",
        )
        self.assertEqual(year_response.status_code, 201)
        year_id = year_response.data["data"]["id"]

        first = self.client.post(
            reverse("academic:semester-list"),
            {
                "school_year": year_id,
                "name": "Semester 1",
                "start_date": "2025-09-01",
                "end_date": "2026-01-31",
                "is_current": True,
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            reverse("academic:semester-list"),
            {
                "school_year": year_id,
                "name": "Semester 2",
                "start_date": "2026-02-01",
                "end_date": "2026-07-31",
                "is_current": True,
            },
            format="json",
        )
        self.assertEqual(second.status_code, 201)

        # Exactly one semester may claim "current" platform-wide.
        self.assertFalse(Semester.objects.get(name="Semester 1").is_current)
        self.assertTrue(Semester.objects.get(name="Semester 2").is_current)

    def test_invalid_date_range_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("academic:school-year-list"),
            {"name": "Bad/Year", "start_date": "2026-01-01", "end_date": "2025-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
