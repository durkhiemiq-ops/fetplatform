"""Notification inbox — eligibility-filtered, owner-scoped (BR §23, API §45).

Notifications are personal records: every row names exactly one recipient, and
no query path ever accepts a client-chosen recipient.  Eligibility (who is
allowed to *receive* a notification) is decided by the trigger that creates
each notification, never by the API layer.

Relevant rules:
- Business Rules §23: notifications only reach users eligible for the related
  information (e.g. a course announcement reaches enrolled students only).
- API spec §45: GET /notifications, PATCH /notifications/{id}/read and
  POST /notifications/read-all; read/unread state.
- User Roles §25: a notification that is not yours is indistinguishable from
  one that does not exist (see notification_service + the API views).
"""

import uuid

from django.db import models


class Notification(models.Model):
    """One entry in exactly one user's inbox."""

    class Category(models.TextChoices):
        ANNOUNCEMENT = "announcement", "Announcement"
        ATTENDANCE_FLAG = "attendance_flag", "Attendance flag"
        ATTENDANCE_CORRECTION = "attendance_correction", "Attendance correction"
        ROLE_CHANGE = "role_change", "Role change"
        ENROLLMENT = "enrollment", "Enrollment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="The only account this notification may be read by.",
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=120)
    body = models.TextField()
    related_type = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Optional object kind for deep-linking (e.g. announcement).",
    )
    related_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional object id for deep-linking.",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "-created_at"],
                name="ntf_rcpt_read_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.recipient_id}:{self.category}:{self.title}"