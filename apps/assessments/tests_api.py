"""API tests: BR-130 (authorization), BR-131 (student visibility),
BR-132 (audit trail) through the assessment endpoints."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import ClassSession, Course
from django.utils import timezone
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
        self.other_course = Course.objects.create(code="FET102", name="Other Course")
        self.other_lecturer = User.objects.create_user(
            "assess-other-lect@example.test", "assess-other-lect", "Other", "Lecturer",
            "StrongPass!2026", role=User.Role.LECTURER,
        )
        ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )
        ClassSession.objects.create(
            course=self.other_course,
            lecturer=self.other_lecturer,
            starts_at=timezone.now(),
        )

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
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_lecturer_creates_audited_assessment(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("assessments:list"),
            {
                "student": str(self.student.id),
                "course": str(self.course.id),
                "score": "85.50",
            },
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
                action="assessment_created", resource_type="assessment"
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

    def test_lecturer_sees_only_supervised_course_with_notes(self):
        Assessment.objects.create(
            student=self.student,
            course=self.course,
            released=True,
            private_notes="visible to supervisor",
        )
        Assessment.objects.create(student=self.student, course=self.course, released=False)
        Assessment.objects.create(
            student=self.other,
            course=self.other_course,
            released=True,
            private_notes="foreign private note",
        )

        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            any(r["private_notes"] == "visible to supervisor" for r in rows)
        )
        self.assertFalse(
            any(r["private_notes"] == "foreign private note" for r in rows)
        )

    def test_release_requires_academic_actor_and_is_audited(self):
        assessment = Assessment.objects.create(
            student=self.student,
            course=self.course,
            released=False,
            private_notes="draft notes",
        )
        self.client.force_authenticate(user=self.student)
        denied = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "FORBIDDEN")

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

    def test_lecturer_approval_controls_assessment_mutations(self):
        assessment = Assessment.objects.create(
            student=self.student,
            course=self.course,
            released=False,
        )
        self.lecturer.lecturer_approval_status = User.LecturerApproval.PENDING
        self.lecturer.save(update_fields=["lecturer_approval_status", "updated_at"])
        self.client.force_authenticate(user=self.lecturer)

        pending = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )
        self.assertEqual(pending.status_code, 403)

        self.lecturer.lecturer_approval_status = User.LecturerApproval.APPROVED
        self.lecturer.save(update_fields=["lecturer_approval_status", "updated_at"])
        approved = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        self.lecturer.lecturer_approval_status = User.LecturerApproval.REJECTED
        self.lecturer.save(update_fields=["lecturer_approval_status", "updated_at"])
        rejected = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": False},
            format="json",
        )
        self.assertEqual(rejected.status_code, 403)
        assessment.refresh_from_db()
        self.assertTrue(assessment.released)

    def test_negative_score_rejected(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("assessments:list"),
            {"student": str(self.student.id), "score": "-5.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_assessment_writes_reject_unknown_fields(self):
        self.client.force_authenticate(user=self.lecturer)
        create = self.client.post(
            reverse("assessments:list"),
            {
                "student": str(self.student.id),
                "course": str(self.course.id),
                "score": "75.00",
                "created_by": str(self.other_lecturer.id),
            },
            format="json",
        )
        self.assertEqual(create.status_code, 400)

        assessment = Assessment.objects.create(student=self.student, course=self.course)
        update = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"status": "official"},
            format="json",
        )
        self.assertEqual(update.status_code, 400)
