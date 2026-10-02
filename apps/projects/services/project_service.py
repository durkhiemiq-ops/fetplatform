"""Project lifecycle and task management service.

This module contains framework-agnostic business logic for project ownership,
project membership, task status updates, and lifecycle transitions. It does not
import Django request/response objects.

Relevant rules implemented:
- BR-100 Project ownership is required
- BR-101 Students may participate only when eligible or explicitly assigned
- BR-102 Student should not appear in the same project group more than once
- BR-103 Group leader assignment is project-scoped
- BR-104 Group leaders cannot change official assessment records
- BR-110 Each task must belong to a valid project
- BR-111 Tasks may be assigned to individuals, groups, or authorized participants
- BR-112 Task status must be valid and trackable
- BR-113 Task updates are limited to authorized users; official assessment remains lecturer-controlled
- BR-140 to BR-143 Project lifecycle: draft, active, completed, archived
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from core.common import ConfigurationError, utc_now
from core.audit import write_audit_entry


class ProjectError(ValueError):
    """Base project-domain error."""


class ProjectNotFoundError(ProjectError):
    """Raised when a project cannot be found."""


class UnauthorizedProjectActionError(ProjectError):
    """Raised when the caller is not allowed to act on the project."""


class ProjectMembershipError(ProjectError):
    """Raised when a membership rule is violated."""


class DuplicateGroupMembershipError(ProjectMembershipError):
    """Raised when a student is added to the same group twice."""


class InvalidProjectStatusError(ProjectError):
    """Raised when a project lifecycle status is invalid or disallowed."""


class TaskError(ProjectError):
    """Raised when task validation fails."""


class TaskNotFoundError(TaskError):
    """Raised when a task cannot be found."""


class TaskStatusError(TaskError):
    """Raised when a task's status is invalid or unauthorized."""


class ContributionError(ProjectError):
    """Raised when contribution evidence is invalid or unauthorized."""


class ArchiveError(ProjectError):
    """Raised when a project cannot be archived safely."""


class ProjectLike(Protocol):
    id: Any
    owner_id: Any
    supervisor_id: Any
    status: Any
    is_active: Any
    archived_at: Any
    created_by_id: Any

    def save(self) -> Any:
        ...


class ProjectGroupLike(Protocol):
    id: Any
    project_id: Any
    student_id: Any
    leader_id: Any

    def save(self) -> Any:
        ...


class ProjectTaskLike(Protocol):
    id: Any
    project_id: Any
    title: Any
    assignee_id: Any
    group_id: Any
    status: Any
    is_official: Any

    def save(self) -> Any:
        ...


VALID_PROJECT_STATUSES = {"draft", "active", "completed", "archived"}
VALID_TASK_STATUSES = {"todo", "in_progress", "completed"}


def _status_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_") if value is not None else ""


def _assert_project_exists(project: Any) -> None:
    if project is None:
        raise ProjectNotFoundError("Project not found")


def _assert_project_modifiable(project: Any, actor_id: Any) -> None:
    """Completed projects restrict edits; archived projects are read-only."""
    _assert_project_exists(project)
    status = _status_key(getattr(project, "status", None))
    if status == "archived":
        raise UnauthorizedProjectActionError("Archived projects are read-only")
    if status == "completed":
        raise UnauthorizedProjectActionError(
            "Completed projects may only be archived or viewed"
        )


def _assert_valid_project_status(status: str) -> None:
    normalized = _status_key(status)
    if normalized not in VALID_PROJECT_STATUSES:
        raise InvalidProjectStatusError(f"Invalid project status: {status}")


def _assert_valid_task_status(status: str) -> None:
    normalized = _status_key(status)
    if normalized not in VALID_TASK_STATUSES:
        raise TaskStatusError(f"Invalid task status: {status}")


def _default_task_authorized(actor_id: Any, task: Any) -> bool:
    """Allow only the task assignee or creator to update a task by default."""
    # BR-113: task updates are restricted to the assigned participant or creator.
    return getattr(task, "assignee_id", None) == actor_id or getattr(
        task, "created_by_id", None
    ) == actor_id


