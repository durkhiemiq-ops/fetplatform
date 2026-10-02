"""Announcement service for scoped academic announcements.

This service keeps announcements limited to the correct academic scope and
records important edits in a clear audit trail. It intentionally avoids Django
request/response objects and raises domain exceptions for API mapping.

Relevant rules:
- BR-080: faculty announcements are scoped to a faculty
- BR-081: department announcements are scoped to a department
- BR-082: course/class announcements are visible only to eligible users
- BR-083: only authorized users may create or publish announcements
- BR-084: important announcement edits must be auditable
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence, Protocol

from core.academic_access import (
    SCOPE_CLASS,
    SCOPE_COURSE,
    SCOPE_COURSE_CLASS,
    SCOPE_DEPARTMENT,
    SCOPE_FACULTY,
    InvalidScopeError,
    normalize_scope,
    user_has_scope_access,
)
from core.audit import write_audit_entry
from core.common import ConfigurationError, utc_now
from apps.notifications.services.notification_service import notify_announcement_published


class AnnouncementError(ValueError):
    """Base business error for announcement operations."""


class InvalidAnnouncementScopeError(AnnouncementError):
    """Raised when the announcement scope is missing or unsupported."""


class UnauthorizedAnnouncementActionError(AnnouncementError):
    """Raised when a user is not allowed to create, publish, or edit."""


class AnnouncementNotFoundError(AnnouncementError):
    """Raised when a requested announcement is missing."""


class AnnouncementModelLike(Protocol):
    id: Any
    title: Any
    body: Any
    scope: Any
    faculty_id: Any
    department_id: Any
    course_id: Any
    class_id: Any
    is_published: Any
    is_important: Any
    created_by_id: Any
    published_by_id: Any
    updated_by_id: Any
    published_at: Any
    updated_at: Any

    def save(self) -> Any:
        ...


def create_announcement(
    *,
    AnnouncementModel: type[AnnouncementModelLike],
    title: str,
    body: str,
    scope: str,
    scope_id: Any,
    actor: Any,
    actor_id: Optional[Any] = None,
    is_important: bool = False,
    published: bool = False,
    user_faculty_id: Optional[Any] = None,
    user_department_id: Optional[Any] = None,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> AnnouncementModelLike:
    """Create a scoped announcement with authorization checks.

    Time complexity: O(1) for valid scope checks and membership set lookups.
    Space complexity: O(1) extra for a few small sets.
    """
    # BR-080 to BR-083: announcements are scoped, and only authorized actors can
    # create them in the matching academic context.
    if AnnouncementModel is None:
        raise ConfigurationError("AnnouncementModel is required")
    if not title or not str(title).strip():
        raise AnnouncementError("Announcement title is required")
    if not body or not str(body).strip():
        raise AnnouncementError("Announcement body is required")

    try:
        normalized_scope = normalize_scope(scope)
    except InvalidScopeError as exc:
        raise InvalidAnnouncementScopeError(str(exc)) from exc
    if not user_has_scope_access(
        user=actor,
        scope=normalized_scope,
        scope_id=scope_id,
        user_faculty_id=user_faculty_id,
        user_department_id=user_department_id,
        user_course_ids=user_course_ids,
        user_class_ids=user_class_ids,
        user_roles=user_roles,
    ):
        raise UnauthorizedAnnouncementActionError(
            f"User is not authorized to create {normalized_scope} announcements for scope {scope_id}"
        )
    if scope_id is None:
        raise InvalidAnnouncementScopeError("Announcement scope id is required")

    announcement = AnnouncementModel()
    announcement.title = title
    announcement.body = body
    announcement.scope = normalized_scope
    announcement.faculty_id = scope_id if normalized_scope == SCOPE_FACULTY else None
    announcement.department_id = scope_id if normalized_scope == SCOPE_DEPARTMENT else None
    announcement.course_id = scope_id if normalized_scope in {SCOPE_COURSE, SCOPE_COURSE_CLASS} else None
    announcement.class_id = scope_id if normalized_scope in {SCOPE_CLASS, SCOPE_COURSE_CLASS} else None
    announcement.is_important = bool(is_important)
    announcement.is_published = bool(published)
    announcement.created_by_id = actor_id if actor_id is not None else getattr(actor, "id", None)
    if published:
        announcement.published_by_id = announcement.created_by_id
        announcement.published_at = utc_now()
    announcement.save()
    # BR §23 + API §45: publishing fans out one notification per eligible user
    # (active course enrollment for course/class scopes; faculty/department
    # links for those scopes in notification_service._announcement_audience).
    if published:
        notify_announcement_published(announcement)
    return announcement


def can_user_view_announcement(
    *,
    announcement: Any,
    user: Any,
    user_faculty_id: Optional[Any] = None,
    user_department_id: Optional[Any] = None,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> bool:
    """Return whether a user can view a published announcement.

    Time complexity: O(1) with set membership checks; O(n) only when a user has
    large lists and they are converted to a set.
    Space complexity: O(k) for the temporary set of course/class IDs.
    """
    if announcement is None or user is None:
        return False
    if getattr(announcement, "is_published", False) is False:
        return False

    try:
        scope = normalize_scope(getattr(announcement, "scope", None))
    except InvalidScopeError as exc:
        raise InvalidAnnouncementScopeError(str(exc)) from exc
    scope_id = getattr(announcement, "scope_id", None)
    if scope_id is None:
        scope_id = getattr(announcement, "faculty_id", None)
        if scope_id is None:
            scope_id = getattr(announcement, "department_id", None)
        if scope_id is None:
            scope_id = getattr(announcement, "course_id", None)
        if scope_id is None:
            scope_id = getattr(announcement, "class_id", None)

    if scope == SCOPE_FACULTY:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_FACULTY,
            scope_id=getattr(announcement, "faculty_id", scope_id),
            user_faculty_id=user_faculty_id,
            user_department_id=user_department_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_roles=user_roles,
        )

    if scope == SCOPE_DEPARTMENT:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_DEPARTMENT,
            scope_id=getattr(announcement, "department_id", scope_id),
            user_faculty_id=user_faculty_id,
            user_department_id=user_department_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_roles=user_roles,
        )

    if scope in {SCOPE_COURSE, SCOPE_COURSE_CLASS}:
        course_scope = getattr(announcement, "course_id", scope_id)
        if user_has_scope_access(
            user=user,
            scope=SCOPE_COURSE,
            scope_id=course_scope,
            user_faculty_id=user_faculty_id,
            user_department_id=user_department_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_roles=user_roles,
        ):
            return True

    if scope in {SCOPE_CLASS, SCOPE_COURSE_CLASS}:
        class_scope = getattr(announcement, "class_id", scope_id)
        return user_has_scope_access(
            user=user,
            scope=SCOPE_CLASS,
            scope_id=class_scope,
            user_faculty_id=user_faculty_id,
            user_department_id=user_department_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_roles=user_roles,
        )

    return False


def get_visible_announcements(
    *,
    announcements: Iterable[Any],
    user: Any,
    user_faculty_id: Optional[Any] = None,
    user_department_id: Optional[Any] = None,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> List[Any]:
    """Filter a collection to only the announcements visible to the user.

    Time complexity: O(n) over the announcement list, with O(1) visibility checks
    for each item. Space complexity: O(k) for the filtered result list.
    """
    result: List[Any] = []
    for announcement in announcements or []:
        if can_user_view_announcement(
            announcement=announcement,
            user=user,
            user_faculty_id=user_faculty_id,
            user_department_id=user_department_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_roles=user_roles,
        ):
            result.append(announcement)
    return result


def update_announcement(
    *,
    announcement: Any,
    actor: Any,
    actor_id: Optional[Any] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    is_important: Optional[bool] = None,
    published: Optional[bool] = None,
    audit_logger: Optional[Any] = None,
    user_faculty_id: Optional[Any] = None,
    user_department_id: Optional[Any] = None,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> AnnouncementModelLike:
    """Update an announcement without silently dropping the edit history.

    Published announcement edits are always sent through the audit path;
    unpublished drafts may be updated without an audit event.
    """
    # BR-083 and BR-084: authorization and auditability are enforced on update.
    if announcement is None:
        raise AnnouncementNotFoundError("Announcement not found")
    was_published = bool(getattr(announcement, "is_published", False))

    try:
        normalized_scope = normalize_scope(getattr(announcement, "scope", None))
    except InvalidScopeError as exc:
        raise InvalidAnnouncementScopeError(str(exc)) from exc
    scope_id = getattr(announcement, "scope_id", None)
    if scope_id is None:
        scope_id = getattr(announcement, "faculty_id", None) or getattr(announcement, "department_id", None) or getattr(announcement, "course_id", None) or getattr(announcement, "class_id", None)

    if not user_has_scope_access(
        user=actor,
        scope=normalized_scope,
        scope_id=scope_id,
        user_faculty_id=user_faculty_id,
        user_department_id=user_department_id,
        user_course_ids=user_course_ids,
        user_class_ids=user_class_ids,
        user_roles=user_roles,
    ):
        raise UnauthorizedAnnouncementActionError("User is not authorized to edit this announcement")

    if title is not None:
        if not str(title).strip():
            raise AnnouncementError("Announcement title cannot be empty")
        announcement.title = title

    if body is not None:
        if not str(body).strip():
            raise AnnouncementError("Announcement body cannot be empty")
        announcement.body = body

    if is_important is not None:
        announcement.is_important = bool(is_important)

    if published is not None:
        announcement.is_published = bool(published)
        if published and not getattr(announcement, "published_at", None):
            announcement.published_at = utc_now()
        if published and hasattr(announcement, "published_by_id"):
            announcement.published_by_id = actor_id if actor_id is not None else getattr(actor, "id", None)

    if hasattr(announcement, "updated_by_id"):
        announcement.updated_by_id = actor_id if actor_id is not None else getattr(actor, "id", None)
    if hasattr(announcement, "updated_at"):
        announcement.updated_at = utc_now()

    if getattr(announcement, "is_published", False):
        # BR-084: every edit to a published announcement is auditable, not only
        # edits marked important.
        audit_details = {
            "scope": normalized_scope,
            "scope_id": scope_id,
            "title": announcement.title,
        }
        if audit_logger is not None:
            audit_logger(
                action="announcement_updated",
                resource_type="announcement",
                resource_id=getattr(announcement, "id", None),
                actor_id=actor_id if actor_id is not None else getattr(actor, "id", None),
                details=audit_details,
            )
        else:
            write_audit_entry(
                action="announcement_updated",
                resource_type="announcement",
                resource_id=getattr(announcement, "id", None),
                actor_id=actor_id if actor_id is not None else getattr(actor, "id", None),
                details=audit_details,
            )

    announcement.save()
    # Draft -> published transition fans out notifications exactly once; editing
    # an already-published announcement does not notify again.
    if not was_published and bool(getattr(announcement, "is_published", False)):
        notify_announcement_published(announcement)
    return announcement
