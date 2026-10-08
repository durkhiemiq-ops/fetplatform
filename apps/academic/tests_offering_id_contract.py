"""The lecturer course list must address an offering the way the client does.

``GET /api/v1/lecturers/me/courses/`` serializes offerings through
``CourseOfferingSerializer``. Every other offering-keyed surface in the API
(``/classrooms/``, ``/students/me/register/``, ``academic.student_course_views``)
names the key ``offering_id``, and that is what the frontend reads — so when
this one endpoint answered with ``id`` alone, ``/assessment`` computed
``selected = undefined`` and never opened the assessment panel, while the
lecturer dashboard navigated to ``/lessons/undefined``.

Both names are emitted on purpose: ``id`` predates the alias and other readers
use it. Dropping either one would fix one screen by breaking another.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    SchoolYear,
    Semester,
)
from apps.academic.serializers import CourseOfferingSerializer


class OfferingIdContractTests(TestCase):
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
            "oi-lect@fet.edu", "oi-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(
            code="CS301", name="Operating Systems", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )

    def test_serializer_carries_offering_id_beside_id(self):
        payload = CourseOfferingSerializer(self.offering).data
        self.assertIn("id", payload)
        self.assertIn("offering_id", payload)
        self.assertEqual(str(payload["offering_id"]), str(self.offering.pk))
        self.assertEqual(str(payload["id"]), str(payload["offering_id"]))

    def test_lecturer_course_list_addresses_the_offering_as_offering_id(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get("/api/v1/lecturers/me/courses/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(str(rows[0]["offering_id"]), str(self.offering.pk))

    def test_unknown_offering_consumers_do_not_lose_id(self):
        """The alias is additive: `id` must survive for existing readers."""
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get("/api/v1/lecturers/me/courses/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(str(response.data["data"][0]["id"]), str(self.offering.pk))
