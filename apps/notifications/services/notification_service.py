"""Notification service — creation, eligibility, and read-state rules.

Every notification is created with an explicit recipient chosen by the
triggering domain event (announcement published, BR-064 flag raised, role
changed, enrollment added, attendance corrected).  The service never accepts a
recipient from an untrusted request, and every read path is forced to the
authenticated user — a notification that is not yours is indistinguishable from
one that does not exist (User Roles §25).

Eligibility (Business Rules §23):
- Announcement published -> the exact audience that may *see* the announcement
  (active course enrollment for course/class scopes; faculty/department links
  for those scopes), mirroring `user_has_scope_access` so we never notify an
  unrelated user.
- Any account-level event (flag, correction, role change, enrollment) -> the
  account the event is about.  An account's own inbox is its own inbox.

This module deliberately imports the ORM models it needs for recipient
computation; it does not build HTTP responses.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Optional

from django.utils import timezone

from apps.academic.models import Course, Enrollment
from apps.accounts.models import User
from core.academic_access import SCOPE_COURSE, SCOPE_COURSE_CLASS, SCOPE_DEPARTMENT, SCOPE_FACULTY

from ..models import Notification

logger = logging.getLogger("apps.notifications")

# Trigger-friendly helpers
CATEGORY_ANNOUNCEMENT = Notification.Category.ANNOUNCEMENT
CATEGORY_ATTENDANCE_FLAG = Notification.Category.ATTENDANCE_FLAG
CATEGORY_ATTENDANCE_CORRECTION = Notification.Category.ATTENDANCE_CORRECTION
CATEGORY_ROLE_CHANGE = Notification.Category.ROLE_CHANGE
CATEGORY_ENROLLMENT = Notification.Category.ENROLLMENT


class NotificationError(ValueError):
    """Base domain error for notification operations."""


class NotificationNotFoundError(NotificationError):
    """Raised when a notification is absent or belongs to another user."""


class InvalidNotificationError(NotificationError):
    """Raised when a notification payload is malformed."""


VALID_CATEGORIES = frozenset(
    {
        CATEGORY_ANNOUNCEMENT,
        CATEGORY_ATTENDANCE_FLAG,
        CATEGORY_ATTENDANCE_CORRECTION,
        CATEGORY_ROLE_CHANGE,
        CATEGORY_ENROLLMENT,
    }
)


def best_effort_delivery(fn):
    """Decorator for the trigger helpers.

    Notifications are a delivery side-channel, not a transaction participant:
    a scan that just flagged a student, or a correction that already appended,
    must NEVER 500 because the inbox write failed.  Failures are logged at
    WARNING (so the trigger tests and operators still see them) and the helper
    returns 0.  This mirrors the production recommendation in the source docs
    (Celery/Redis background delivery) rather than an inline blocking write.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - delivery is best-effort by design
            logger.warning(
                "Notification delivery failed for %s", fn.__name__, exc_info=True
            )
            return 0

    return wrapper


def create_notification(
    *,
    recipient: Any,
    category: str,
    title: str,
    body: str,
    related_type: str = "",
    related_id: Any = None,
) -> Notification:
    """Create one notification for one recipient (BR §23: explicit eligibility).

    This is the single creation path for the whole platform; triggers call it
    (or the higher-level helpers below) so every inbox row names the exact
    account it belongs to.
    """
    if recipient is None:
        raise InvalidNotificationError("A recipient is required")
    if str(category) not in VALID_CATEGORIES:
        raise InvalidNotificationError(f"Unsupported notification category: {category}")
    if not title or not str(title).strip():
        raise InvalidNotificationError("Notification title is required")
    if not body or not str(body).strip():
        raise InvalidNotificationError("Notification body is required")

    return Notification.objects.create(
        recipient=recipient,
        category=category,
        title=title.strip(),
        body=body.strip(),
        related_type=str(related_type or ""),
        related_id=str(related_id) if related_id is not None else "",
    )


def list_notifications(
    *,
    recipient: Any,
    unread_only: bool = False,
    limit: int = 200,
) -> list[Notification]:
    """Return the requesting user's own inbox, newest first.

    The recipient is always the authenticated user: there is no code path that
    lists another user's notifications.
    """
    if recipient is None:
        return []
    queryset = Notification.objects.filter(recipient=recipient)
    if unread_only:
        queryset = queryset.filter(is_read=False)
    return list(queryset.order_by("-created_at", "-id")[: max(1, int(limit))])


def get_owned_notification(*, notification_id: Any, recipient: Any) -> Optional[Notification]:
    """Fetch a notification only when it belongs to `recipient`.

    Returns None for a missing id AND for another user's id — the §25 rule:
    both must look identical to the caller.
    """
    if recipient is None or notification_id is None:
        return None
    return (
        Notification.objects.filter(recipient=recipient, id=notification_id).first()
    )