def create_project(
    *,
    ProjectModel: type[ProjectLike],
    owner_id: Any,
    title: str,
    status: str = "draft",
    owner_lookup: Optional[Any] = None,
    **kwargs: Any,
) -> ProjectLike:
    """Create a project with an authorized academic owner and lifecycle state."""
    # BR-100 and BR-140: every project has an owner and a draft lifecycle state
    # before activation.
    if ProjectModel is None:
        raise ConfigurationError("ProjectModel is required")
    if owner_id is None:
        raise UnauthorizedProjectActionError("Project owner is required")
    # BR-100, BR-170: the owner must be a real authorized academic identity.
    if owner_lookup is None:
        raise UnauthorizedProjectActionError("An owner authorization check is required")
    try:
        owner_valid = owner_lookup(owner_id=owner_id)
    except TypeError:
        owner_valid = owner_lookup(owner_id)
    if not bool(owner_valid):
        raise UnauthorizedProjectActionError("Project owner is not authorized")
    if not title or not str(title).strip():
        raise ProjectError("Project title is required")
    _assert_valid_project_status(status)
    if _status_key(status) != "draft":
        raise InvalidProjectStatusError("New projects must start in draft status")

    project = ProjectModel()
    project.owner_id = owner_id
    project.supervisor_id = owner_id
    project.status = status
    if hasattr(project, "title"):
        project.title = title
    if hasattr(project, "is_active"):
        project.is_active = status == "active"
    for key, value in kwargs.items():
        if hasattr(project, key):
            setattr(project, key, value)
    project.save()
    return project


def add_project_member(
    *,
    ProjectModel: type[ProjectLike],
    project_id: Any,
    student_id: Any,
    actor_id: Any,
    group_id: Optional[Any] = None,
    GroupMembershipModel: Optional[type[ProjectGroupLike]] = None,
    is_explicit_assignment: bool = True,
    actor_authorizer: Optional[Any] = None,
) -> Any:
    """Assign a student to a project or group when authorized and valid."""
    # BR-101, BR-102: eligibility and explicit assignment are required; a student
    # cannot occupy the same project group more than once.
    if ProjectModel is None:
        raise ConfigurationError("ProjectModel is required")

    project = ProjectModel.objects.get(id=project_id) if hasattr(ProjectModel, "objects") else None
    _assert_project_exists(project)
    _assert_project_modifiable(project, actor_id)
    if actor_authorizer is None:
        raise UnauthorizedProjectActionError("A project membership authorization check is required")
    if not bool(actor_authorizer(actor_id=actor_id, project=project)):
        raise UnauthorizedProjectActionError("Actor is not authorized to manage project membership")

    if GroupMembershipModel is not None:
        # BR-101/102: a student occupies a project at most once, whether or
        # not a group is being set on this assignment.
        existing = GroupMembershipModel.objects.filter(project_id=project_id, student_id=student_id)
        if hasattr(existing, "exists") and existing.exists():
            raise DuplicateGroupMembershipError("Student is already in this project")

    if not is_explicit_assignment:
        raise ProjectMembershipError("Project participation requires explicit assignment or eligibility")

    record = GroupMembershipModel() if GroupMembershipModel is not None else project
    if hasattr(record, "project_id"):
        record.project_id = project_id
    if hasattr(record, "student_id"):
        record.student_id = student_id
    if hasattr(record, "group_id"):
        record.group_id = group_id
    if hasattr(record, "assigned_by_id"):
        record.assigned_by_id = actor_id
    if hasattr(record, "status"):
        record.status = "active"
    if hasattr(record, "save"):
        record.save()
    return record


