"""Announcement API — visible feed plus authorized create/edit (BR-080 to BR-084).

Scope facts used for authorization are always derived server-side from the
authenticated user (enrollments, taught classes, faculty/department links);
the payload only says *which* scope it targets, never *who* the caller is.
"""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academic.models import ClassSession, Course, Department, Enrollment, Faculty
from core.academic_access import is_authorized_academic_user

from .models import Announcement, AnnouncementRead
from .serializers import (
    AnnouncementCreateSerializer,
    AnnouncementSerializer,
    AnnouncementUpdateSerializer,
)
from .services.announcement_service import (
    AnnouncementError,
    AnnouncementNotFoundError,
    InvalidAnnouncementScopeError,
    UnauthorizedAnnouncementActionError,
    announcement_audience,
    archive_announcement,
    can_manage_announcement,
    can_user_view_announcement,
    create_announcement,
    get_visible_announcements,
    mark_announcement_read,
    set_announcement_pin,
    update_announcement,
)


def _error(code, message, http_status):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


def _scope_context(user) -> dict:
    """Server-derived scope facts for the service's access checks."""
    enrolled = set(
        Enrollment.objects.filter(student=user, is_active=True).values_list(
            "course_id", flat=True
        )
    )
    taught = set(
        ClassSession.objects.filter(lecturer=user).values_list("course_id", flat=True)
    )
    course_ids = enrolled | taught
    class_ids = set(
        ClassSession.objects.filter(Q(lecturer=user) | Q(course_id__in=course_ids))
        .values_list("id", flat=True)
    )
    return {
        "user_faculty_id": user.faculty_id,
        "user_department_id": user.department_id,
        "user_course_ids": course_ids,
        "user_class_ids": class_ids,
        "user_roles": [user.role.lower()],
    }


_ANNOUNCEMENT_SELECT = (
    "faculty",
    "department",
    "course",
    "class_session__course",
    "created_by",
)


def _scope_exists(scope, scope_id):
    models = {
        "faculty": Faculty,
        "department": Department,
        "course": Course,
        "class": ClassSession,
    }
    model = models.get(scope)
    return bool(model and model.objects.filter(pk=scope_id).exists())


def _scoped_announcement(user, pk, *, published_only=False):
    announcement = Announcement.objects.filter(pk=pk, is_archived=False).select_related(
        *_ANNOUNCEMENT_SELECT
    ).first()
    if announcement is None:
        return None
    if published_only and not announcement.is_published:
        return None
    if can_manage_announcement(user, announcement):
        return announcement
    try:
        if can_user_view_announcement(
            announcement=announcement, user=user, **_scope_context(user)
        ):
            return announcement
    except AnnouncementError:
        pass
    return None


class AnnouncementListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Announcement.objects.filter(
            is_published=True, is_archived=False
        ).select_related(
            *_ANNOUNCEMENT_SELECT
        ).prefetch_related("reads__user")
        visible = get_visible_announcements(
            announcements=queryset,
            user=request.user,
            **_scope_context(request.user),
        )
        course_id = request.query_params.get("course_id")
        if course_id:
            visible = [item for item in visible if str(item.course_id) == course_id]
        return _success(
            AnnouncementSerializer(visible, many=True, context={"request": request}).data
        )

    def post(self, request):
        # BR-083: creation is for authorized academic users; the service then
        # narrows by scope (faculty/department/course/class) ownership.
        if not is_authorized_academic_user(request.user):
            return _error(
                "UNAUTHORIZED", "Only academic users may create announcements.", 403
            )
        serializer = AnnouncementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            announcement = create_announcement(
                AnnouncementModel=Announcement,
                title=validated["title"],
                body=validated["body"],
                scope=validated["scope"],
                scope_id=validated["scope_id"],
                actor=request.user,
                actor_id=request.user.id,
                is_important=validated.get("is_important", False),
                published=validated.get("published", False),
                scope_exists=_scope_exists,
                **_scope_context(request.user),
            )
        except InvalidAnnouncementScopeError as exc:
            return _error("INVALID_SCOPE", str(exc), 400)
        except UnauthorizedAnnouncementActionError as exc:
            # A target outside the caller's academic scope is indistinguishable
            # from a missing UUID; otherwise this write endpoint is an oracle.
            return _error("NOT_FOUND", "Announcement scope target not found.", 404)
        except AnnouncementError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(
            AnnouncementSerializer(announcement, context={"request": request}).data, 201
        )


class AnnouncementUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        # BR-083 applies to edits too — students can view, never edit.
        if not is_authorized_academic_user(request.user):
            return _error(
                "UNAUTHORIZED", "Only academic users may edit announcements.", 403
            )
        announcement = _scoped_announcement(request.user, pk)
        if announcement is None:
            return _error("NOT_FOUND", "Announcement not found.", 404)
        serializer = AnnouncementUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            # Published edits always pass through the audit path (BR-084).
            announcement = update_announcement(
                announcement=announcement,
                actor=request.user,
                actor_id=request.user.id,
                title=validated.get("title"),
                body=validated.get("body"),
                is_important=validated.get("is_important"),
                published=validated.get("published"),
                **_scope_context(request.user),
            )
        except AnnouncementNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except InvalidAnnouncementScopeError as exc:
            return _error("INVALID_SCOPE", str(exc), 400)
        except UnauthorizedAnnouncementActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except AnnouncementError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(
            AnnouncementSerializer(announcement, context={"request": request}).data
        )

    def delete(self, request, pk):
        announcement = _scoped_announcement(request.user, pk)
        if announcement is None:
            return _error("NOT_FOUND", "Announcement not found.", 404)
        if not can_manage_announcement(request.user, announcement):
            return _error("FORBIDDEN", "Only the author or an administrator may edit this announcement.", 403)
        try:
            archive_announcement(announcement=announcement, actor=request.user)
        except UnauthorizedAnnouncementActionError as exc:
            return _error("FORBIDDEN", str(exc), 403)
        return _success({"id": str(announcement.id), "archived": True})


class AnnouncementPinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if set(request.data) - {"pinned"}:
            return _error("INVALID_INPUT", "Only pinned may be submitted.", 400)
        announcement = _scoped_announcement(request.user, pk)
        if announcement is None:
            return _error("NOT_FOUND", "Announcement not found.", 404)
        try:
            set_announcement_pin(
                announcement=announcement,
                actor=request.user,
                pinned=bool(request.data.get("pinned", True)),
            )
        except UnauthorizedAnnouncementActionError as exc:
            return _error("FORBIDDEN", str(exc), 403)
        except AnnouncementError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(
            AnnouncementSerializer(announcement, context={"request": request}).data
        )


class AnnouncementReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        announcement = _scoped_announcement(request.user, pk, published_only=True)
        if announcement is None:
            return _error("NOT_FOUND", "Announcement not found.", 404)
        mark_announcement_read(
            announcement=announcement, user=request.user, ReadModel=AnnouncementRead
        )
        return _success(
            AnnouncementSerializer(announcement, context={"request": request}).data
        )


class AnnouncementReadersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        announcement = _scoped_announcement(request.user, pk)
        if announcement is None:
            return _error("NOT_FOUND", "Announcement not found.", 404)
        if not can_manage_announcement(request.user, announcement):
            return _error("FORBIDDEN", "Only the author or an administrator can view receipts.", 403)
        read_ids = set(announcement.reads.values_list("user_id", flat=True))
        audience = announcement_audience(announcement)
        unread = audience.exclude(id__in=read_ids)[:100]
        readers = announcement.reads.select_related("user")[:100]
        return _success({
            "announcement": str(announcement.id),
            "read_count": len(read_ids),
            "recipient_count": audience.count(),
            "readers": [
                {
                    "id": str(row.user_id),
                    "full_name": f"{row.user.first_name} {row.user.last_name}".strip(),
                    "read_at": row.read_at,
                }
                for row in readers
            ],
            "unread": [
                {
                    "id": str(user.id),
                    "full_name": f"{user.first_name} {user.last_name}".strip(),
                    "matricule": user.matricule or "",
                }
                for user in unread
            ],
        })


class AnnouncementReadStateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Announcement.objects.filter(
            is_published=True, is_archived=False
        ).select_related(*_ANNOUNCEMENT_SELECT)
        visible = get_visible_announcements(
            announcements=queryset, user=request.user, **_scope_context(request.user)
        )
        visible_ids = [item.id for item in visible]
        read_ids = set(AnnouncementRead.objects.filter(
            user=request.user, announcement_id__in=visible_ids
        ).values_list("announcement_id", flat=True))
        return _success({"unread": len(set(visible_ids) - read_ids)})
