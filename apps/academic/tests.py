from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.academic.models import ClassSession, Course, Enrollment
from apps.academic.services.eligibility_service import (
    ClassNotFoundError,
    is_student_eligible_for_class,
)
from apps.academic.services.enrollment_service import (
    drop_student_from_course,
    enroll_student_in_course,
)
from apps.accounts.models import User


class EligibilityServiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "student@example.test",
            "student",
            "Stu",
            "Dent",
            "StrongPass!2026",
        )
        self.other_student = User.objects.create_user(
            "other@example.test",
            "other",
            "Other",
            "Student",
            "StrongPass!2026",
        )
        self.lecturer = User.objects.create_user(
            "lecturer@example.test",
            "lecturer",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")
        self.other_course = Course.objects.create(code="FET102", name="Other Course")
        self.class_session = ClassSession.objects.create(
            course=self.course,
            lecturer=self.lecturer,
            starts_at=timezone.now() + timedelta(hours=1),
        )

    def test_active_enrollment_makes_student_eligible(self):
        Enrollment.objects.create(student=self.student, course=self.course)

        self.assertTrue(
            is_student_eligible_for_class(
                self.student.id,
                class_id=self.class_session.id,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )

    def test_inactive_enrollment_is_not_eligible(self):
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            is_active=False,
            status="inactive",
        )

        self.assertFalse(
            is_student_eligible_for_class(
                self.student.id,
                class_id=self.class_session.id,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )

    def test_enrollment_in_another_course_is_not_eligible(self):
        Enrollment.objects.create(student=self.student, course=self.other_course)

        self.assertFalse(
            is_student_eligible_for_class(
                self.student.id,
                class_id=self.class_session.id,
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )
        )

    def test_missing_class_is_rejected(self):
        with self.assertRaises(ClassNotFoundError):
            is_student_eligible_for_class(
                self.student.id,
                class_id="00000000-0000-0000-0000-000000000000",
                ClassModel=ClassSession,
                EnrollmentModel=Enrollment,
            )


class EnrollmentServiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "student@example.test",
            "student",
            "Stu",
            "Dent",
            "StrongPass!2026",
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")

    def test_drop_preserves_row_and_ends_eligibility(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
        )

        dropped = drop_student_from_course(
            self.student.id,
            self.course.id,
            EnrollmentModel=Enrollment,
            actor_id="authorized-actor",
            authorization_checker=lambda **kwargs: True,
            reason="Course withdrawn",
        )

        self.assertEqual(dropped.pk, enrollment.pk)
        self.assertFalse(dropped.is_active)
        self.assertEqual(dropped.status, "inactive")
        self.assertEqual(Enrollment.objects.filter(pk=enrollment.pk).count(), 1)

    def test_reenrollment_reactivates_existing_row(self):
        enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            is_active=False,
            status="inactive",
        )

        reactivated = enroll_student_in_course(
            self.student.id,
            self.course.id,
            EnrollmentModel=Enrollment,
            StudentModel=User,
            CourseModel=Course,
            actor_id="authorized-actor",
            authorization_checker=lambda **kwargs: True,
        )

        self.assertEqual(reactivated.pk, enrollment.pk)
        self.assertTrue(reactivated.is_active)
        self.assertEqual(reactivated.status, "active")
