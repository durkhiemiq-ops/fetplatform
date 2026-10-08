from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User

from .models import Project


class ProjectLecturerApprovalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.pending = self.user("project-pending", User.LecturerApproval.PENDING)
        self.rejected = self.user("project-rejected", User.LecturerApproval.REJECTED)
        self.approved = self.user("project-approved", User.LecturerApproval.APPROVED)
        self.legacy = self.user("project-legacy", None)

    def user(self, username, approval):
        return User.objects.create_user(
            f"{username}@example.test", username, "Test", username,
            "StrongPass!2026", role=User.Role.LECTURER,
            lecturer_approval_status=approval,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def test_pending_and_rejected_lecturers_have_no_project_privileges(self):
        for user in (self.pending, self.rejected):
            project = Project.objects.create(
                title=f"{user.username} project", owner=user,
                supervisor=user, created_by=user
            )
            listing = self.auth(user).get(reverse("projects:list"))
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.data["data"], [])
            detail = self.client.get(reverse("projects:detail", args=[project.pk]))
            self.assertEqual(detail.status_code, 404)
            create = self.client.post(
                reverse("projects:list"), {"title": "Forged project"}, format="json"
            )
            self.assertEqual(create.status_code, 403)
            self.assertFalse(Project.objects.filter(title="Forged project").exists())

    def test_approved_and_legacy_lecturers_remain_authorized(self):
        for user in (self.approved, self.legacy):
            response = self.auth(user).post(
                reverse("projects:list"),
                {"title": f"{user.username} project"},
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)
