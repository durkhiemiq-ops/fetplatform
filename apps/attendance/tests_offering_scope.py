"""Flexible attendance retains and enforces its course-offering context."""

from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)

from .services.attendance_service import (
    eligible_students_for_session,
    start_flexible_attendance_session,
)


class AttendanceOfferingScopeTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            "attendance-offering@example.test",
            "attendance-offering",
            "Attendance",
            "Lecturer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.enrolled = User.objects.create_user(
            "attendance-enrolled@example.test",
            "attendance-enrolled",
            "Enrolled",
            "Student",
            "StrongPass!2026",
        )
        self.other_period = User.objects.create_user(
            "attendance-other-period@example.test",
            "attendance-other-period",
            "Other",
            "Period",
            "StrongPass!2026",
        )
        faculty = Faculty.objects.create(name="Attendance Offering Faculty")
        department = Department.objects.create(
            name="Attendance Offering Department", code="AOF", faculty=faculty
        )
        course = Course.objects.create(
            code="AOF101", name="Offering Attendance", department=department
        )
        year = SchoolYear.objects.create(
            name="2033/2034",
            start_date=date(2033, 9, 1),
            end_date=date(2034, 6, 30),
        )
        first = Semester.objects.create(
            school_year=year,
            name="First",
            start_date=date(2033, 9, 1),
            end_date=date(2034, 1, 31),
        )
        second = Semester.objects.create(
            school_year=year,
            name="Second",
            start_date=date(2034, 2, 1),
            end_date=date(2034, 6, 30),
        )
        self.offering = CourseOffering.objects.create(
            course=course,
            semester=first,
            department=department,
            lecturer=self.lecturer,
        )
        other_offering = CourseOffering.objects.create(
            course=course,
            semester=second,
            department=department,
            lecturer=self.lecturer,
        )
        Enrollment.objects.create(
            student=self.enrolled,
            course=course,
            course_offering=self.offering,
        )
        Enrollment.objects.create(
            student=self.other_period,
            course=course,
            course_offering=other_offering,
        )

    def test_flexible_session_retains_offering_and_uses_its_roster(self):
        session = start_flexible_attendance_session(
            actor=self.lecturer,
            offering_id=self.offering.pk,
        )

        self.assertEqual(session.class_session.course_offering_id, self.offering.pk)
        self.assertEqual(
            [student.pk for student in eligible_students_for_session(session=session)],
            [self.enrolled.pk],
        )
