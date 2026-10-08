"""Server-side account and role business rules.

This module intentionally accepts plain values and Django-like model classes.
It does not read frontend role claims and it does not construct HTTP responses.

Business rules enforced here:
- BR-001: active academic identities have at most one active account.
- BR-002: registrations default to STUDENT; role changes require an authorized
  administrator and are audited.
- BR-003: permissions derive from the server-side stored role only.
- BR-170: account operations reject missing referenced identities.
- BR-210: role changes are recorded as significant security actions.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from core.academic_access import (
    ADMIN_ROLES,
    ROLE_STUDENT,
    normalize_role,
)
from core.audit import write_audit_entry
from core.common import ConfigurationError
from apps.notifications.services.notification_service import notify_role_changed


DEFAULT_ROLE = ROLE_STUDENT.upper()
ADMINISTRATOR_ROLES = frozenset(role.upper() for role in ADMIN_ROLES)


class AuthError(ValueError):
    """Base domain error raised by account workflows."""


class DuplicateAccountError(AuthError):
    """Raised when an active account already exists for an identity."""


class IdentityNotFoundError(AuthError):
    """Raised when the referenced academic identity cannot be found."""


class UnauthorizedRoleChangeError(AuthError):
    """Raised when a non-administrator attempts to change a role."""


class SelfRoleAssignmentError(AuthError):
    """Raised when a user attempts to assign their own role."""


class InvalidRoleError(AuthError):
    """Raised when a role is missing or not supported by the account model."""


class WeakPasswordError(AuthError):
    """The submitted password failed the configured validators."""


class InvalidCurrentPasswordError(AuthError):
    """Raised when the current credential does not match."""


class PasswordPolicyError(AuthError):
    """Raised when a replacement credential violates password policy."""


class AccountModelLike(Protocol):
    """Minimal shape expected from an account model (matches the real User)."""

    id: Any
    email: Any
    username: Any
    first_name: Any
    last_name: Any
    role: Any
    is_active: Any

    def save(self) -> Any:
        ...


def _is_active(account: Any) -> bool:
    value = getattr(account, "is_active", None)
    if value is not None:
        return bool(value)
    return str(getattr(account, "status", "")).lower() in {
        "active",
        "enabled",
    }


@transaction.atomic
def register_account(
    *,
    email: str,
    username: str,
    first_name: str,
    last_name: str,
    password: str,
    AccountModel: type[AccountModelLike],
    role: Optional[str] = None,
    lecturer_approval_status: Optional[str] = None,
    department_id: Any = None,
    level: str = "",
    matricule: Optional[str] = None,
    staffid: Optional[str] = None,
) -> AccountModelLike:
    """Create one account with a **server-resolved** role.

    BR-001: reject duplicate active accounts.
    BR-002: registrations default to STUDENT.
    BR-003: role is set server-side, never from client input.
    BR-170: reject missing required fields.

    ``role`` is a *server* decision. Callers pass the output of
    ``registration_eligibility.resolve_role``, which derives it from the
    requested account type and cannot yield ADMINISTRATOR. The public
    serializers never expose a role field, so there is no path from the
    request body to this argument.

    ``lecturer_approval_status`` is likewise server-owned: a self-registering
    lecturer is created PENDING and holds no academic privileges until an
    administrator approves them. It is ``None`` for every other account,
    including those created by an administrator or a roster import.
    """
    if AccountModel is None:
        raise ConfigurationError("AccountModel is required")

    manager = getattr(AccountModel, "objects", None)
    if manager is None or not hasattr(manager, "filter"):
        raise ConfigurationError("AccountModel.objects.filter is required")

    # BR-001, BR-170: reject missing fields and duplicate active accounts.
    if not email or not str(email).strip():
        raise IdentityNotFoundError("Email is required")
    if not username or not str(username).strip():
        raise IdentityNotFoundError("Username is required")
    if not first_name or not str(first_name).strip():
        raise IdentityNotFoundError("First name is required")
    if not last_name or not str(last_name).strip():
        raise IdentityNotFoundError("Last name is required")
    if not password:
        raise IdentityNotFoundError("Password is required")

    existing = manager.filter(email=str(email).strip().lower())
    if any(_is_active(record) for record in existing):
        raise DuplicateAccountError(
            f"An active account already exists for {email}"
        )

    # BR-002/BR-203 + AUTH_PASSWORD_VALIDATORS: enforced here, in the one place
    # every registration path passes through. It previously lived only in
    # RegisterSerializer, so the self-registration serializer could bypass it
    # and accept "12345678". The candidate carries the submitted identity so
    # UserAttributeSimilarityValidator can compare against it.
    candidate = None
    if hasattr(AccountModel, "objects"):
        try:
            candidate = AccountModel(
                email=str(email).strip().lower(),
                username=str(username).strip().lower(),
                first_name=str(first_name).strip(),
                last_name=str(last_name).strip(),
            )
        except Exception:  # pragma: no cover - Protocol models without kwargs
            candidate = None
    try:
        validate_password(password, user=candidate)
    except DjangoValidationError as exc:
        raise WeakPasswordError(" ".join(exc.messages)) from exc

    # BR-002, BR-003: the role is whatever the server resolved, never a client
    # field. A caller that omits it still gets STUDENT.
    resolved_role = str(role).strip().upper() if role else DEFAULT_ROLE
    extras = {
        "lecturer_approval_status": lecturer_approval_status if resolved_role == "LECTURER" else None,
        "department_id": department_id,
        "level": str(level or "").strip().upper(),
        "matricule": str(matricule).strip().upper() if matricule else None,
        "staffid": str(staffid).strip().upper() if staffid else None,
    }
    # The actual User model's create_user handles password hashing.
    try:
        account = manager.create_user(
            email=str(email).strip().lower(),
            username=str(username).strip().lower(),
            first_name=str(first_name).strip(),
            last_name=str(last_name).strip(),
            password=password,
            role=resolved_role,
            **{
                key: value
                for key, value in extras.items()
                if value not in (None, "")
            },
        )
    except AttributeError:
        # Fallback for Protocol-based callers that provide custom models.
        account = AccountModel()
        account.email = str(email).strip().lower()
        account.username = str(username).strip().lower()
        account.first_name = str(first_name).strip()
        account.last_name = str(last_name).strip()
        account.role = resolved_role
        if hasattr(account, "lecturer_approval_status"):
            account.lecturer_approval_status = lecturer_approval_status if resolved_role == "LECTURER" else None
        if hasattr(account, "is_active"):
            account.is_active = True
        if hasattr(account, "set_password"):
            account.set_password(password)
        account.save()

    write_audit_entry(
        action="account_registered", resource_type="account", resource_id=account.id,
        actor_id=account.id, details={"role": resolved_role, "lecturer_approval_status": lecturer_approval_status},
    )
    return account


def change_account_password(*, account: Any, current_password: str, new_password: str):
    """Atomically replace a password and clear an institution-issued lock."""
    if account is None or not new_password:
        raise PasswordPolicyError("A new password is required.")

    # Django's session middleware exposes request.user as SimpleLazyObject;
    # _meta.model resolves the concrete custom user without trusting a caller-
    # supplied model class.
    model = account._meta.model
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=account.pk)
        if not locked.check_password(current_password):
            raise InvalidCurrentPasswordError("Current password is incorrect.")
        if locked.check_password(new_password):
            raise PasswordPolicyError(
                "The new password must differ from the current password."
            )
        try:
            validate_password(new_password, locked)
        except DjangoValidationError as exc:
            raise PasswordPolicyError(" ".join(exc.messages)) from exc

        was_forced = locked.must_change_password
        locked.set_password(new_password)
        locked.must_change_password = False
        locked.save(update_fields=["password", "must_change_password"])
        write_audit_entry(
            action="password_changed",
            resource_type="account",
            resource_id=locked.pk,
            actor_id=locked.pk,
            details={"cleared_temporary_password": was_forced},
        )
    return locked


def change_user_role(
    account: AccountModelLike,
    new_role: str,
    *,
    actor: Any,
    allowed_roles: Optional[set[str]] = None,
) -> AccountModelLike:
    """Change an account role only when an administrator explicitly does so."""
    # BR-002: role changes require an authorized administrator and cannot be
    # self-assigned by the affected user.
    if account is None or actor is None:
        raise UnauthorizedRoleChangeError("Account and administrator are required")
    if getattr(account, "id", None) == getattr(actor, "id", None):
        raise SelfRoleAssignmentError("Users cannot assign themselves a role")
    if normalize_role(getattr(actor, "role", None)) not in ADMIN_ROLES:
        raise UnauthorizedRoleChangeError("Only an administrator may change roles")

    normalized_role = str(new_role).strip().upper() if new_role is not None else ""
    if not normalized_role:
        raise InvalidRoleError("A role is required")
    if allowed_roles is not None and normalized_role not in {
        str(role).upper() for role in allowed_roles
    }:
        raise InvalidRoleError(f"Unsupported role: {new_role}")

    old_role = getattr(account, "role", None)
    account.role = normalized_role
    account.save()

    # BR-210: role changes are significant security actions and must be audited.
    write_audit_entry(
        action="role_changed",
        resource_type="account",
        resource_id=account.id,
        actor_id=actor.id,
        old_value=old_role,
        new_value=normalized_role,
    )
    # BR §23 + API §45: the account whose role changed may see the change in
    # its own inbox (the recipient is the target account, never the admin).
    notify_role_changed(
        account=account, old_role=old_role, new_role=normalized_role
    )
    return account


def get_server_role(account: AccountModelLike) -> str:
    """Return the stored role used as the sole permission source."""
    # BR-003: never derive permissions from frontend-provided claims.
    if account is None or getattr(account, "role", None) is None:
        raise InvalidRoleError("Account has no server-side role")
    return str(account.role).upper()
