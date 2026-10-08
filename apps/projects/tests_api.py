"""API tests for the project domain (BR-100 to BR-161)."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

from .models import (
    Project,
    ProjectContribution,
    ProjectGroup,
    ProjectGroupMembership,
    ProjectTask,
)

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

    def test_project_inputs_reject_unknown_fields(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("projects:list"),
            {"title": "Looks valid", "role": "ADMINISTRATOR"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Project.objects.filter(title="Looks valid").exists())

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

    def test_group_creation_is_audited_and_archived_projects_are_read_only(self):
        url = reverse("projects:group-create", args=[self.project.pk])
        self.client.force_authenticate(user=self.lecturer)

        created = self.client.post(url, {"name": "Core Team"}, format="json")
        self.assertEqual(created.status_code, 201)
        group_id = created.data["data"]["id"]
        self.assertTrue(
            AuditEvent.objects.filter(
                action="project_group_created",
                resource_id=str(group_id),
                actor_id=self.lecturer.id,
            ).exists()
        )

        self.project.status = Project.Status.ARCHIVED
        self.project.save(update_fields=["status"])
        rejected = self.client.post(url, {"name": "Late Team"}, format="json")
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.data["error"]["code"], "UNAUTHORIZED")
        self.assertEqual(ProjectGroup.objects.filter(project=self.project).count(), 1)

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
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.data["error"]["code"], "NOT_FOUND")

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
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.data["error"]["code"], "NOT_FOUND")

    def test_candidate_list_is_minimal_paginated_and_searchable(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(
            reverse("projects:candidates", args=[self.project.pk]),
            {"search": "proj-", "page_size": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertGreaterEqual(response.data["pagination"]["total"], 2)
        self.assertEqual(response.data["pagination"]["page_size"], 1)
        self.assertEqual(
            set(response.data["data"][0]),
            {"id", "first_name", "last_name", "username"},
        )

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
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.data["error"]["code"], "NOT_FOUND")

    def test_contribution_flow(self):
        self._add_member()
        self.task.assignee = self.student
        self.task.save(update_fields=["assignee"])
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
        self.assertEqual(not_participant.status_code, 404)
        self.assertEqual(not_participant.data["error"]["code"], "NOT_FOUND")

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
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.data["error"]["code"], "NOT_FOUND")

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

    def test_member_removal_is_project_scoped_and_audited(self):
        group = ProjectGroup.objects.create(project=self.project, name="Team")
        membership = ProjectGroupMembership.objects.create(
            project=self.project, group=group, student=self.student
        )
        url = reverse(
            "projects:member-delete",
            args=[self.project.pk, group.pk, self.student.pk],
        )

        self.client.force_authenticate(user=self.outsider)
        hidden = self.client.delete(url)
        self.assertEqual(hidden.status_code, 404)
        self.assertTrue(ProjectGroupMembership.objects.filter(pk=membership.pk).exists())

        self.client.force_authenticate(user=self.lecturer)
        removed = self.client.delete(url)
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(ProjectGroupMembership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(
                action="project_member_removed", resource_id=str(membership.pk)
            ).exists()
        )

    def test_student_cannot_claim_another_students_task(self):
        other_student = User.objects.create_user(
            "proj-other-student@example.test",
            "proj-other-student",
            "Other",
            "Student",
            "StrongPass!2026",
        )
        self._add_member()
        self._add_member(other_student)
        self.task.assignee = other_student
        self.task.save(update_fields=["assignee"])

        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("projects:contribution-create", args=[self.project.pk]),
            {"evidence_type": "task", "evidence_ref": str(self.task.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["error"]["code"], "INVALID_EVIDENCE")
        self.assertFalse(ProjectContribution.objects.exists())

    def test_official_task_status_stays_lecturer_controlled(self):
        self._add_member()
        self.task.assignee = self.student
        self.task.is_official = True
        self.task.save(update_fields=["assignee", "is_official"])

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("projects:task-status", args=[self.task.pk]),
            {"status": "completed"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "todo")


class CrossProjectGroupIdorTests(TestCase):
    """A client-supplied group id must be scoped to the project being modified.

    The vulnerability these close
    -----------------------------
    ``POST /projects/{pk}/members/`` validated its optional ``group`` field with
    a bare ``ProjectGroup.objects.filter(pk=group_id).exists()`` -- "does this
    group exist anywhere in the system", not "does it belong to *this* project".
    A manager of project A could pass the UUID of a group owned by project B and
    write a ``ProjectGroupMembership`` row whose ``project_id`` was A while its
    ``group_id`` pointed into B. Because ``ProjectGroupMembership.group`` uses
    ``related_name="memberships"``, the injected row then appeared in project
    B's group roster.

    ``TaskCreateSerializer.validate_group`` had the identical unscoped probe,
    which made the two a chain: create the cross-project membership, then point
    a task at that group and pass ``_participant_lookup`` (which requires a
    membership row matching *both* the caller's project and the group id).

    Every assertion below fails against the original code: the pre-fix service
    returned 201 and persisted the row.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.alice = User.objects.create_user(
            "alice-lect@example.test", "alice-lect", "Alice", "L", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.bob = User.objects.create_user(
            "bob-lect@example.test", "bob-lect", "Bob", "L", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "idor-student@example.test", "idor-student", "Stu", "Dent", "StrongPass!2026"
        )

        # Project A, managed by Alice. Project B, managed by Bob.
        self.project_a = Project.objects.create(
            title="Project A", owner=self.alice, supervisor=self.alice,
            created_by=self.alice, status="draft",
        )
        self.project_b = Project.objects.create(
            title="Project B", owner=self.bob, supervisor=self.bob,
            created_by=self.bob, status="draft",
        )
        self.group_b = ProjectGroup.objects.create(
            project=self.project_b, name="Bob's secret group"
        )
        self.group_a = ProjectGroup.objects.create(
            project=self.project_a, name="Alice's group"
        )

    def test_cannot_add_member_into_another_projects_group(self):
        """The core IDOR: Alice writes into Bob's group via her own project."""
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            reverse("projects:member-add", args=[self.project_a.pk]),
            {"student": str(self.student.id), "group": str(self.group_b.pk)},
            format="json",
        )

        # Pre-fix this was 201 and wrote the row.
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")

        # Nothing persisted, and crucially nothing pointing at Bob's group.
        self.assertFalse(ProjectGroupMembership.objects.exists())
        self.assertFalse(
            ProjectGroupMembership.objects.filter(
                project=self.project_a, group=self.group_b
            ).exists()
        )
        self.assertFalse(self.group_b.memberships.exists())

    def test_cannot_assign_task_to_another_projects_group(self):
        """Second link in the chain, closed independently.

        Pre-fix, ``validate_group`` accepted any existing group id, and
        ``_participant_lookup`` was satisfied by the membership row created
        above -- so a task in project A could be aimed at project B's group.
        """
        # Plant the exact row the first exploit would have created.
        ProjectGroupMembership.objects.create(
            project=self.project_a, group=self.group_b, student=self.student
        )
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            reverse("projects:task-create", args=[self.project_a.pk]),
            {"title": "Leak", "group": str(self.group_b.pk)},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")
        self.assertFalse(
            ProjectTask.objects.filter(project=self.project_a, group=self.group_b).exists()
        )

    def test_missing_group_and_foreign_group_are_indistinguishable(self):
        """§25: the endpoint must not reveal which group ids exist platform-wide.

        Both a non-existent uuid and a real group owned by another project must
        produce byte-identical status, code and message.
        """
        self.client.force_authenticate(user=self.alice)
        url = reverse("projects:member-add", args=[self.project_a.pk])
        payload = {"student": str(self.student.id)}

        foreign = self.client.post(
            url, dict(payload, group=str(self.group_b.pk)), format="json"
        )
        nonexistent = self.client.post(
            url, dict(payload, group=GHOST), format="json"
        )

        self.assertEqual(foreign.status_code, nonexistent.status_code)
        self.assertEqual(foreign.data, nonexistent.data)
        self.assertEqual(nonexistent.status_code, 404)

    def test_own_projects_group_is_still_accepted(self):
        """The fix must not over-block: a group from the caller's own project
        works exactly as before."""
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            reverse("projects:member-add", args=[self.project_a.pk]),
            {"student": str(self.student.id), "group": str(self.group_a.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        membership = ProjectGroupMembership.objects.get(project=self.project_a)
        self.assertEqual(membership.group_id, self.group_a.pk)

    def test_group_omitted_is_unaffected(self):
        """Membership without a group (the common case) still works."""
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            reverse("projects:member-add", args=[self.project_a.pk]),
            {"student": str(self.student.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(ProjectGroupMembership.objects.get().group_id)

    def test_admin_is_also_project_scoped_for_groups(self):
        """Even a platform admin cannot smuggle a foreign group id.

        ``_can_manage`` lets an admin manage any project, which is correct --
        but "manages project A" must not extend to "may point project A's rows
        at project B's groups".
        """
        admin = User.objects.create_user(
            "idor-admin@example.test", "idor-admin", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_authenticate(user=admin)
        response = self.client.post(
            reverse("projects:member-add", args=[self.project_a.pk]),
            {"student": str(self.student.id), "group": str(self.group_b.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectGroupMembership.objects.exists())

    def test_service_layer_refuses_without_a_scoped_lookup(self):
        """Defence in depth: the service fails closed if no scoped lookup is
        supplied, so a future caller cannot reintroduce the bug by forgetting
        the injection."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.projects.services.project_service import (
            ProjectGroupNotInProjectError,
            add_project_member,
        )

        with self.assertRaises(ProjectGroupNotInProjectError):
            add_project_member(
                ProjectModel=Project,
                project_id=self.project_a.pk,
                student_id=self.student.pk,
                actor_id=self.alice.pk,
                group_id=self.group_b.pk,
                GroupMembershipModel=ProjectGroupMembership,
                is_explicit_assignment=True,
                actor_authorizer=lambda actor_id, project: True,
                # group_lookup intentionally omitted
            )
