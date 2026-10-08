"""BR-210 attendance session state must roll back with failed auditing."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academic.models import ClassSession, Course

from .models import AttendanceSession
from .services.attendance_service import close_attendance_session, start_attendance_session


class AttendanceAuditAtomicityTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            "attendance-audit@example.test",
            "attendance-audit",
            "Attendance",
            "Auditor",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(code="ATA101", name="Atomic Attendance")
        self.class_session = ClassSession.objects.create(
            course=self.course,
            lecturer=self.lecturer,
            starts_at=timezone.now(),
        )

    @patch(
        "apps.attendance.services.attendance_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_start_rolls_back_when_audit_fails(self, _audit):
        with self.assertRaises(RuntimeError):
            start_attendance_session(
                actor=self.lecturer,
                class_session_id=self.class_session.pk,
            )

        self.assertFalse(
            AttendanceSession.objects.filter(class_session=self.class_session).exists()
        )

    @patch(
        "apps.attendance.services.attendance_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_close_rolls_back_when_audit_fails(self, _audit):
        session = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        with self.assertRaises(RuntimeError):
            close_attendance_session(actor=self.lecturer, session=session)

        session.refresh_from_db()
        self.assertEqual(session.status, AttendanceSession.Status.ACTIVE)
