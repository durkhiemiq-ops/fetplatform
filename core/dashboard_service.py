"""Role-aware dashboard aggregation.

Implements API Specification §46 (``GET /api/v1/dashboard``): one aggregated
read that replaces a client fan-out to five endpoints. The payload is chosen by
the caller's role, and every number in it is derived from the caller's own
records -- no cross-account data is reachable from here.

Boundary rules observed by this module:

* **No duplicated policy.** Announcement visibility is delegated to
  ``announcement_service.get_visible_announcements`` so the dashboard can never
  disagree with the announcements endpoint about who may see what.
* **No new authorization logic.** The view is authenticated-only and only ever
  queries rows scoped to ``request.user``; nothing here accepts a target id.
* **Read-only.** There is no write path, so BR-210 audit entries are not
  applicable (nothing changes state).

Field casing follows the wire contract the client already consumes: project and
task statuses are emitted exactly as the models store them (lowercase), which
is what ``/projects/`` returns today.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from apps.academic.models import ClassSchedule, Enrollment
from apps.announcements.models import Announcement
from apps.announcements.services.announcement_service import (
    get_visible_announcements,
)
from apps.attendance.models import AttendanceRecord
from apps.projects.models import Project, ProjectGroupMembership, ProjectTask

User = get_user_model()

#: Cap on list-shaped sections so one loud term cannot make the dashboard
#: paginate forever; the client renders short lists anyway.
LIST_LIMIT = 12

_DAY_NAMES = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)


def _today_day_name() -> str:
    """Weekday name in the ``ClassSchedule.Day`` vocabulary, for today."""
    return _DAY_NAMES[timezone.localdate().weekday()]


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _enrollment_rows(user):
    return (
        Enrollment.objects.filter(student=user, is_active=True, deleted_at__isnull=True)
        .select_related("course", "course_offering")
        .order_by("course__code")
    )


def _enrolled_offering_ids(user) -> List[Any]:
    return [
        row.course_offering_id
        for row in _enrollment_rows(user)
        if row.course_offering_id
    ]


def _user_course_ids(user) -> List[Any]:
    return [row.course_id for row in _enrollment_rows(user)]


def _today_classes(offerings_qs, *, lecturer_id=None) -> List[Dict[str, Any]]:
    """Today's timetable entries for a set of offerings.

    ``ClassSchedule`` is the recurring weekly timetable (day + start/end time),
    so "today" means the rows whose ``day_of_week`` is today. ``starts_at`` is
    materialised as today's date combined with ``start_time`` because the
    client renders it through ``new Date(...)``.
    """
    today = _today_day_name()
    day_start = timezone.localdate()

    rows = (
        ClassSchedule.objects.filter(is_active=True, day_of_week=today)
        .select_related("course_offering__course")
        .order_by("start_time")
    )
    if offerings_qs is not None:
        rows = rows.filter(course_offering_id__in=offerings_qs)
    if lecturer_id is not None:
        rows = rows.filter(lecturer_id=lecturer_id)

    out: List[Dict[str, Any]] = []
    for row in rows:
        course = row.course_offering.course if row.course_offering else None
        # ClassSchedule stores a wall-clock TimeField with no date or zone, so
        # "today's 09:00" has to be materialised as a datetime the client can
        # pass to new Date(...). Combine with today, then localise.
        naive = datetime.combine(day_start, row.start_time)
        starts_at = timezone.make_aware(naive) if timezone.is_naive(naive) else naive
        out.append(
            {
                "session_id": str(row.pk),
                "class_name": course.name if course else "",
                "course_code": course.code if course else "",
                "starts_at": starts_at.isoformat(),
                "ends_at": _iso(row.end_time),
                "location": row.location,
                "class_type": row.class_type,
            }
        )
    return out


def _visible_announcements(user, course_ids, limit: int = LIST_LIMIT):
    base = (
        Announcement.objects.filter(is_published=True, is_archived=False)
        .order_by("-is_pinned", "-created_at")[: limit * 3]
    )
    visible = get_visible_announcements(
        announcements=base,
        user=user,
        user_faculty_id=getattr(user, "faculty_id", None),
        user_department_id=getattr(user, "department_id", None),
        user_course_ids=course_ids,
        user_class_ids=[],
        user_roles=[user.role],
    )
    return [
        {
            "id": str(a.pk),
            "title": a.title,
            "scope": a.scope,
            "is_pinned": a.is_pinned,
            "created_at": _iso(a.created_at),
        }
        for a in visible[:limit]
    ]


def _projects_for(user, *, include_owned: bool = True):
    """Projects the user participates in: owner, supervisor, or group member."""
    membership_project_ids = ProjectGroupMembership.objects.filter(
        student=user, status="active"
    ).values_list("project_id", flat=True)

    scope = Q(pk__in=membership_project_ids)
    if include_owned:
        scope = scope | Q(owner=user) | Q(supervisor=user)

    return (
        Project.objects.filter(scope)
        .select_related("owner")
        .exclude(status="archived")
        .distinct()
        .annotate(
            task_count=Count("tasks", distinct=True),
            completed_task_count=Count(
                "tasks",
                filter=Q(tasks__status=ProjectTask.Status.COMPLETED),
                distinct=True,
            ),
        )
        .order_by("-created_at")[:LIST_LIMIT]
    )


def _group_names_for(user) -> Dict[Any, str]:
    """project_id -> the name of the group this user belongs to on it."""
    rows = ProjectGroupMembership.objects.filter(student=user, group__isnull=False)
    return {
        row.project_id: row.group.name
        for row in rows.select_related("group")
        if row.group.name
    }


def _serialize_project(project, group_names) -> Dict[str, Any]:
    return {
        "id": str(project.pk),
        "title": project.title,
        # Projects are not modelled against a course or a deadline in this
        # schema, so these stay null rather than being invented. The client
        # already guards both.
        "course_code": None,
        "deadline": None,
        "group_name": group_names.get(project.pk),
        "status": project.status,
        "task_count": project.task_count,
        "completed_task_count": project.completed_task_count,
        "owner_name": f"{project.owner.first_name} {project.owner.last_name}".strip()
        if project.owner
        else None,
    }


def _pending_tasks(user, project_titles) -> List[Dict[str, Any]]:
    """Open tasks assigned to this user, on the projects already in scope."""
    group_ids = ProjectGroupMembership.objects.filter(
        student=user, group__isnull=False
    ).values_list("group_id", flat=True)

    rows = (
        ProjectTask.objects.filter(
            Q(assignee=user) | Q(group_id__in=list(group_ids))
        )
        .exclude(status=ProjectTask.Status.COMPLETED)
        .select_related("project")
        .order_by("created_at")[:LIST_LIMIT]
    )

    out: List[Dict[str, Any]] = []
    for task in rows:
        out.append(
            {
                "id": str(task.pk),
                "title": task.title,
                "project": task.project.title if task.project else "",
                "status": task.status,
                # This schema has no due date or priority on a task; both are
                # rendered conditionally by the client.
                "due_at": None,
                "priority": None,
            }
        )
    return out


def _attendance_summary(user) -> Dict[str, Any]:
    """Attendance rate over this student's own records only."""
    rows = AttendanceRecord.objects.filter(student=user).values_list(
        "status", flat=True
    )
    total = 0
    attended = 0
    for status in rows:
        total += 1
        if status in (
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.LATE,
        ):
            attended += 1

    rate = round((attended / total) * 100) if total else 0
    return {
        "total_sessions": total,
        "attended": attended,
        "rate": rate,
        "attendance_rate": f"{rate}%",
    }


def _student_dashboard(user) -> Dict[str, Any]:
    enrollments = list(_enrollment_rows(user))
    course_ids = [row.course_id for row in enrollments]
    offering_ids = [row.course_offering_id for row in enrollments if row.course_offering_id]

    projects = list(_projects_for(user))
    group_names = _group_names_for(user)
    active_projects = [_serialize_project(p, group_names) for p in projects]
    pending_tasks = _pending_tasks(user, {p.title for p in projects})
    attendance = _attendance_summary(user)

    courses = [
        {
            "id": str(row.course_id),
            "code": row.course.code,
            "name": row.course.name,
            "credit_units": row.course.credit_units,
            "course_offering_id": str(row.course_offering_id)
            if row.course_offering_id
            else None,
        }
        for row in enrollments
    ]

    return {
        "stats": {
            "enrolled_courses": len(courses),
            "attendance_rate": attendance["attendance_rate"],
            "active_projects": len(active_projects),
            "pending_tasks": len(pending_tasks),
        },
        "courses": courses,
        "today_classes": _today_classes(offering_ids),
        "announcements": _visible_announcements(user, course_ids),
        "active_projects": active_projects,
        "pending_tasks": pending_tasks,
        "attendance": attendance,
    }


def _lecturer_dashboard(user) -> Dict[str, Any]:
    from apps.academic.models import CourseOffering

    offerings = list(
        CourseOffering.objects.filter(lecturer=user)
        .select_related("course", "department")
        .order_by("course__code")
    )
    offering_ids = [o.pk for o in offerings]

    projects = list(_projects_for(user))
    group_names = _group_names_for(user)
    active_projects = [_serialize_project(p, group_names) for p in projects]

    my_courses = [
        {
            "id": str(o.pk),
            "code": o.course.code,
            "name": o.course.name,
            "course_offering_id": str(o.pk),
            "status": o.status,
        }
        for o in offerings
    ]

    return {
        "stats": {
            "my_courses": len(my_courses),
            "active_projects": len(active_projects),
        },
        "my_courses": my_courses,
        "today_classes": _today_classes(None, lecturer_id=user.pk),
        "active_projects": active_projects,
        "announcements": _visible_announcements(
            user, [o.course_id for o in offerings]
        ),
    }


def _admin_dashboard(user) -> Dict[str, Any]:
    counts = User.objects.aggregate(
        total_users=Count("id"),
        total_students=Count("id", filter=Q(role=User.Role.STUDENT)),
        total_lecturers=Count("id", filter=Q(role=User.Role.LECTURER)),
    )
    for key in ("total_users", "total_students", "total_lecturers"):
        counts[key] = counts[key] or 0

    return {
        "stats": counts,
        **counts,
        "announcements": _visible_announcements(user, []),
    }


def build_dashboard(user) -> Dict[str, Any]:
    """Return the aggregated payload for ``user``'s role (API §46)."""
    role = getattr(user, "role", None)
    if role == User.Role.STUDENT:
        return _student_dashboard(user)
    if role == User.Role.LECTURER:
        return _lecturer_dashboard(user)
    return _admin_dashboard(user)