def assign_group_leader(
    *,
    GroupModel: type[ProjectGroupLike],
    group_id: Any,
    student_id: Any,
    actor_id: Any,
    project_id: Optional[Any] = None,
    actor_authorizer: Optional[Any] = None,
    member_lookup: Optional[Any] = None,
) -> ProjectGroupLike:
    """Assign a project group leader without altering official assessment records."""
    # BR-103 and BR-104: group leaders are project-scoped, and the leader must not
    # be allowed to change official lecturer assessments.
    if GroupModel is None:
        raise ConfigurationError("GroupModel is required")

    group = GroupModel.objects.get(id=group_id) if hasattr(GroupModel, "objects") else None
    if group is None:
        raise ProjectError("Project group not found")
    if actor_authorizer is None or member_lookup is None:
        raise UnauthorizedProjectActionError(
            "Authorization and group-membership checks are required"
        )
    if not bool(actor_authorizer(actor_id=actor_id, group=group)):
        raise UnauthorizedProjectActionError("Actor is not authorized to assign a group leader")
    if not bool(member_lookup(group_id=group_id, student_id=student_id)):
        raise ProjectMembershipError("Group leader must be a member of the group")

    if project_id is not None and hasattr(group, "project_id") and getattr(group, "project_id") != project_id:
        raise ProjectError("Group does not belong to the indicated project")

    if hasattr(group, "leader_id"):
        group.leader_id = student_id
    if hasattr(group, "updated_by_id"):
        group.updated_by_id = actor_id
    if hasattr(group, "save"):
        group.save()
    return group


def advance_project_status(
    *,
    project: Any,
    actor_id: Any,
    new_status: str,
) -> Any:
    """Move a project through the lifecycle states: draft → active → completed → archived."""
    # BR-140 through BR-143 define the controlled lifecycle. Career transitions
    # beyond the intended flow are rejected.
    _assert_project_exists(project)
    current_status = _status_key(getattr(project, "status", "draft"))
    _assert_valid_project_status(new_status)

    if actor_id not in {getattr(project, "owner_id", None), getattr(project, "supervisor_id", None), getattr(project, "created_by_id", None)}:
        raise UnauthorizedProjectActionError("Only the project owner or supervisor may change the project lifecycle")

    lifecycle = ["draft", "active", "completed", "archived"]
    current_index = lifecycle.index(current_status) if current_status in lifecycle else 0
    next_index = lifecycle.index(_status_key(new_status)) if _status_key(new_status) in lifecycle else -1
    if next_index < current_index:
        raise InvalidProjectStatusError("Project lifecycle transitions may not move backward")
    if next_index - current_index > 1:
        raise InvalidProjectStatusError("Project lifecycle may only move to the next defined state")

    project.status = new_status
    if hasattr(project, "is_active"):
        project.is_active = new_status == "active"
    if hasattr(project, "archived_at") and new_status == "archived":
        project.archived_at = utc_now()
    project.save()
    return project


def create_task(
    *,
    ProjectModel: type[ProjectLike],
    project_id: Any,
    title: str,
    actor_id: Any,
    status: str = "todo",
    assignee_id: Optional[Any] = None,
    assignee_group_id: Optional[Any] = None,
    TaskModel: Optional[type[ProjectTaskLike]] = None,
    participant_lookup: Optional[Any] = None,
) -> ProjectTaskLike:
    """Create a project task that belongs to a valid project and valid status."""
    # BR-110, BR-111, BR-112: every task belongs to a valid project and uses an
    # allowed status; assignment can be individual or group based.
    if TaskModel is None:
        raise ConfigurationError("TaskModel is required")
    project = ProjectModel.objects.get(id=project_id) if hasattr(ProjectModel, "objects") else None
    _assert_project_exists(project)
    _assert_project_modifiable(project, actor_id)
    if actor_id not in {getattr(project, "owner_id", None), getattr(project, "supervisor_id", None), getattr(project, "created_by_id", None)}:
        raise UnauthorizedProjectActionError("Only the project owner or supervisor may create tasks")
    if not title or not str(title).strip():
        raise TaskError("Task title is required")
    _assert_valid_task_status(status)
    if assignee_id is not None or assignee_group_id is not None:
        # BR-111, BR-170: assignments must target authorized project
        # participants or groups.
        if participant_lookup is None:
            raise TaskError("A participant authorization check is required for assignments")
        try:
            assigned = participant_lookup(
                project_id=project_id,
                assignee_id=assignee_id,
                group_id=assignee_group_id,
            )
        except TypeError:
            assigned = participant_lookup(project_id, assignee_id, assignee_group_id)
        if not bool(assigned):
            raise TaskError("Task assignee is not an authorized project participant")

    task = TaskModel()
    if hasattr(task, "project_id"):
        task.project_id = project_id
    if hasattr(task, "title"):
        task.title = title
    if hasattr(task, "assignee_id"):
        task.assignee_id = assignee_id
    if hasattr(task, "group_id"):
        task.group_id = assignee_group_id
    if hasattr(task, "status"):
        task.status = status
    if hasattr(task, "created_by_id"):
        task.created_by_id = actor_id
    task.save()
    return task


