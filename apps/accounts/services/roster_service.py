"""Secure, administrator-driven student roster provisioning."""

from __future__ import annotations

import csv
import io
import re
import secrets
from dataclasses import dataclass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from apps.academic.models import Department
from core.audit import write_audit_entry

from ..models import User


MAX_ROSTER_BYTES = 2 * 1024 * 1024
MAX_ROSTER_ROWS = 5000
ROSTER_COLUMNS = (
    "matricule",
    "first_name",
    "last_name",
    "email",
    "level",
    "department_code",
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_SAFE_LEVEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class RosterError(ValueError):
    """Raised when the upload itself is invalid and no rows may be processed."""


class RosterRowError(ValueError):
    """Raised when one row is invalid; other rows may still be processed."""


@dataclass(frozen=True)
class RosterRow:
    matricule: str
    first_name: str
    last_name: str
    email: str
    level: str
    department_code: str


def _clean_text(value, *, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise RosterRowError(f"{label} is required.")
    if len(text) > max_length:
        raise RosterRowError(f"{label} is too long.")
    if any(ord(character) < 32 for character in text):
        raise RosterRowError(f"{label} contains invalid control characters.")
    return text


def _normalize_row(raw: dict[str, str]) -> RosterRow:
    matricule = _clean_text(raw.get("matricule"), label="Matricule", max_length=50)
    if not _SAFE_IDENTIFIER.fullmatch(matricule):
        raise RosterRowError("Matricule contains unsupported characters.")

    first_name = _clean_text(raw.get("first_name"), label="First name", max_length=150)
    last_name = _clean_text(raw.get("last_name"), label="Last name", max_length=150)
    email = _clean_text(raw.get("email"), label="Email", max_length=254).lower()
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise RosterRowError("Email is invalid.") from exc

    level = _clean_text(raw.get("level"), label="Level", max_length=10).upper()
    if not _SAFE_LEVEL.fullmatch(level):
        raise RosterRowError("Level contains unsupported characters.")

    department_code = _clean_text(
        raw.get("department_code"), label="Department code", max_length=30
    ).upper()
    if not _SAFE_IDENTIFIER.fullmatch(department_code):
        raise RosterRowError("Department code contains unsupported characters.")

    return RosterRow(
        matricule=matricule.upper(),
        first_name=first_name,
        last_name=last_name,
        email=email,
        level=level,
        department_code=department_code,
    )


def _read_rows(uploaded_file) -> list[tuple[int, dict[str, str]]]:
    if uploaded_file is None:
        raise RosterError("A CSV file is required.")
    if getattr(uploaded_file, "size", 0) > MAX_ROSTER_BYTES:
        raise RosterError("The roster file exceeds the 2 MB limit.")

    payload = uploaded_file.read(MAX_ROSTER_BYTES + 1)
    if len(payload) > MAX_ROSTER_BYTES:
        raise RosterError("The roster file exceeds the 2 MB limit.")
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise RosterError("The roster must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
    if tuple(headers) != ROSTER_COLUMNS:
        raise RosterError(
            "CSV columns must be exactly: " + ", ".join(ROSTER_COLUMNS) + "."
        )

    rows = []
    for line_number, raw in enumerate(reader, start=2):
        if line_number - 1 > MAX_ROSTER_ROWS:
            raise RosterError(f"A roster may contain at most {MAX_ROSTER_ROWS} rows.")
        if raw.get(None):
            raise RosterError(f"Line {line_number} has more values than columns.")
        rows.append((line_number, raw))
    if not rows:
        raise RosterError("The roster contains no student rows.")
    return rows


def _temporary_password(user: User) -> str:
    """Generate a validator-compliant password without weakening policy."""
    for _ in range(10):
        candidate = secrets.token_urlsafe(18)
        try:
            validate_password(candidate, user=user)
        except DjangoValidationError:
            continue
        return candidate
    raise RosterRowError("Could not generate a secure temporary password.")


def _upsert_student(row: RosterRow, *, actor: User) -> tuple[str, User, str | None]:
    department = Department.objects.filter(code__iexact=row.department_code).first()
    if department is None:
        raise RosterRowError("Department code is not recognized.")

    by_email = User.objects.select_for_update().filter(email__iexact=row.email).first()
    by_matricule = (
        User.objects.select_for_update()
        .filter(matricule__iexact=row.matricule)
        .first()
    )
    if by_email is not None and by_matricule is not None and by_email.pk != by_matricule.pk:
        raise RosterRowError("Email and matricule belong to different accounts.")

    user = by_email or by_matricule
    if user is not None:
        if user.role != User.Role.STUDENT:
            raise RosterRowError("The matched account is not a student account.")
        collision = User.objects.exclude(pk=user.pk).filter(
            email__iexact=row.email
        ).exists() or User.objects.exclude(pk=user.pk).filter(
            matricule__iexact=row.matricule
        ).exists()
        if collision:
            raise RosterRowError("Email or matricule belongs to another account.")

        changed_fields = []
        assignments = {
            "email": row.email,
            "matricule": row.matricule,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "department": department,
            "faculty": department.faculty,
            "level": row.level,
        }
        for field, value in assignments.items():
            current = getattr(user, f"{field}_id", None) if field in {"department", "faculty"} else getattr(user, field)
            expected = value.pk if field in {"department", "faculty"} and value is not None else value
            if current != expected:
                setattr(user, field, value)
                changed_fields.append(field)
        if changed_fields:
            changed_fields.append("updated_at")
            user.save(update_fields=changed_fields)

        write_audit_entry(
            action="roster_student_updated",
            resource_type="account",
            resource_id=user.pk,
            actor_id=actor.pk,
            details={"changed_fields": changed_fields[:-1] if changed_fields else []},
        )
        return "updated", user, None

    username = row.matricule.lower()
    if User.objects.filter(username__iexact=username).exists():
        raise RosterRowError("Matricule conflicts with an existing login identifier.")

    user = User(
        email=row.email,
        username=username,
        first_name=row.first_name,
        last_name=row.last_name,
        matricule=row.matricule,
        role=User.Role.STUDENT,
        department=department,
        faculty=department.faculty,
        level=row.level,
        is_active=True,
        is_email_verified=True,
        must_change_password=True,
    )
    temporary_password = _temporary_password(user)
    user.set_password(temporary_password)
    user.save()
    write_audit_entry(
        action="roster_student_created",
        resource_type="account",
        resource_id=user.pk,
        actor_id=actor.pk,
        details={
            "department_id": department.pk,
            "level": row.level,
            "temporary_password_issued": True,
        },
    )
    return "created", user, temporary_password


def import_student_roster(uploaded_file, *, actor: User) -> dict:
    """Import a strict CSV; role and security flags are always server-owned."""
    rows = _read_rows(uploaded_file)
    created = []
    updated = []
    errors = []

    with transaction.atomic():
        for line_number, raw in rows:
            matricule = str(raw.get("matricule") or "").strip()[:50]
            try:
                row = _normalize_row(raw)
                with transaction.atomic():
                    outcome, user, temporary_password = _upsert_student(row, actor=actor)
            except (RosterRowError, IntegrityError) as exc:
                message = str(exc) if isinstance(exc, RosterRowError) else "Identity conflicts with an existing account."
                errors.append({"line": line_number, "matricule": matricule, "error": message})
                continue

            if outcome == "created":
                created.append(
                    {
                        "id": str(user.pk),
                        "email": user.email,
                        "matricule": user.matricule,
                        "full_name": f"{user.first_name} {user.last_name}".strip(),
                        "temp_password": temporary_password,
                    }
                )
            else:
                updated.append(
                    {
                        "id": str(user.pk),
                        "email": user.email,
                        "matricule": user.matricule,
                        "full_name": f"{user.first_name} {user.last_name}".strip(),
                    }
                )

        write_audit_entry(
            action="student_roster_uploaded",
            resource_type="student_roster",
            resource_id=actor.pk,
            actor_id=actor.pk,
            details={
                "created_count": len(created),
                "updated_count": len(updated),
                "error_count": len(errors),
            },
        )

    return {
        "created_count": len(created),
        "updated_count": len(updated),
        "error_count": len(errors),
        "created": created,
        "updated": updated,
        "errors": errors,
    }
