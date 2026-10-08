"""Query-count regression test for the staff classroom card.

``ClassroomListView._staff_body`` renders ``enrolled_students`` per offering.
A per-row ``COUNT`` issues one query per offering; the grouped
``_enrollment_counts`` keeps the card at a constant cost. This test pins the
scaling property: tripling the offerings must not add a query, and the
per-offering figures must stay right.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User

from .models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)


class ClassroomStaffCardQueryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.department = Department.objects.create(name="Engineering", code="ENG")
        year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date() - timedelta(days=100),
            end_date=timezone.now().date() + timedelta(days=200),
        )
        self.semester = Semester.objects.create(
            school_year=year,
            name="Semester 1",
            start_date=timezone.now().date() - timedelta(days=20),
            end_date=timezone.now().date() + timedelta(days=80),
            is_current=True,
        )
        self.lecturer = User.objects.create_user(
            "cc-lect@fet.edu", "cc-lect", "Cc", "Lect", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "cc-stu@fet.edu", "cc-stu", "Cc", "Stu", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.client.force_authenticate(user=self.lecturer)
        self.url = reverse("academic:classroom-list")

    def make_offering(self, code):
        course = Course.objects.create(
            code=code, name=f"Course {code}", department=self.department
        )
        offering = CourseOffering.objects.create(
            course=course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        Enrollment.objects.create(
            student=self.student, course=course, course_offering=offering
        )
        return offering

    def get_courses(self):
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        return len(context), response.json()["data"]["courses"]

    def test_staff_card_cost_is_constant_in_offering_count(self):
        self.make_offering("CC401")
        small_queries, small_courses = self.get_courses()
        self.assertEqual(len(small_courses), 1)
        self.assertEqual(small_courses[0]["enrolled_students"], 1)

        self.make_offering("CC402")
        self.make_offering("CC403")
        large_queries, large_courses = self.get_courses()
        self.assertEqual(len(large_courses), 3)
        self.assertTrue(
            all(course["enrolled_students"] == 1 for course in large_courses)
        )
        # Tripling the offerings must not add a single query.
        self.assertEqual(small_queries, large_queries)
        self.assertLessEqual(large_queries, 14)
