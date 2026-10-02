"""Project lifecycle persistence matching the project service contract.

Covers BR-100 to BR-143: projects, groups, memberships, tasks, and
contribution evidence.  Field names mirror the service's Protocol shapes
(``owner_id``, ``leader_id``, ``assignee_id``, ...) so the service can write
attributes directly on model instances.
"""

import uuid

from django.db import models


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    owner = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="owned_projects"
    )
    supervisor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_projects",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_active = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_project"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ProjectGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=150, blank=True)
    leader = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_group"
        ordering = ["created_at"]

    def __str__(self):
        return self.name or f"Group {self.pk}"


class ProjectGroupMembership(models.Model):
    """BR-102: a student occupies a given project group at most once."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    group = models.ForeignKey(
        ProjectGroup, on_delete=models.CASCADE, null=True, blank=True, related_name="memberships"
    )
    student = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="project_memberships"
    )
    assigned_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    status = models.CharField(max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_group_membership"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "student"], name="unique_student_per_group"
            ),
        ]

    def __str__(self):
        return f"{self.student_id} in {self.group_id or self.project_id}"


class ProjectTask(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=255)
    assignee = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    group = models.ForeignKey(
        ProjectGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    is_official = models.BooleanField(
        default=False,
        help_text="Official assessment tasks stay lecturer-controlled (BR-113).",
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_task"
        ordering = ["created_at"]

    def __str__(self):
        return self.title


class ProjectMilestone(models.Model):
    """Project milestone with progress tracking.

    Follows the same lifecycle discipline as ProjectTask: completed/archived
    projects read-only. Authorization is participant-scoped — same predicate
    as tasks (``_can_manage`` in views).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="milestones"
    )
    title = models.CharField(max_length=255)
    progress = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-100",
    )
    due_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_milestone"
        ordering = ["created_at"]

    def __str__(self):
        return self.title


class ProjectContribution(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="contributions")
    student = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="project_contributions"
    )
    evidence_type = models.CharField(max_length=64)
    evidence_ref = models.CharField(max_length=512)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_REVIEW)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "projects_contribution"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.evidence_type}:{self.evidence_ref}"
