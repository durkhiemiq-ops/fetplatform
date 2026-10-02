"""Announcement API — visible feed plus authorized create/edit (BR-080 to BR-084).

Scope facts used for authorization are always derived server-side from the
authenticated user (enrollments, taught classes, faculty/department links);
the payload only says *which* scope it targets, never *who* the caller is.
"""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academic.models import ClassSession, Enrollment
from core.academic_access import is_authorized_academic_user

from .models import Announcement
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
    create_announcement,
    get_visible_announcements,
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


class AnnouncementListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Announcement.objects.filter(is_published=True).select_related(
            *_ANNOUNCEMENT_SELECT
        )
        visible = get_visible_announcements(
            announcements=queryset,
            user=request.user,
            **_scope_context(request.user),
        )
        return _success(AnnouncementSerializer(visible, many=True).data)

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
                **_scope_context(request.user),
            )
        except InvalidAnnouncementScopeError as exc:
            return _error("INVALID_SCOPE", str(exc), 400)
        except UnauthorizedAnnouncementActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except AnnouncementError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        return _success(AnnouncementSerializer(announcement).data, 201)


class AnnouncementUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        # BR-083 applies to edits too — students can view, never edit.
        if not is_authorized_academic_user(request.user):
            return _error(
                "UNAUTHORIZED", "Only academic users may edit announcements.", 403
            )
        announcement = Announcement.objects.filter(pk=pk).select_related(
            *_ANNOUNCEMENT_SELECT
        ).first()
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
        return _success(AnnouncementSerializer(announcement).data)
