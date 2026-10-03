from rest_framework import serializers

from apps.accounts.models import User

from .models import (
    Project,
    ProjectContribution,
    ProjectGroup,
    ProjectGroupMembership,
    ProjectMilestone,
    ProjectTask,
)


def _full_name(user) -> str:
    return f"{user.first_name} {user.last_name}".strip()


class ProjectSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    supervisor_name = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "owner",
            "owner_name",
            "supervisor",
            "supervisor_name",
            "status",
            "is_active",
            "archived_at",
            "created_by",
            "created_at",
        ]

    def get_owner_name(self, obj) -> str:
        return _full_name(obj.owner)

    def get_supervisor_name(self, obj) -> str:
        return _full_name(obj.supervisor) if obj.supervisor else None


class ProjectGroupSerializer(serializers.ModelSerializer):
    leader_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectGroup
        fields = ["id", "project", "name", "leader", "leader_name", "created_by", "created_at"]

    def get_leader_name(self, obj) -> str:
        return _full_name(obj.leader) if obj.leader else None


class MembershipSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectGroupMembership
        fields = [
            "id",
            "project",
            "group",
            "student",
            "student_name",
            "assigned_by",
            "status",
            "created_at",
        ]

    def get_student_name(self, obj) -> str:
        return _full_name(obj.student)


class TaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectTask
        fields = [
            "id",
            "project",
            "title",
            "assignee",
            "assignee_name",
            "group",
            "status",
            "is_official",
            "created_by",
            "created_at",
        ]

    def get_assignee_name(self, obj) -> str:
        return _full_name(obj.assignee) if obj.assignee else None


class ContributionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectContribution
        fields = [
            "id",
            "project",
            "student",
            "student_name",
            "evidence_type",
            "evidence_ref",
            "status",
            "notes",
            "created_by",
            "reviewed_by",
            "reviewed_at",
            "created_at",
        ]

    def get_student_name(self, obj) -> str:
        return _full_name(obj.student)


class MilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMilestone
        fields = [
            "id",
            "project",
            "title",
            "progress",
            "due_date",
            "created_by",
            "created_at",
        ]


class MilestoneCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    progress = serializers.IntegerField(min_value=0, max_value=100, default=0, required=False)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"title", "progress", "due_date"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class MilestoneUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    progress = serializers.IntegerField(min_value=0, max_value=100, required=False)
    due_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"title", "progress", "due_date"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


# ===== input payloads =====


class ProjectCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)


class ProjectStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c.value for c in Project.Status])


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, allow_blank=True, default="")


class MemberCreateSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    group = serializers.UUIDField(required=False, allow_null=True, default=None)


class TaskCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    status = serializers.ChoiceField(
        choices=[c.value for c in ProjectTask.Status], default="todo", required=False
    )
    assignee = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True, default=None
    )
    group = serializers.UUIDField(required=False, allow_null=True, default=None)

    # NOTE: there is deliberately no `validate_group` existence probe here.
    # It used to be `ProjectGroup.objects.filter(pk=value).exists()` -- a
    # system-wide existence check that could not know which project the task
    # belonged to, because the project id is not in the payload. It therefore
    # accepted a group owned by an unrelated project (IDOR). Ownership is
    # now enforced project-scoped in the service, which does receive the
    # project, and it raises a 403 for both "no such group" and "group owned
    # by another project" so this endpoint is not a group-id oracle.


class TaskStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c.value for c in ProjectTask.Status])


class ContributionCreateSerializer(serializers.Serializer):
    """Only activity-linked evidence qualifies (BR-120/121 — no freeform claims)."""

    evidence_type = serializers.ChoiceField(choices=["task"])
    evidence_ref = serializers.CharField(max_length=512)


class ContributionReviewSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
