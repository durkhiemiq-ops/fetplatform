"""Calendar API tests: reads open to authenticated users, writes admin-only."""

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent
from apps.academic.models import ClassSession, Course, Enrollment, Faculty, Semester

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
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status="active",
            is_active=True,
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

    def test_class_list_hides_unenrolled_courses_and_unassigned_lecturers(self):
        other_lecturer = User.objects.create_user(
            "other-lecturer@example.test",
            "other-lecturer",
            "Other",
            "Lecturer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        other_course = Course.objects.create(code="FET999", name="Private Class")
        other_session = ClassSession.objects.create(
            course=other_course,
            lecturer=other_lecturer,
            starts_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.student)
        student_rows = self.client.get(reverse("academic:class-list")).data["data"]
        self.assertEqual({row["id"] for row in student_rows}, {str(self.session.id)})

        self.client.force_authenticate(user=self.lecturer)
        lecturer_rows = self.client.get(reverse("academic:class-list")).data["data"]
        self.assertEqual({row["id"] for row in lecturer_rows}, {str(self.session.id)})
        self.assertNotIn(str(other_session.id), {row["id"] for row in lecturer_rows})

    def test_students_cannot_write_calendar(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:school-year-list"),
            {"name": "2030/2031", "start_date": "2030-09-01", "end_date": "2031-07-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_calendar_write_rejects_unknown_and_read_only_fields(self):
        self.client.force_authenticate(user=self.admin)
        unknown = self.client.post(
            reverse("academic:school-year-list"),
            {
                "name": "2031/2032",
                "start_date": "2031-09-01",
                "end_date": "2032-07-31",
                "owner": str(self.student.id),
            },
            format="json",
        )
        forged_id = self.client.post(
            reverse("academic:school-year-list"),
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "2032/2033",
                "start_date": "2032-09-01",
                "end_date": "2033-07-31",
            },
            format="json",
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(forged_id.status_code, 400)

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
        self.assertEqual(second.status_code, 201, second.data)

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

    def test_admin_activation_endpoint_is_audited(self):
        year = self.client.force_authenticate(user=self.admin)
        from apps.academic.models import SchoolYear

        school_year = SchoolYear.objects.create(
            name="2027/2028",
            start_date="2027-09-01",
            end_date="2028-07-31",
        )
        first = Semester.objects.create(
            school_year=school_year,
            name="Semester 1",
            start_date="2027-09-01",
            end_date="2028-01-31",
            is_current=True,
        )
        second = Semester.objects.create(
            school_year=school_year,
            name="Semester 2",
            start_date="2028-02-01",
            end_date="2028-07-31",
        )

        response = self.client.post(
            reverse("academic:semester-activate", kwargs={"pk": second.pk})
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="semester_activated", resource_id=str(second.pk)
            ).exists()
        )

    def test_non_admin_cannot_activate_semester(self):
        from apps.academic.models import SchoolYear

        school_year = SchoolYear.objects.create(
            name="2028/2029",
            start_date="2028-09-01",
            end_date="2029-07-31",
        )
        semester = Semester.objects.create(
            school_year=school_year,
            name="Semester 1",
            start_date="2028-09-01",
            end_date="2029-01-31",
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:semester-activate", kwargs={"pk": semester.pk})
        )
        self.assertEqual(response.status_code, 403)
        semester.refresh_from_db()
        self.assertFalse(semester.is_current)

    def test_database_rejects_multiple_current_semesters_even_via_update(self):
        from apps.academic.models import SchoolYear

        school_year = SchoolYear.objects.create(
            name="2029/2030",
            start_date="2029-09-01",
            end_date="2030-07-31",
        )
        first = Semester.objects.create(
            school_year=school_year,
            name="Semester 1",
            start_date="2029-09-01",
            end_date="2030-01-31",
            is_current=True,
        )
        second = Semester.objects.create(
            school_year=school_year,
            name="Semester 2",
            start_date="2030-02-01",
            end_date="2030-07-31",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Semester.objects.filter(pk=second.pk).update(is_current=True)
        self.assertTrue(Semester.objects.get(pk=first.pk).is_current)
        self.assertFalse(Semester.objects.get(pk=second.pk).is_current)
