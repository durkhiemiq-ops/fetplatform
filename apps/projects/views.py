"""Project API — lifecycle, groups, tasks, contributions (BR-100 to BR-161).

All business rules (ownership, lifecycle transitions, membership uniqueness,
task authorization, contribution evidence, lecturer review) are enforced by
apps.projects.services.project_service; this module only translates HTTP to
service calls and domain errors to the standard error envelope.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from core.academic_access import is_admin_user, is_authorized_academic_user

from .models import (
    Project,
    ProjectContribution,
    ProjectGroup,
    ProjectGroupMembership,
    ProjectMilestone,
    ProjectTask,
)
from .serializers import (
    ContributionCreateSerializer,
    ContributionReviewSerializer,
    ContributionSerializer,
    GroupCreateSerializer,
    MemberCreateSerializer,
    MembershipSerializer,
    MilestoneCreateSerializer,
    MilestoneSerializer,
    MilestoneUpdateSerializer,
    ProjectCreateSerializer,
    ProjectGroupSerializer,
    ProjectSerializer,
    ProjectStatusSerializer,
    TaskCreateSerializer,
    TaskSerializer,
    TaskStatusSerializer,
)
from .services.project_service import (
    ArchiveError,
    DuplicateGroupMembershipError,
    InvalidProjectStatusError,
    MilestoneError,
    MilestoneNotFoundError,
    ProjectError,
    ProjectMembershipError,
    ProjectNotFoundError,
    TaskError,
    TaskStatusError,
    UnauthorizedProjectActionError,
    add_project_member,
    advance_project_status,
    archive_project,
    create_milestone,
    create_project,
    create_task,
    delete_milestone,
    record_contribution,
    review_contribution,
    update_milestone,
    update_task_status,
)


def _error(code, message, http_status):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


def _can_manage(user, project) -> bool:
    """Owner/supervisor/creator or platform admin (same predicate the service
    authorizers use for membership, tasks, and contribution review)."""
    if user is None or project is None:
        return False
    if is_admin_user(user):
        return True
    return user.id in {project.owner_id, project.supervisor_id, project.created_by_id}


def _visible_projects(user):
    """BR-100-adjacent visibility: owners/supervisors see their projects,
    participants see the ones they belong to, admins see everything."""
    queryset = Project.objects.all().select_related("owner", "supervisor", "created_by")
    if is_admin_user(user):
        return queryset
    return queryset.filter(
        Q(owner=user)
        | Q(supervisor=user)
        | Q(created_by=user)
        | Q(memberships__student=user)
    ).distinct()


def _owner_lookup(owner_id) -> bool:
    """create_project's BR-100/170 authorization probe: owner must be a real,
    authorized academic identity."""
    owner = User.objects.filter(pk=owner_id).first()
    return is_authorized_academic_user(owner)


def _participant_lookup(
    project_id, assignee_id=None, group_id=None, student_id=None
) -> bool:
    """Shared participant probe for tasks (assignee/group) and contributions
    (student): membership, or project ownership."""
    student = assignee_id if assignee_id is not None else student_id
    if student is None:
        if group_id is None:
            return False
        return ProjectGroupMembership.objects.filter(
            project_id=project_id, group_id=group_id
        ).exists()
    if ProjectGroupMembership.objects.filter(
        project_id=project_id, student_id=student
    ).exists():
        return True
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return False
    return student in {project.owner_id, project.supervisor_id, project.created_by_id}


def _evidence_lookup(
    project_id, student_id=None, evidence_type=None, evidence_ref=None
) -> bool:
    """BR-120/121: evidence must reference real activity inside this project —
    currently a task belonging to the same project."""
    if str(evidence_type or "").strip().lower() != "task":
        return False
    try:
        return ProjectTask.objects.filter(
            pk=evidence_ref, project_id=project_id
        ).exists()
    except (ValueError, DjangoValidationError, TypeError):
        return False


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success(ProjectSerializer(_visible_projects(request.user), many=True).data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # BR-100/140: service requires an authorized academic owner and
            # forces the initial draft state.
            project = create_project(
                ProjectModel=Project,
                owner_id=request.user.id,
                title=serializer.validated_data["title"],
                owner_lookup=_owner_lookup,
                created_by_id=request.user.id,
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except InvalidProjectStatusError as exc:
            return _error("INVALID_STATUS", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(ProjectSerializer(project).data, 201)


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = _visible_projects(request.user).filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        return _success(
            {
                "project": ProjectSerializer(project).data,
                "groups": ProjectGroupSerializer(
                    project.groups.select_related("leader"), many=True
                ).data,
                "members": MembershipSerializer(
                    project.memberships.select_related("student"), many=True
                ).data,
                "tasks": TaskSerializer(
                    project.tasks.select_related("assignee"), many=True
                ).data,
                "contributions": ContributionSerializer(
                    project.contributions.select_related("student"), many=True
                ).data,
                "milestones": MilestoneSerializer(
                    project.milestones.select_related("created_by"), many=True
                ).data,
            }
        )

    def patch(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        serializer = ProjectStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        try:
            if new_status == "archived":
                # BR-160/161: archive path has the strictest rules + audit.
                project = archive_project(project=project, actor_id=request.user.id)
            else:
                # BR-140..143: forward, one-step lifecycle transitions only.
                project = advance_project_status(
                    project=project, actor_id=request.user.id, new_status=new_status
                )
        except ProjectNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except (InvalidProjectStatusError, ArchiveError) as exc:
            return _error("INVALID_STATUS", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(ProjectSerializer(project).data)


class ProjectGroupCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        if not _can_manage(request.user, project):
            return _error(
                "UNAUTHORIZED",
                "Only the project owner or supervisor may manage groups.",
                403,
            )
        serializer = GroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = ProjectGroup.objects.create(
            project=project,
            name=serializer.validated_data["name"],
            created_by=request.user,
        )
        return _success(ProjectGroupSerializer(group).data, 201)


class ProjectMemberCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        serializer = MemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        group_id = validated.get("group")
        if group_id is not None and not ProjectGroup.objects.filter(pk=group_id).exists():
            return _error("INVALID_INPUT", "Group does not exist.", 400)
        try:
            # BR-101/102: explicit assignment, authorization, no duplicates.
            record = add_project_member(
                ProjectModel=Project,
                project_id=project.pk,
                student_id=validated["student"].pk,
                actor_id=request.user.id,
                group_id=group_id,
                GroupMembershipModel=ProjectGroupMembership,
                is_explicit_assignment=True,
                actor_authorizer=lambda actor_id, project: _can_manage(
                    request.user, project
                ),
            )
        except DuplicateGroupMembershipError as exc:
            return _error("DUPLICATE_MEMBER", str(exc), 409)
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except ProjectMembershipError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(MembershipSerializer(record).data, 201)


class ProjectTaskCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        assignee = validated.get("assignee")
        try:
            # BR-110/111/112: valid project, authorized creator, valid status,
            # participants only for assignments.
            task = create_task(
                ProjectModel=Project,
                project_id=project.pk,
                title=validated["title"],
                actor_id=request.user.id,
                status=validated.get("status", "todo"),
                assignee_id=assignee.pk if assignee else None,
                assignee_group_id=validated.get("group"),
                TaskModel=ProjectTask,
                participant_lookup=_participant_lookup,
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except TaskStatusError as exc:
            return _error("INVALID_STATUS", str(exc), 400)
        except TaskError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(TaskSerializer(task).data, 201)


class TaskStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        task = ProjectTask.objects.filter(pk=pk).first()
        if task is None:
            return _error("NOT_FOUND", "Task not found.", 404)
        serializer = TaskStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # BR-112/113: valid transition + assignee/creator-only updates.
            task = update_task_status(
                task=task,
                actor_id=request.user.id,
                new_status=serializer.validated_data["status"],
                project_lookup=lambda project_id: Project.objects.get(pk=project_id),
            )
        except ProjectNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except TaskStatusError as exc:
            return _error("INVALID_STATUS", str(exc), 400)
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(TaskSerializer(task).data)


class ProjectContributionCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        serializer = ContributionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        # Precise codes for the two distinct failures; the service re-enforces
        # both paths afterwards (pre-checks only improve the envelope).
        if not _participant_lookup(project_id=project.pk, student_id=request.user.id):
            return _error(
                "NOT_PARTICIPANT", "You are not a participant of this project.", 403
            )
        if not _evidence_lookup(
            project_id=project.pk,
            evidence_type=validated["evidence_type"],
            evidence_ref=validated["evidence_ref"],
        ):
            return _error(
                "INVALID_EVIDENCE",
                "Contribution evidence must link to a task in this project.",
                400,
            )
        try:
            # BR-120/121: self-only submission, participant + evidence checks.
            contribution = record_contribution(
                ContributionModel=ProjectContribution,
                project_id=project.pk,
                student_id=request.user.id,
                evidence_type=validated["evidence_type"],
                evidence_ref=validated["evidence_ref"],
                participant_lookup=_participant_lookup,
                evidence_lookup=_evidence_lookup,
                actor_id=request.user.id,
            )
        except TaskError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        except ProjectMembershipError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(ContributionSerializer(contribution).data, 201)


class ContributionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = ProjectContribution.objects.filter(
            Q(student=request.user) | Q(project__in=_visible_projects(request.user))
        ).select_related("student", "project").distinct()
        return _success(ContributionSerializer(queryset, many=True).data)


class ContributionReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        contribution = ProjectContribution.objects.filter(pk=pk).select_related(
            "project"
        ).first()
        if contribution is None:
            return _error("NOT_FOUND", "Contribution not found.", 404)
        serializer = ContributionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            # BR-122/210: only the project's academics may review, and the
            # review always writes an audit event.
            contribution = review_contribution(
                contribution=contribution,
                lecturer_id=request.user.id,
                approved=validated["approved"],
                lecturer_authorizer=lambda lecturer_id, contribution: (
                    is_authorized_academic_user(request.user)
                    and _can_manage(request.user, contribution.project)
                ),
                notes=validated.get("notes") or None,
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except ProjectMembershipError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        return _success(ContributionSerializer(contribution).data)


class ProjectMilestoneListCreateView(APIView):
    """Milestones for a project; participants read, managers write.

    Milestones are official tracking surfaces, so writes go through the same
    `_can_manage` predicate that gates tasks (BR-113 spirit): only the project
    owner/supervisor/creator or an administrator — not raw members.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        project = _visible_projects(request.user).filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        milestones = project.milestones.select_related("created_by").all()
        return _success(MilestoneSerializer(milestones, many=True).data)

    def post(self, request, pk):
        project = Project.objects.filter(pk=pk).first()
        if project is None:
            return _error("NOT_FOUND", "Project not found.", 404)
        serializer = MilestoneCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            milestone = create_milestone(
                ProjectModel=Project,
                project_id=project.pk,
                title=validated["title"],
                actor_id=request.user.id,
                progress=validated.get("progress", 0),
                due_date=validated.get("due_date"),
                MilestoneModel=ProjectMilestone,
                manager_lookup=lambda actor_id, project_id: _can_manage(
                    request.user, project
                ),
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except ProjectNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except MilestoneError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(MilestoneSerializer(milestone).data, 201)


class ProjectMilestoneDetailView(APIView):
    """PATCH/DELETE a single milestone. Non-manager denial mirrors not-found."""

    permission_classes = [IsAuthenticated]

    def _milestone(self, request, pk):
        milestone = ProjectMilestone.objects.filter(pk=pk).select_related("project").first()
        if milestone is None:
            return None, _error("NOT_FOUND", "Milestone not found.", 404)
        return milestone, None

    def patch(self, request, pk):
        milestone, err = self._milestone(request, pk)
        if err is not None:
            return err
        serializer = MilestoneUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            milestone = update_milestone(
                milestone=milestone,
                actor_id=request.user.id,
                updates=serializer.validated_data,
                project_lookup=lambda project_id: Project.objects.get(pk=project_id),
                manager_lookup=lambda actor_id, project_id: _can_manage(
                    request.user, milestone.project
                ),
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except MilestoneNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except MilestoneError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(MilestoneSerializer(milestone).data)

    def delete(self, request, pk):
        milestone, err = self._milestone(request, pk)
        if err is not None:
            return err
        try:
            delete_milestone(
                milestone=milestone,
                actor_id=request.user.id,
                project_lookup=lambda project_id: Project.objects.get(pk=project_id),
                manager_lookup=lambda actor_id, project_id: _can_manage(
                    request.user, milestone.project
                ),
            )
        except UnauthorizedProjectActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except MilestoneNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except ProjectError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success({"deleted": True})