def update_task_status(
    *,
    task: Any,
    actor_id: Any,
    new_status: str,
    is_authorized: Optional[Any] = None,
    project_lookup: Optional[Any] = None,
) -> Any:
    """Update a task status only when the actor is authorized to manage it."""
    # BR-112 and BR-113: status must be valid and only authorized actors may
    # modify tasks; official assessment status stays controlled by the lecturer.
    if task is None:
        raise TaskNotFoundError("Task not found")
    _assert_valid_task_status(new_status)
    if project_lookup is None:
        raise TaskStatusError("A project lookup is required for task updates")
    project = project_lookup(project_id=getattr(task, "project_id", None))
    _assert_project_modifiable(project, actor_id)

    if is_authorized is None:
        is_authorized = _default_task_authorized

    if not bool(is_authorized(actor_id, task)):
        raise UnauthorizedProjectActionError("Actor is not authorized to update this task")

    task.status = new_status
    if hasattr(task, "updated_by_id"):
        task.updated_by_id = actor_id
    task.save()
    return task


def _require_project_participant(
    project_id: Any,
    student_id: Any,
    *,
    participant_lookup: Optional[Any],
) -> None:
    # BR-101, BR-120, BR-121: project activity must belong to an eligible or
    # explicitly assigned participant.
    if participant_lookup is None:
        return
    try:
        valid = participant_lookup(project_id=project_id, student_id=student_id)
    except TypeError:
        valid = participant_lookup(project_id, student_id)
    if not bool(valid):
        raise ProjectMembershipError("Student is not an authorized project participant")


def record_contribution(
    *,
    ContributionModel: type[Any],
    project_id: Any,
    student_id: Any,
    evidence_type: str,
    evidence_ref: Any,
    participant_lookup: Optional[Any] = None,
    evidence_lookup: Optional[Any] = None,
    actor_id: Optional[Any] = None,
) -> Any:
    """Record contribution evidence that maps to real project activity."""
    # BR-120, BR-121: contributions require real evidence from an authorized
    # participant and cannot be fabricated as freeform claims.
    if ContributionModel is None:
        raise ConfigurationError("ContributionModel is required")
    if project_id is None or student_id is None:
        raise ProjectMembershipError("Project and student are required")
    if evidence_ref is None or not str(evidence_type or "").strip():
        raise TaskError("Contribution evidence type and reference are required")
    if actor_id is None or participant_lookup is None or evidence_lookup is None:
        raise ProjectMembershipError(
            "Actor, participant, and evidence checks are required"
        )
    if str(actor_id) != str(student_id):
        raise ProjectMembershipError(
            "A student may only submit contribution evidence for themselves"
        )
    _require_project_participant(
        project_id,
        student_id,
        participant_lookup=participant_lookup,
    )
    try:
        valid = evidence_lookup(
            project_id=project_id,
            student_id=student_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
        )
    except TypeError:
        valid = evidence_lookup(project_id, student_id, evidence_type, evidence_ref)
    if not bool(valid):
        raise ProjectMembershipError("Contribution evidence is not linked to project activity")

    contribution = ContributionModel()
    for name, value in (
        ("project_id", project_id),
        ("student_id", student_id),
        ("evidence_type", str(evidence_type).strip().lower().replace(" ", "_")),
        ("evidence_ref", evidence_ref),
        ("status", "pending_review"),
        ("created_by_id", actor_id),
    ):
        if value is not None and hasattr(contribution, name):
            setattr(contribution, name, value)
    if hasattr(contribution, "created_at"):
        contribution.created_at = utc_now()
    contribution.save()
    return contribution


def review_contribution(
    *,
    contribution: Any,
    lecturer_id: Any,
    approved: bool,
    lecturer_authorizer: Optional[Any] = None,
    notes: Optional[str] = None,
) -> Any:
    """Review contribution evidence before it is used for assessment."""
    # BR-122: lecturer review is required before contribution evidence is used.
    if contribution is None or lecturer_id is None:
        raise ProjectMembershipError("Contribution and lecturer are required")
    if lecturer_authorizer is None:
        raise ContributionError("A lecturer authorization check is required")
    if not bool(
        lecturer_authorizer(lecturer_id=lecturer_id, contribution=contribution)
    ):
        raise UnauthorizedProjectActionError("Lecturer is not authorized to review this contribution")
    if hasattr(contribution, "status"):
        contribution.status = "approved" if approved else "rejected"
    if hasattr(contribution, "reviewed_by_id"):
        contribution.reviewed_by_id = lecturer_id
    if hasattr(contribution, "reviewed_at"):
        contribution.reviewed_at = utc_now()
    if notes is not None and hasattr(contribution, "notes"):
        contribution.notes = notes
    contribution.save()
    # BR-122, BR-210: contribution review is a significant academic action.
    write_audit_entry(
        action="contribution_reviewed",
        resource_type="contribution",
        resource_id=getattr(contribution, "id", None),
        actor_id=lecturer_id,
        details={"approved": approved, "project_id": getattr(contribution, "project_id", None)},
    )
    return contribution


class MilestoneError(ProjectError):
    """Raised when milestone validation fails."""


class MilestoneNotFoundError(MilestoneError):
    """Raised when a milestone cannot be found."""


def _participant_can_manage(project_id: Any, actor_id: Any, *, participant_lookup: Optional[Any], manager_lookup: Optional[Any] = None) -> bool:
    """Owner/supervisor/creator always manage; participants may if the view
    passes its manager predicate (same predicate that gates tasks).
    """
    if manager_lookup is not None:
        try:
            return bool(manager_lookup(actor_id=actor_id, project_id=project_id))
        except TypeError:
            return bool(manager_lookup(actor_id, project_id))
    if participant_lookup is None:
        return False
    try:
        return bool(participant_lookup(project_id=project_id, student_id=actor_id))
    except TypeError:
        return bool(participant_lookup(project_id, actor_id))


def create_milestone(
    *,
    ProjectModel: type[ProjectLike],
    project_id: Any,
    title: str,
    actor_id: Any,
    progress: int = 0,
    due_date: Optional[Any] = None,
    MilestoneModel: Optional[type[Any]] = None,
    participant_lookup: Optional[Any] = None,
    manager_lookup: Optional[Any] = None,
) -> Any:
    """Create a project milestone for an authorized participant.

    Mirrors task rules (BR-110 domain): the project must exist, be modifiable,
    the actor must be a project participant/manager, and progress must sit in
    the 0-100 band.  Writes are audited (BR-210).
    """
    if MilestoneModel is None:
        raise ConfigurationError("MilestoneModel is required")
    project = ProjectModel.objects.get(id=project_id) if hasattr(ProjectModel, "objects") else None
    _assert_project_exists(project)
    _assert_project_modifiable(project, actor_id)
    if not _participant_can_manage(
        project_id, actor_id, participant_lookup=participant_lookup, manager_lookup=manager_lookup
    ):
        raise UnauthorizedProjectActionError(
            "Actor is not authorized to manage milestones for this project"
        )
    if not title or not str(title).strip():
        raise MilestoneError("Milestone title is required")
    if not isinstance(progress, int) or progress < 0 or progress > 100:
        raise MilestoneError("Milestone progress must be between 0 and 100")

    milestone = MilestoneModel()
    milestone.project_id = project_id
    milestone.title = title
    milestone.progress = progress
    if due_date is not None and hasattr(milestone, "due_date"):
        milestone.due_date = due_date
    if hasattr(milestone, "created_by_id"):
        milestone.created_by_id = actor_id
    milestone.save()

    write_audit_entry(
        action="milestone_created",
        resource_type="project_milestone",
        resource_id=milestone.id,
        actor_id=actor_id,
        details={"project_id": project_id, "title": title},
    )
    return milestone


