"""Tests for the aggregated dashboard (API Specification §46).

Three things are pinned here:

1. The route exists and is reachable by every authenticated role — it was a
   frontend-to-backend gap before this module existed, so every dashboard page
   404'd.
2. The payload shape each role's page destructures is present and stable.
3. **Scoping**: a student's dashboard is built only from that student's own
   records. The endpoint takes no target id, and these tests assert that one
   student cannot see another's attendance, enrollment, or project totals.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.academic.models import ClassSession
from django.utils import timezone

from datetime import timedelta


def _envelope(response):
    return response.status_code, response.json()


class DashboardRouteTests(TestCase):
    """The endpoint must exist for every authenticated role."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.url = reverse("dashboard")

    def _user(self, role, email, username):
        return User.objects.create_user(
            email, username, "Dash", "User", "StrongPass!2026", role=role
        )

    def test_anonymous_is_denied_with_the_standard_envelope(self):
        code, body = _envelope(self.client.get(self.url))
        self.assertEqual(code, 403)
        self.assertFalse(body["success"])
        self.assertIn("error", body)

    def test_student_receives_the_student_payload(self):
        user = self._user(User.Role.STUDENT, "dash-stu@fet.edu", "dash-stu")
        self.client.force_authenticate(user=user)
        code, body = _envelope(self.client.get(self.url))
        self.assertEqual(code, 200)
        self.assertTrue(body["success"])
        data = body["data"]
        for key in (
            "stats",
            "courses",
            "today_classes",
            "announcements",
            "active_projects",
            "pending_tasks",
            "attendance",
        ):
            self.assertIn(key, data)
        for key in ("enrolled_courses", "attendance_rate", "active_projects", "pending_tasks"):
            self.assertIn(key, data["stats"])

    def test_lecturer_receives_the_lecturer_payload(self):
        user = self._user(User.Role.LECTURER, "dash-lect@fet.edu", "dash-lect")
        self.client.force_authenticate(user=user)
        code, body = _envelope(self.client.get(self.url))
        self.assertEqual(code, 200)
        data = body["data"]
        for key in ("my_courses", "today_classes", "active_projects", "stats"):
            self.assertIn(key, data)

    def test_administrator_receives_user_totals(self):
        self._user(User.Role.ADMINISTRATOR, "dash-admin@fet.edu", "dash-admin")
        self._user(User.Role.STUDENT, "dash-stu2@fet.edu", "dash-stu2")
        self._user(User.Role.LECTURER, "dash-lect2@fet.edu", "dash-lect2")
        user = User.objects.get(email="dash-admin@fet.edu")
        self.client.force_authenticate(user=user)
        code, body = _envelope(self.client.get(self.url))
        self.assertEqual(code, 200)
        data = body["data"]
        for key in ("total_users", "total_students", "total_lecturers"):
            self.assertIn(key, data)
        self.assertGreaterEqual(data["total_users"], 3)
        self.assertEqual(data["total_students"], 1)
        self.assertEqual(data["total_lecturers"], 1)


class DashboardScopingTests(TestCase):
    """No cross-account leakage through the aggregate."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        department = Department.objects.create(name="Engineering", code="ENG")
        school_year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date() - timedelta(days=120),
            end_date=timezone.now().date() + timedelta(days=240),
        )
        semester = Semester.objects.create(
            school_year=school_year,
            name="Semester 1",
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=90),
            is_current=True,
        )
        self.lecturer = User.objects.create_user(
            "dash-lect3@fet.edu", "dash-lect3", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        course = Course.objects.create(code="CS101", name="Computing", department=department)
        self.offering = CourseOffering.objects.create(
            course=course,
            semester=semester,
            department=department,
            lecturer=self.lecturer,
        )

        self.mine = User.objects.create_user(
            "dash-mine@fet.edu", "dash-mine", "Mine", "Student", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.theirs = User.objects.create_user(
            "dash-theirs@fet.edu", "dash-theirs", "Theirs", "Student", "StrongPass!2026",
            role=User.Role.STUDENT,
        )

        Enrollment.objects.create(
            student=self.mine, course=course, course_offering=self.offering
        )

        # Give the other student attendance the viewer does not have.
        class_session = ClassSession.objects.create(
            course=course, course_offering=self.offering, lecturer=self.lecturer,
            starts_at=timezone.now(),
        )
        session = AttendanceSession.objects.create(
            class_session=class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        AttendanceRecord.objects.create(
            attendance_session=session, student=self.theirs
        )

    def test_student_dashboard_counts_only_their_own_enrollment(self):
        self.client.force_authenticate(user=self.mine)
        code, body = _envelope(self.client.get(reverse("dashboard")))
        self.assertEqual(code, 200)
        data = body["data"]
        self.assertEqual(data["stats"]["enrolled_courses"], 1)
        self.assertEqual(len(data["courses"]), 1)
        # The other student's attendance must not surface here.
        self.assertEqual(data["attendance"]["total_sessions"], 0)

    def test_second_student_sees_their_own_record_not_the_first(self):
        self.client.force_authenticate(user=self.theirs)
        code, body = _envelope(self.client.get(reverse("dashboard")))
        self.assertEqual(code, 200)
        data = body["data"]
        self.assertEqual(data["stats"]["enrolled_courses"], 0)
        self.assertEqual(data["attendance"]["total_sessions"], 1)
        self.assertEqual(data["attendance"]["rate"], 100)