def mark_read(*, notification_id: Any, recipient: Any) -> Notification:
    """Mark one owned notification as read (idempotent)."""
    notification = get_owned_notification(notification_id=notification_id, recipient=recipient)
    if notification is None:
        raise NotificationNotFoundError("Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])
    return notification


def mark_all_read(*, recipient: Any) -> int:
    """Mark every unread notification owned by the user as read.

    Returns the number of notifications whose state actually changed.
    """
    if recipient is None:
        return 0
    return Notification.objects.filter(
        recipient=recipient, is_read=False
    ).update(is_read=True, read_at=timezone.now())


# ============================================================================
# Trigger helpers — wired into the domain services that own each real event.
# Each helper decides the recipient set from the event itself, so §23
# eligibility cannot be bypassed by the caller.
# ============================================================================

def _announcement_audience(announcement: Any) -> list[User]:
    """Eligible recipients for a published announcement (BR §23, BR-082).

    Mirrors `user_has_scope_access` so we notify exactly the users who may see
    the announcement: course/class scopes reach students with an active
    enrollment in the course; department/faculty scopes reach accounts linked
    to that department/faculty.
    """
    if announcement is None or not getattr(announcement, "is_published", False):
        return []
    scope = str(getattr(announcement, "scope", "") or "").strip().lower()

    if scope in {SCOPE_COURSE, SCOPE_COURSE_CLASS}:
        course_id = getattr(announcement, "course_id", None)
        if course_id is None:
            return []
        return list(
            User.objects.filter(
                enrollments__course_id=course_id,
                enrollments__is_active=True,
            ).distinct()
        )

    if scope == SCOPE_DEPARTMENT:
        department_id = getattr(announcement, "department_id", None)
        if department_id is None:
            return []
        return list(User.objects.filter(department_id=department_id))

    if scope == SCOPE_FACULTY:
        faculty_id = getattr(announcement, "faculty_id", None)
        if faculty_id is None:
            return []
        return list(User.objects.filter(faculty_id=faculty_id))

    return []


@best_effort_delivery
def notify_announcement_published(announcement: Any) -> int:
    """Fan out one notification per eligible user when an announcement is published.

    Returns the number of notifications created (0 when the announcement is a
    draft or has no eligible audience).  Called from the announcement service's
    publish transitions only.
    """
    recipients = _announcement_audience(announcement)
    if not recipients:
        return 0
    created = 0
    rows = []
    for user in recipients:
        rows.append(
            Notification(
                recipient=user,
                category=CATEGORY_ANNOUNCEMENT,
                title="New announcement posted",
                body=str(getattr(announcement, "title", "") or "").strip(),
                related_type="announcement",
                related_id=str(getattr(announcement, "id", "") or ""),
            )
        )
    if rows:
        created = len(Notification.objects.bulk_create(rows))
    return created


@best_effort_delivery
def notify_suspicious_activity_flagged(*, actor_id: Any, reason: str, metadata: Optional[dict] = None) -> int:
    """Notify the account whose behaviour was flagged for review (BR-064).

    Recipient is the flagged account itself — an account's own security events
    are always §23-eligible.  A missing account is skipped silently (the audit
    entry is still written by the caller).
    """
    if actor_id is None:
        return 0
    user = User.objects.filter(id=actor_id).first()
    if user is None:
        return 0
    failure_code = (metadata or {}).get("failure_code") or reason
    return int(
        create_notification(
            recipient=user,
            category=CATEGORY_ATTENDANCE_FLAG,
            title="Attendance flagged for review",
            body=(
                f"Suspicious activity was flagged on your account for review: "
                f"{failure_code}. Your attendance standing is not changed by the flag."
            ),
            related_type="attendance_security_event",
            related_id=f"{actor_id}:{timezone.now().isoformat()}",
        )
        is not None
    )


@best_effort_delivery
def notify_attendance_corrected(*, record: Any, correction: Any) -> int:
    """Notify the student whose attendance record was corrected (BR-042)."""
    record_obj = getattr(record, "attendance_record", record)
    student = getattr(record_obj, "student", None)
    if student is None:
        return 0
    return int(
        create_notification(
            recipient=student,
            category=CATEGORY_ATTENDANCE_CORRECTION,
            title="Attendance record corrected",
            body=(
                "Your attendance record was corrected by a reviewer. "
                "The correction is audited and append-only."
            ),
            related_type="attendance_record",
            related_id=str(getattr(record_obj, "id", "") or ""),
        )
        is not None
    )


@best_effort_delivery
def notify_role_changed(*, account: Any, old_role: Any, new_role: Any) -> int:
    """Notify the account whose role an administrator changed (BR-002/BR-210)."""
    if account is None or getattr(account, "id", None) is None:
        return 0
    return int(
        create_notification(
            recipient=account,
            category=CATEGORY_ROLE_CHANGE,
            title="Account role updated",
            body=(
                f"Your account role was changed from {old_role or 'unknown'} "
                f"to {new_role} by an administrator."
            ),
            related_type="account",
            related_id=str(account.id),
        )
        is not None
    )


@best_effort_delivery
def notify_student_enrolled(*, student_id: Any, course_id: Any) -> int:
    """Notify a student when they are enrolled in a course (BR-010)."""
    if student_id is None or course_id is None:
        return 0
    user = User.objects.filter(id=student_id).first()
    if user is None:
        return 0
    course = Course.objects.filter(id=course_id).first()
    if course is not None:
        body = f"You were enrolled in {course.code}: {course.name}."
    else:
        body = "You were enrolled in a new course."
    return int(
        create_notification(
            recipient=user,
            category=CATEGORY_ENROLLMENT,
            title="Course enrollment",
            body=body,
            related_type="course",
            related_id=str(course_id),
        )
        is not None
    )