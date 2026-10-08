"""Assessment writes required by BR-132/BR-210 are transactional."""

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.academic.models import Course

from .models import Assessment
from .services.assessment_service import create_assessment, update_assessment


class AssessmentAuditAtomicityTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            "assessment-audit@example.test",
            "assessment-audit",
            "Assessment",
            "Auditor",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "assessment-student@example.test",
            "assessment-student",
            "Assessment",
            "Student",
            "StrongPass!2026",
        )
        self.course = Course.objects.create(code="ASA101", name="Atomic Assessment")

    @patch(
        "apps.assessments.services.assessment_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_create_rolls_back_when_audit_fails(self, _audit):
        with self.assertRaises(RuntimeError):
            create_assessment(
                AssessmentModel=Assessment,
                student_id=self.student.pk,
                created_by=self.lecturer,
                score=72,
                private_notes="",
                course_id=self.course.pk,
                scope_authorizer=lambda actor: True,
            )

        self.assertFalse(Assessment.objects.filter(student=self.student).exists())

    @patch(
        "apps.assessments.services.assessment_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_update_rolls_back_when_audit_fails(self, _audit):
        assessment = Assessment.objects.create(
            student=self.student,
            course=self.course,
            score=40,
            created_by=self.lecturer,
        )

        with self.assertRaises(RuntimeError):
            update_assessment(
                assessment=assessment,
                actor=self.lecturer,
                new_score=80,
                released=True,
            )

        assessment.refresh_from_db()
        self.assertEqual(assessment.score, 40)
        self.assertFalse(assessment.released)
