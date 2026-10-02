"""API tests for the project domain (BR-100 to BR-161)."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

from .models import Project, ProjectContribution, ProjectGroupMembership, ProjectTask

GHOST = "11111111-1111-1111-1111-111111111111"


class ProjectApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.lecturer = User.objects.create_user(
            "proj-lect@example.test",
            "proj-lect",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "proj-student@example.test", "proj-student", "Stu", "Dent", "StrongPass!2026"
        )
        self.outsider = User.objects.create_user(
            "proj-outsider@example.test", "proj-outsider", "Out", "Sider", "StrongPass!2026"
        )
        self.project = Project.objects.create(
            title="Capstone",
            owner=self.lecturer,
            supervisor=self.lecturer,
            created_by=self.lecturer,
            status="draft",
        )
        self.task = ProjectTask.objects.create(
            project=self.project, title="Design doc", created_by=self.lecturer
        )

    def _add_member(self, student=None):
        return ProjectGroupMembership.objects.create(
            project=self.project, student=student or self.student
        )

    def test_requires_authentication(self):
        response = self.client.get(reverse("projects:list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_student_cannot_own_project(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("projects:list"), {"title": "Mine"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_lecturer_creates_draft_project(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("projects:list"), {"title": "New Capstone"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        data = response.data["data"]
        # BR-140: every project starts as draft, inactive.
        self.assertEqual(data["status"], "draft")
        self.assertFalse(data["is_active"])
        self.assertEqual(str(data["owner"]), str(self.lecturer.id))

    def test_lifecycle_transitions_and_archive_audit(self):
        detail = reverse("projects:detail", args=[self.project.pk])
        self.client.force_authenticate(user=self.lecturer)

        # draft -> active
        response = self.client.patch(detail, {"status": "active"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "active")

        # backward transition rejected (BR-140..143)
        backward = self.client.patch(detail, {"status": "draft"}, format="json")
        self.assertEqual(backward.status_code, 400)

        # skipping to archived before completed rejected
        early_archive = self.client.patch(detail, {"status": "archived"}, format="json")
        self.assertEqual(early_archive.status_code, 400)

        # active -> completed -> archived (with audit, BR-161)
        completed = self.client.patch(detail, {"status": "completed"}, format="json")
        self.assertEqual(completed.status_code, 200)
        archived = self.client.patch(detail, {"status": "archived"}, format="json")
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.data["data"]["status"], "archived")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="project_archived", resource_id=str(self.project.pk)
            ).exists()
        )

        # students may not drive the lifecycle
        self.client.force_authenticate(user=self.student)
        denied = self.client.patch(detail, {"status": "active"}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "UNAUTHORIZED")

    def test_membership_duplicate_and_authorization(self):
        url = reverse("projects:member-add", args=[self.project.pk])
        self.client.force_authenticate(user=self.lecturer)
        first = self.client.post(url, {"student": str(self.student.id)}, format="json")
        self.assertEqual(first.status_code, 201)

        duplicate = self.client.post(url, {"student": str(self.student.id)}, format="json")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["error"]["code"], "DUPLICATE_MEMBER")

        self.client.force_authenticate(user=self.outsider)
        denied = self.client.post(url, {"student": str(self.student.id)}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "UNAUTHORIZED")

    def test_task_creation_and_status_rules(self):
        self._add_member()
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            reverse("projects:task-create", args=[self.project.pk]),
            {"title": "Build", "assignee": str(self.student.id)},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        task_id = created.data["data"]["id"]

        # BR-111: only authorized participants can be assigned.
        bad_assignee = self.client.post(
            reverse("projects:task-create", args=[self.project.pk]),
            {"title": "Sneaky", "assignee": str(self.outsider.id)},
            format="json",
        )
        self.assertEqual(bad_assignee.status_code, 400)

        # assignee updates status (BR-112/113)
        self.client.force_authenticate(user=self.student)
        status_url = reverse("projects:task-status", args=[task_id])
        ok = self.client.patch(status_url, {"status": "in_progress"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["data"]["status"], "in_progress")

        # outsiders cannot
        self.client.force_authenticate(user=self.outsider)
        denied = self.client.patch(status_url, {"status": "completed"}, format="json")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "UNAUTHORIZED")

    def test_contribution_flow(self):
        self._add_member()
        list_url = reverse("projects:contribution-create", args=[self.project.pk])

        # participant submits task-linked evidence (BR-120/121)
        self.client.force_authenticate(user=self.student)
        created = self.client.post(
            list_url,
            {"evidence_type": "task", "evidence_ref": str(self.task.id)},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["data"]["status"], "pending_review")
        contribution_id = created.data["data"]["id"]

        # evidence must exist inside the project
        bad_evidence = self.client.post(
            list_url,
            {"evidence_type": "task", "evidence_ref": GHOST},
            format="json",
        )
        self.assertEqual(bad_evidence.status_code, 400)
        self.assertEqual(bad_evidence.data["error"]["code"], "INVALID_EVIDENCE")

        # non-participants are rejected before anything else
        self.client.force_authenticate(user=self.outsider)
        not_participant = self.client.post(
            list_url,
            {"evidence_type": "task", "evidence_ref": str(self.task.id)},
            format="json",
        )
        self.assertEqual(not_participant.status_code, 403)
        self.assertEqual(not_participant.data["error"]["code"], "NOT_PARTICIPANT")

        # supervisor reviews with audit (BR-122/210)
        self.client.force_authenticate(user=self.lecturer)
        review = self.client.patch(
            reverse("projects:contribution-review", args=[contribution_id]),
            {"approved": True, "notes": "solid work"},
            format="json",
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.data["data"]["status"], "approved")
        self.assertTrue(
            AuditEvent.objects.filter(action="contribution_reviewed").exists()
        )

        # outsiders cannot review
        self.client.force_authenticate(user=self.outsider)
        denied = self.client.patch(
            reverse("projects:contribution-review", args=[contribution_id]),
            {"approved": False},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["error"]["code"], "UNAUTHORIZED")

    def test_contribution_list_visibility(self):
        self._add_member()
        ProjectContribution.objects.create(
            project=self.project,
            student=self.student,
            evidence_type="task",
            evidence_ref=str(self.task.id),
            created_by=self.student,
        )
        url = reverse("projects:contribution-list")

        self.client.force_authenticate(user=self.student)
        own = self.client.get(url)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(len(own.data["data"]), 1)

        self.client.force_authenticate(user=self.outsider)
        none = self.client.get(url)
        self.assertEqual(none.status_code, 200)
        self.assertEqual(len(none.data["data"]), 0)

        self.client.force_authenticate(user=self.lecturer)
        all_rows = self.client.get(url)
        self.assertEqual(all_rows.status_code, 200)
        self.assertEqual(len(all_rows.data["data"]), 1)

    def test_milestone_crud_and_authorization(self):
        list_url = reverse("projects:milestone-list", args=[self.project.pk])

        # Owner/supervisor manages milestones; members can read them only.
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            list_url,
            {"title": "Requirements", "progress": 20, "due_date": "2026-10-01"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        milestone_id = created.data["data"]["id"]
        self.assertEqual(str(created.data["data"]["project"]), str(self.project.pk))
        self.assertTrue(
            AuditEvent.objects.filter(action="milestone_created").exists()
        )

        # Detail bundle carries milestones
        detail = self.client.get(reverse("projects:detail", args=[self.project.pk]))
        self.assertEqual(len(detail.data["data"]["milestones"]), 1)
        self.assertEqual(
            detail.data["data"]["milestones"][0]["id"], milestone_id
        )

        # Student member reads but cannot write
        self._add_member()
        self.client.force_authenticate(user=self.student)
        read_ok = self.client.get(list_url)
        self.assertEqual(read_ok.status_code, 200)
        self.assertEqual(len(read_ok.data["data"]), 1)

        forbidden = self.client.post(
            list_url, {"title": "Nope"}, format="json"
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.data["error"]["code"], "UNAUTHORIZED")

        # Manager updates; invalid progress rejected
        self.client.force_authenticate(user=self.lecturer)
        detail_url = reverse("projects:milestone-detail", args=[milestone_id])
        bad = self.client.patch(detail_url, {"progress": 250}, format="json")
        self.assertEqual(bad.status_code, 400)

        good = self.client.patch(
            detail_url, {"progress": 100}, format="json"
        )
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.data["data"]["progress"], 100)
        self.assertTrue(
            AuditEvent.objects.filter(action="milestone_updated").exists()
        )

        # Delete audited; id then returns 404
        deleted = self.client.delete(detail_url)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(action="milestone_deleted").exists()
        )
        gone = self.client.patch(detail_url, {"title": "x"}, format="json")
        self.assertEqual(gone.status_code, 404)

    def test_milestone_completed_project_is_read_only(self):
        self.project.status = "completed"
        self.project.save(update_fields=["status"])
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("projects:milestone-list", args=[self.project.pk]),
            {"title": "Frozen"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")
