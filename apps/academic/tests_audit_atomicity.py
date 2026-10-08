"""BR-210 academic mutations and audit records commit or roll back together."""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User

from .models import Course, CourseOffering, Department, Enrollment, Faculty, SchoolYear, Semester
from .services.enrollment_service import drop_student_from_course, enroll_student_in_course
from .services.structure_service import create_course_offering, create_school_year


class AcademicAuditAtomicityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "audit-admin@example.test",
            "audit-admin",
            "Audit",
            "Admin",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.student = User.objects.create_user(
            "audit-student@example.test",
            "audit-student",
            "Audit",
            "Student",
            "StrongPass!2026",
        )
        faculty = Faculty.objects.create(name="Audit Faculty")
        self.department = Department.objects.create(
            name="Audit Department", code="AUD", faculty=faculty
        )
        self.course = Course.objects.create(
            code="AUD101", name="Audit Systems", department=self.department
        )

    @patch(
        "apps.academic.services.structure_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_school_year_creation_rolls_back_when_audit_fails(self, _audit):
        with self.assertRaises(RuntimeError):
            create_school_year(
                actor=self.admin,
                data={
                    "name": "2030/2031",
                    "start_date": date(2030, 9, 1),
                    "end_date": date(2031, 6, 30),
                },
            )

        self.assertFalse(SchoolYear.objects.filter(name="2030/2031").exists())

    @patch(
        "apps.academic.services.structure_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_offering_creation_rolls_back_when_audit_fails(self, _audit):
        year = SchoolYear.objects.create(
            name="2031/2032",
            start_date=date(2031, 9, 1),
            end_date=date(2032, 6, 30),
        )
        semester = Semester.objects.create(
            school_year=year,
            name="First",
            start_date=date(2031, 9, 1),
            end_date=date(2032, 1, 31),
        )

        with self.assertRaises(RuntimeError):
            create_course_offering(
                actor=self.admin,
                data={
                    "course": self.course,
                    "semester": semester,
                    "department": self.department,
                },
            )

        self.assertFalse(CourseOffering.objects.filter(course=self.course).exists())

    @patch(
        "apps.academic.services.enrollment_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_enrollment_create_and_drop_roll_back_when_audit_fails(self, _audit):
        authorize = lambda **kwargs: True
        with self.assertRaises(RuntimeError):
            enroll_student_in_course(
                self.student.pk,
                self.course.pk,
                EnrollmentModel=Enrollment,
                StudentModel=User,
                CourseModel=Course,
                actor_id=self.admin.pk,
                authorization_checker=authorize,
            )
        self.assertFalse(
            Enrollment.objects.filter(student=self.student, course=self.course).exists()
        )

        enrollment = Enrollment.objects.create(student=self.student, course=self.course)
        with self.assertRaises(RuntimeError):
            drop_student_from_course(
                self.student.pk,
                self.course.pk,
                EnrollmentModel=Enrollment,
                actor_id=self.admin.pk,
                authorization_checker=authorize,
            )
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_active)
        self.assertEqual(enrollment.status, "active")
