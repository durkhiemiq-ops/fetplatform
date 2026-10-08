"""Class sessions use offering-specific enrollment when that context exists."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User

from .models import (
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)
from .services.eligibility_service import is_student_eligible_for_class


class OfferingScopedClassSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.lecturer = User.objects.create_user(
            "offering-lecturer@example.test",
            "offering-lecturer",
            "Offering",
            "Lecturer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "offering-student@example.test",
            "offering-student",
            "Offering",
            "Student",
            "StrongPass!2026",
        )
        faculty = Faculty.objects.create(name="Offering Faculty")
        department = Department.objects.create(
            name="Offering Department", code="OFD", faculty=faculty
        )
        self.course = Course.objects.create(
            code="OFS101", name="Offering Scope", department=department
        )
        year = SchoolYear.objects.create(
            name="2032/2033",
            start_date=date(2032, 9, 1),
            end_date=date(2033, 6, 30),
        )
        first = Semester.objects.create(
            school_year=year,
            name="First",
            start_date=date(2032, 9, 1),
            end_date=date(2033, 1, 31),
        )
        second = Semester.objects.create(
            school_year=year,
            name="Second",
            start_date=date(2033, 2, 1),
            end_date=date(2033, 6, 30),
        )
        self.first_offering = CourseOffering.objects.create(
            course=self.course,
            semester=first,
            department=department,
            lecturer=self.lecturer,
        )
        self.second_offering = CourseOffering.objects.create(
            course=self.course,
            semester=second,
            department=department,
            lecturer=self.lecturer,
        )
        self.first_session = ClassSession.objects.create(
            course=self.course,
            course_offering=self.first_offering,
            lecturer=self.lecturer,
            starts_at=timezone.now() + timedelta(days=1),
        )
        self.second_session = ClassSession.objects.create(
            course=self.course,
            course_offering=self.second_offering,
            lecturer=self.lecturer,
            starts_at=timezone.now() + timedelta(days=2),
        )
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            course_offering=self.first_offering,
        )

    def test_same_course_different_offering_does_not_grant_eligibility(self):
        self.assertTrue(
            is_student_eligible_for_class(
                self.student.pk,
                class_id=self.first_session.pk,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )
        self.assertFalse(
            is_student_eligible_for_class(
                self.student.pk,
                class_id=self.second_session.pk,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )

    def test_student_class_list_is_scoped_to_enrolled_offering(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("academic:class-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["data"]],
            [str(self.first_session.pk)],
        )
        self.assertEqual(
            response.data["data"][0]["course_offering"],
            self.first_offering.pk,
        )

    def test_legacy_course_only_session_keeps_course_fallback(self):
        legacy_student = User.objects.create_user(
            "legacy-offering-student@example.test",
            "legacy-offering-student",
            "Legacy",
            "Student",
            "StrongPass!2026",
        )
        Enrollment.objects.create(student=legacy_student, course=self.course)
        legacy_session = ClassSession.objects.create(
            course=self.course,
            lecturer=self.lecturer,
            starts_at=timezone.now() + timedelta(days=3),
        )

        self.assertTrue(
            is_student_eligible_for_class(
                legacy_student.pk,
                class_id=legacy_session.pk,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )
