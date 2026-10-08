"""Reusable DRF permission classes built on the central access policy.

Why this module exists
----------------------
Lecturer approval (``User.lecturer_approval_status``) is a *server-owned*
authorization fact, but until now every endpoint had to remember to consult it.
A new view written as::

    permission_classes = [IsAuthenticated]
    ...
    if request.user.role == User.Role.LECTURER: ...

looks correct and silently grants a PENDING or REJECTED lecturer the
lecturer-only behaviour. That is the failure mode this module closes.

``is_authorized_academic_user`` in :mod:`core.academic_access` remains the one
place the policy is *decided*. The classes here only *apply* it, so there is
exactly one implementation of the rules to audit and one place to change them.

Usage::

    class LecturerOnlyView(APIView):
        permission_classes = [IsApprovedAcademicUser]

The predicate is already used at ~25 call sites in services and views; this is
the opt-in-free equivalent for new code, not a replacement for working logic.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from .academic_access import is_admin_user, is_authorized_academic_user

#: Deliberately generic. Telling a rejected applicant "you were rejected" from
#: an authorization error leaks their application outcome to whoever holds the
#: session, and tells a legitimate lecturer nothing useful. §25 also asks for
#: denial shapes that do not vary with the reason.
DENIED_MESSAGE = "You do not have permission to perform this action."


class IsApprovedAcademicUser(BasePermission):
    """Requires an authenticated academic user who may act as teaching staff.

    Grants: ADMINISTRATOR (and the legacy ``admin`` label), LECTURER with
    ``lecturer_approval_status`` APPROVED, and LECTURER with a NULL status
    (pre-existing rows, preserved for backward compatibility).

    Denies: anonymous, STUDENT, and LECTURER with PENDING or REJECTED.

    This is the structural form of the lecturer approval policy. Prefer it over
    ``IsAuthenticated`` on any lecturer-only or teaching-staff endpoint so the
    approval gate cannot be forgotten.
    """

    message = DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return is_authorized_academic_user(user)


class IsAdministrator(BasePermission):
    """Requires an authenticated user holding a server-side administrator role.

    Mirrors the ``is_admin_user(request.user)`` guards already written inline in
    the approval views, so those endpoints can declare the rule instead of
    re-implementing it. Administrators are unaffected by lecturer approval,
    which is why this is separate from :class:`IsApprovedAcademicUser`.
    """

    message = DENIED_MESSAGE

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return is_admin_user(user)