def update_milestone(
    *,
    milestone: Any,
    actor_id: Any,
    updates: dict,
    project_lookup: Optional[Any] = None,
    participant_lookup: Optional[Any] = None,
    manager_lookup: Optional[Any] = None,
) -> Any:
    """Update a milestone's mutable fields; audit the change (BR-210)."""
    if milestone is None:
        raise MilestoneNotFoundError("Milestone not found")
    if project_lookup is None:
        raise MilestoneError("A project lookup is required for milestone updates")
    project = project_lookup(project_id=getattr(milestone, "project_id", None))
    _assert_project_modifiable(project, actor_id)
    if not _participant_can_manage(
        getattr(milestone, "project_id", None),
        actor_id,
        participant_lookup=participant_lookup,
        manager_lookup=manager_lookup,
    ):
        raise UnauthorizedProjectActionError(
            "Actor is not authorized to manage milestones for this project"
        )

    allowed = {"title", "progress", "due_date"}
    old_values = {}
    for key, value in (updates or {}).items():
        if key not in allowed:
            continue
        if key == "progress" and (not isinstance(value, int) or value < 0 or value > 100):
            raise MilestoneError("Milestone progress must be between 0 and 100")
        if key == "title" and (not value or not str(value).strip()):
            raise MilestoneError("Milestone title is required")
        old_values[key] = getattr(milestone, key, None)
        setattr(milestone, key, value)
    if not old_values:
        raise MilestoneError("No valid milestone fields provided")
    milestone.save()
    write_audit_entry(
        action="milestone_updated",
        resource_type="project_milestone",
        resource_id=getattr(milestone, "id", None),
        actor_id=actor_id,
        old_value=old_values,
        new_value={k: getattr(milestone, k, None) for k in old_values},
    )
    return milestone


def delete_milestone(
    *,
    milestone: Any,
    actor_id: Any,
    project_lookup: Optional[Any] = None,
    participant_lookup: Optional[Any] = None,
    manager_lookup: Optional[Any] = None,
) -> None:
    """Delete a milestone; audit (BR-210)."""
    if milestone is None:
        raise MilestoneNotFoundError("Milestone not found")
    if project_lookup is None:
        raise MilestoneError("A project lookup is required for milestone deletion")
    project = project_lookup(project_id=getattr(milestone, "project_id", None))
    _assert_project_modifiable(project, actor_id)
    if not _participant_can_manage(
        getattr(milestone, "project_id", None),
        actor_id,
        participant_lookup=participant_lookup,
        manager_lookup=manager_lookup,
    ):
        raise UnauthorizedProjectActionError(
            "Actor is not authorized to manage milestones for this project"
        )
    milestone_id = getattr(milestone, "id", None)
    title = getattr(milestone, "title", None)
    milestone.delete()
    write_audit_entry(
        action="milestone_deleted",
        resource_type="project_milestone",
        resource_id=milestone_id,
        actor_id=actor_id,
        details={"title": title},
    )


def archive_project(
    *,
    project: Any,
    actor_id: Any,
    audit_logger: Optional[Any] = None,
) -> Any:
    """Archive a completed project without deleting its relationship chain."""
    # BR-140 to BR-143: only completed projects may move to ARCHIVED.
    _assert_project_exists(project)
    if _status_key(getattr(project, "status", None)) != "completed":
        raise ArchiveError("Only completed projects may be archived")
    if actor_id not in {
        getattr(project, "owner_id", None),
        getattr(project, "supervisor_id", None),
        getattr(project, "created_by_id", None),
    }:
        raise UnauthorizedProjectActionError("Only the project owner or supervisor may archive the project")

    # BR-160, BR-161: archive by status transition only; preserve all related
    # records and make ordinary post-archive edits unavailable.
    project.status = "archived"
    if hasattr(project, "is_active"):
        project.is_active = False
    if hasattr(project, "archived_at"):
        project.archived_at = utc_now()
    project.save()
    # BR-161: archiving must always produce an audit record.
    if audit_logger is not None:
        audit_logger(
            action="project_archived",
            project_id=getattr(project, "id", None),
            actor_id=actor_id,
        )
    else:
        write_audit_entry(
            action="project_archived",
            resource_type="project",
            resource_id=getattr(project, "id", None),
            actor_id=actor_id,
            details={"status": "archived"},
        )
    return project
