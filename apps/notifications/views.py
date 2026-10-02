"""Notification API — own inbox list, per-item read, read-all (API §45).

Every endpoint is owner-scoped by the authenticated user: the payload never
carries a recipient, and a notification belonging to someone else is answered
with the exact same 404 as one that does not exist (User Roles §25).
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import NotificationSerializer
from .services.notification_service import (
    NotificationNotFoundError,
    list_notifications,
    mark_all_read,
    mark_read,
)


def _error(code, message, http_status):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


class NotificationListView(APIView):
    """GET /notifications/ — the requesting user's own inbox, newest first.

    Optional ``?unread=true`` filters to unread rows.  There is no parameter
    that can name another user.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        unread_only = request.query_params.get("unread", "").lower() == "true"
        notifications = list_notifications(
            recipient=request.user, unread_only=unread_only
        )
        return _success(
            NotificationSerializer(notifications, many=True).data
        )


class NotificationReadView(APIView):
    """PATCH /notifications/{id}/read/ — mark one owned notification read.

    404 NOT_FOUND (identical shape to a missing id) when the notification does
    not belong to the requester or does not exist (§25).
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notifications"

    def patch(self, request, pk):
        try:
            notification = mark_read(
                notification_id=pk, recipient=request.user
            )
        except NotificationNotFoundError:
            return _error("NOT_FOUND", "Notification not found", 404)
        return _success(NotificationSerializer(notification).data)


class NotificationReadAllView(APIView):
    """POST /notifications/read-all/ — mark every unread owned notification read."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notifications"

    def post(self, request):
        updated_count = mark_all_read(recipient=request.user)
        return _success({"updated_count": updated_count})