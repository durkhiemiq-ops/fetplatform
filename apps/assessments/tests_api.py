"""API tests: BR-130 (authorization), BR-131 (student visibility),
BR-132 (audit trail) through the assessment endpoints."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import Course
from core.models import AuditEvent

from .models import Assessment


class AssessmentApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.lecturer = User.objects.create_user(
            "assess-lect@example.test",
            "assess-lect",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "assess-student@example.test", "assess-student", "Stu", "Dent", "StrongPass!2026"
        )
        self.other = User.objects.create_user(
            "assess-other@example.test", "assess-other", "Oth", "Er", "StrongPass!2026"
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")

    def test_requires_authentication(self):
        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_student_cannot_create(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("assessments:list"),
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_lecturer_creates_audited_assessment(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("assessments:list"),
            {"student": str(self.student.id), "score": "85.50"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], "official")
        # response.data holds pre-render Python values (UUID pk); the JSON
        # wire format this asserts against is the string form.
        self.assertEqual(str(response.data["data"]["created_by"]), str(self.lecturer.id))
        # BR-132: creation flows through the shared audit helper.
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_updated", resource_type="assessment"
            ).exists()
        )

    def test_student_sees_only_own_released(self):
        Assessment.objects.create(
            student=self.student, course=self.course, score="80.00",
            released=True, private_notes="hidden",
        )
        Assessment.objects.create(student=self.student, released=False)
        Assessment.objects.create(student=self.other, released=True)

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        # BR-131: own + released only, private notes stripped.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], "80.00")
        self.assertIsNone(rows[0]["private_notes"])

    def test_lecturer_sees_all_with_notes(self):
        Assessment.objects.create(
            student=self.student, released=True, private_notes="hidden"
        )
        Assessment.objects.create(student=self.student, released=False)
        Assessment.objects.create(student=self.other, released=True)

        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(any(r["private_notes"] == "hidden" for r in rows))

    def test_release_requires_academic_actor_and_is_audited(self):
        assessment = Assessment.objects.create(
            student=self.student, released=False, private_notes="draft notes"
        )
        self.client.force_authenticate(user=self.student)
        denied = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "UNAUTHORIZED")

        self.client.force_authenticate(user=self.lecturer)
        before = AuditEvent.objects.filter(
            action="assessment_updated", resource_type="assessment"
        ).count()
        allowed = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.data["data"]["released"])
        after = AuditEvent.objects.filter(
            action="assessment_updated", resource_type="assessment"
        ).count()
        self.assertGreater(after, before)

    def test_negative_score_rejected(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("assessments:list"),
            {"student": str(self.student.id), "score": "-5.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
