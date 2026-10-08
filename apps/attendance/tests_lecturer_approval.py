from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course
from apps.accounts.models import User
from apps.attendance.models import AttendanceSession


class AttendanceLecturerApprovalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.pending = self.user("attendance-pending", User.LecturerApproval.PENDING)
        self.rejected = self.user("attendance-rejected", User.LecturerApproval.REJECTED)
        self.approved = self.user("attendance-approved", User.LecturerApproval.APPROVED)
        self.course = Course.objects.create(code="APP401", name="Approval Security")

    def user(self, username, approval):
        return User.objects.create_user(
            f"{username}@example.test", username, "Test", username,
            "StrongPass!2026", role=User.Role.LECTURER,
            lecturer_approval_status=approval,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def test_pending_and_rejected_lecturers_cannot_open_attendance(self):
        for user in (self.pending, self.rejected):
            class_session = ClassSession.objects.create(
                course=self.course, lecturer=user, starts_at=timezone.now()
            )
            response = self.auth(user).post(
                reverse("attendance:session-list"),
                {"class_session": str(class_session.pk)},
                format="json",
            )
            self.assertEqual(response.status_code, 403, user.username)
        self.assertFalse(AttendanceSession.objects.exists())

    def test_approved_lecturer_can_open_owned_attendance(self):
        class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.approved, starts_at=timezone.now()
        )
        response = self.auth(self.approved).post(
            reverse("attendance:session-list"),
            {"class_session": str(class_session.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
