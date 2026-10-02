"""Shared academic access helpers.

This module centralizes the repeated lookup and scope rules used by multiple
services so the codebase does not duplicate access checks in several places.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Set

from .common import as_set

ROLE_STUDENT = "student"
ROLE_ADMIN = "admin"
ROLE_ADMINISTRATOR = "administrator"
ROLE_LECTURER = "lecturer"
ROLE_ACADEMIC_STAFF = "academic_staff"
ROLE_STAFF = "staff"
ADMIN_ROLES = frozenset({ROLE_ADMIN, ROLE_ADMINISTRATOR})
ACADEMIC_ROLES = frozenset(
    {ROLE_ADMIN, ROLE_ADMINISTRATOR, ROLE_LECTURER, ROLE_ACADEMIC_STAFF, ROLE_STAFF}
)

SCOPE_FACULTY = "faculty"
SCOPE_DEPARTMENT = "department"
SCOPE_COURSE = "course"
SCOPE_CLASS = "class"
SCOPE_COURSE_CLASS = "course_class"
SCOPE_PROJECT = "project"
ACADEMIC_CONTEXTS = frozenset(
    {SCOPE_COURSE, SCOPE_CLASS, SCOPE_PROJECT, SCOPE_DEPARTMENT, SCOPE_FACULTY}
)
ANNOUNCEMENT_SCOPES = frozenset(
    {SCOPE_FACULTY, SCOPE_DEPARTMENT, SCOPE_COURSE, SCOPE_CLASS, SCOPE_COURSE_CLASS}
)


class InvalidScopeError(ValueError):
    """Raised when an academic scope is missing or unsupported."""

VALID_ANNOUNCEMENT_SCOPES = ANNOUNCEMENT_SCOPES
VALID_ACADEMIC_CONTEXTS = ACADEMIC_CONTEXTS
VALID_ACADEMIC_ROLES = ACADEMIC_ROLES


def normalize_role(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def is_authorized_academic_user(user: Any) -> bool:
    """Return whether the subject is an authorized academic user."""
    if user is None:
        return False
    role = normalize_role(getattr(user, "role", None))
    if role in ACADEMIC_ROLES:
        return True
    if getattr(user, "is_staff", False):
        return True
    if getattr(user, "is_lecturer", False):
        return True
    return False


def is_admin_user(user: Any) -> bool:
    """Return whether a user has a server-side administrator role."""
    if user is None:
        return False
    return normalize_role(getattr(user, "role", None)) in ADMIN_ROLES or bool(
        getattr(user, "is_staff", False)
    )


def normalize_scope(scope: Optional[str], *, allowed_scopes: Optional[set[str]] = None) -> str:
    """Normalize and validate a scope string.

    Returns a canonical identifier like "course" or "course_class".
    """
    valid_scopes = allowed_scopes or ANNOUNCEMENT_SCOPES
    if scope is None:
        raise InvalidScopeError("Scope is required")
    value = str(scope).strip().lower().replace("/", "_").replace("-", "_")
    if value in {SCOPE_COURSE_CLASS, "class_course"}:
        return SCOPE_COURSE_CLASS
    if value not in valid_scopes:
        raise InvalidScopeError(f"Unsupported scope: {scope}")
    return value


def collect_user_course_ids(
    user: Any,
    extras: Optional[Iterable[Any]] = None,
) -> Set[Any]:
    """Collect server-known course assignments plus trusted extra IDs."""
    values = set()
    if user is None:
        return values
    values |= as_set(getattr(user, "course_ids", None))
    values |= as_set(getattr(user, "eligible_course_ids", None))
    values |= as_set(getattr(user, "enrolled_course_ids", None))
    if extras is not None:
        values |= as_set(extras)
    return values


def collect_user_class_ids(
    user: Any,
    extras: Optional[Iterable[Any]] = None,
) -> Set[Any]:
    """Collect server-known class assignments plus trusted extra IDs."""
    values = set()
    if user is None:
        return values
    values |= as_set(getattr(user, "class_ids", None))
    values |= as_set(getattr(user, "eligible_class_ids", None))
    values |= as_set(getattr(user, "enrolled_class_ids", None))
    if extras is not None:
        values |= as_set(extras)
    return values


def user_has_scope_access(
    *,
    user: Any,
    scope: str,
    scope_id: Any,
    user_faculty_id: Optional[Any] = None,
    user_department_id: Optional[Any] = None,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> bool:
    """Return whether a user can access a scope such as faculty, department, course, or class."""
    if user is None:
        return False
    if scope_id is None:
        return False

    roles = {str(role).strip().lower() for role in (user_roles or [])}
    roles.add(normalize_role(getattr(user, "role", None)))
    if getattr(user, "is_staff", False):
        roles.add("staff")
    if "admin" in roles or "administrator" in roles:
        return True

    normalized = normalize_scope(scope, allowed_scopes=VALID_ANNOUNCEMENT_SCOPES)

    if normalized == SCOPE_FACULTY:
        faculty_id = getattr(user, "faculty_id", None) or user_faculty_id
        return faculty_id == scope_id

    if normalized == SCOPE_DEPARTMENT:
        department_id = getattr(user, "department_id", None) or user_department_id
        return department_id == scope_id

    if normalized in {SCOPE_COURSE, SCOPE_COURSE_CLASS}:
        # Server-derived memberships (e.g. the announcement view's enrollment
        # lookup) arrive as user_course_ids and must be honoured; user
        # attributes alone are only a fallback.
        if scope_id in collect_user_course_ids(user, user_course_ids):
            return True

    if normalized in {SCOPE_CLASS, SCOPE_COURSE_CLASS}:
        if scope_id in collect_user_class_ids(user, user_class_ids):
            return True

    return False
