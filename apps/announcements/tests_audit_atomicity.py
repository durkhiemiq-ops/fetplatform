"""Announcement mutations and their BR-084 audit entries are atomic."""

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.academic.models import Faculty

from .models import Announcement
from .services.announcement_service import create_announcement, update_announcement


class AnnouncementAuditAtomicityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "announcement-audit@example.test",
            "announcement-audit",
            "Announcement",
            "Auditor",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.faculty = Faculty.objects.create(name="Announcement Faculty")

    @patch(
        "apps.announcements.services.announcement_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_create_rolls_back_when_audit_fails(self, _audit):
        with self.assertRaises(RuntimeError):
            create_announcement(
                AnnouncementModel=Announcement,
                title="Atomic notice",
                body="This should not survive.",
                scope="faculty",
                scope_id=self.faculty.pk,
                actor=self.admin,
                scope_exists=lambda scope, scope_id: True,
            )

        self.assertFalse(Announcement.objects.filter(title="Atomic notice").exists())

    @patch(
        "apps.announcements.services.announcement_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_update_rolls_back_when_audit_fails(self, _audit):
        announcement = Announcement.objects.create(
            title="Before",
            body="Original",
            scope=Announcement.Scope.FACULTY,
            faculty=self.faculty,
            created_by=self.admin,
            is_published=True,
        )

        with self.assertRaises(RuntimeError):
            update_announcement(
                announcement=announcement,
                actor=self.admin,
                actor_id=self.admin.pk,
                title="After",
            )

        announcement.refresh_from_db()
        self.assertEqual(announcement.title, "Before")
