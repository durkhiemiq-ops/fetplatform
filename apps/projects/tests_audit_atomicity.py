"""Destructive project writes must roll back when their audit record fails."""

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User

from .models import Project, ProjectGroup, ProjectGroupMembership, ProjectMilestone
from .services.project_service import (
    assign_group_leader,
    create_project,
    delete_milestone,
    remove_project_member,
)


class DestructiveProjectAuditAtomicityTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            "project-manager@example.test",
            "project-manager",
            "Project",
            "Manager",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "project-student@example.test",
            "project-student",
            "Project",
            "Student",
            "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.project = Project.objects.create(
            title="Audited project",
            owner=self.manager,
            created_by=self.manager,
        )

    @patch(
        "apps.projects.services.project_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_project_create_rolls_back_when_audit_fails(self, _audit):
        with self.assertRaises(RuntimeError):
            create_project(
                ProjectModel=Project,
                owner_id=self.manager.pk,
                title="Must roll back",
                owner_lookup=lambda **kwargs: True,
                created_by_id=self.manager.pk,
            )

        self.assertFalse(Project.objects.filter(title="Must roll back").exists())

    @patch(
        "apps.projects.services.project_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_group_leader_assignment_rolls_back_when_audit_fails(self, _audit):
        group = ProjectGroup.objects.create(
            project=self.project,
            name="Atomic group",
            created_by=self.manager,
        )
        ProjectGroupMembership.objects.create(
            project=self.project,
            group=group,
            student=self.student,
            assigned_by=self.manager,
        )

        with self.assertRaises(RuntimeError):
            assign_group_leader(
                GroupModel=ProjectGroup,
                group_id=group.pk,
                student_id=self.student.pk,
                actor_id=self.manager.pk,
                project_id=self.project.pk,
                actor_authorizer=lambda **kwargs: True,
                member_lookup=lambda **kwargs: True,
            )

        group.refresh_from_db()
        self.assertIsNone(group.leader_id)

    @patch(
        "apps.projects.services.project_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_membership_delete_rolls_back_when_audit_fails(self, _audit):
        membership = ProjectGroupMembership.objects.create(
            project=self.project,
            student=self.student,
            assigned_by=self.manager,
        )
        membership_id = membership.pk

        with self.assertRaises(RuntimeError):
            remove_project_member(
                membership=membership,
                actor_id=self.manager.id,
                actor_authorizer=lambda **kwargs: True,
            )

        self.assertTrue(ProjectGroupMembership.objects.filter(pk=membership_id).exists())

    @patch(
        "apps.projects.services.project_service.write_audit_entry",
        side_effect=RuntimeError("audit unavailable"),
    )
    def test_milestone_delete_rolls_back_when_audit_fails(self, _audit):
        milestone = ProjectMilestone.objects.create(
            project=self.project,
            title="Audited milestone",
            created_by=self.manager,
        )
        milestone_id = milestone.pk

        with self.assertRaises(RuntimeError):
            delete_milestone(
                milestone=milestone,
                actor_id=self.manager.id,
                project_lookup=lambda project_id: Project.objects.get(pk=project_id),
                manager_lookup=lambda **kwargs: True,
            )

        self.assertTrue(ProjectMilestone.objects.filter(pk=milestone_id).exists())
