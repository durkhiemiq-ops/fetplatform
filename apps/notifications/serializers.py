"""API serializers for the notification inbox (API §45, §67 trimmed)."""

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Read-only shape: exactly what a notification UI needs, nothing more.

    The recipient is implied by the authenticated session and is never
    serialized; internal names and ID internals are excluded (§67).
    """

    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "title",
            "body",
            "related_type",
            "related_id",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields