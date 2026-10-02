"""Audit trail helper for significant platform actions.

This helper is intentionally framework-agnostic and plain-Python so it can be
called by services without including any Django request or DRF response logic.
The goal is to keep all significant academic corrections and security-sensitive
actions traceable and non-silent.

Business rules enforced here:
- BR-042: attendance corrections retain an audit trail and never silently
  overwrite historical activity.
- BR-132: every significant assessment create/modify action is traceable.
- BR-210: important actions involving authentication, attendance, assessments,
  projects, permissions, and security settings must be audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID


def _json_safe(value: Any) -> Any:
    """Coerce audit payloads into JSON-serializable primitives.

    Audit details routinely carry UUIDs (scope/student/project ids),
    datetimes, and decimals, which the AuditEvent JSONField cannot encode;
    rather than losing the audit record (or crashing the business action),
    every value is converted to a safe primitive recursively.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


class AuditError(ValueError):
    """Raised when an audit event cannot be recorded safely."""


class ProtectedAuditEntryError(AuditError):
    """Raised if an attempt is made to mutate an audit record itself."""


@dataclass
class AuditEntry:
    action: str
    resource_type: str
    resource_id: Any
    actor_id: Any
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    correlation_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "actor_id": self.actor_id,
            "details": dict(self.details or {}),
            "timestamp": self.timestamp.isoformat(),
            "old_value": self.old_value,
            "new_value": self.new_value,
            "correlation_id": self.correlation_id,
        }


def _normalize_resource_name(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def _ensure_action_is_important(action: str) -> None:
    if not action or not str(action).strip():
        raise AuditError("Audit action is required")


def _build_correlation_id(*parts: Any) -> Optional[str]:
    values = [str(part) for part in parts if part is not None]
    if not values:
        return None
    return "::".join(values)


def write_audit_entry(
    *,
    action: str,
    resource_type: str,
    resource_id: Any,
    actor_id: Any,
    details: Optional[Dict[str, Any]] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    timestamp: Optional[datetime] = None,
    allowed_actions: Optional[Iterable[str]] = None,
) -> AuditEntry:
    """Persist a single audit record for a significant platform action.

    This helper is intentionally generic: attendance corrections, assessment
    changes, and permission/auth actions all use it to retain a traceable record
    without mutating historical data.
    """
    # BR-042: corrections must be traceable; this helper ensures every change is
    # captured while preserving the original historical record.
    # BR-132: significant assessment changes must be traceable.
    # BR-210: important actions across auth, attendance, projects, assessments,
    # permissions, and security must be audited.
    _ensure_action_is_important(action)
    if resource_type is None:
        raise AuditError("Resource type is required")
    if resource_id is None:
        raise AuditError("Resource id is required")
    if actor_id is None:
        raise AuditError("Actor id is required")

    if allowed_actions is not None:
        allowed = {str(item).strip() for item in allowed_actions if item is not None}
        if action not in allowed:
            raise AuditError(f"Action '{action}' is not allowed for audit logging")

    entry = AuditEntry(
        action=str(action),
        resource_type=str(resource_type),
        resource_id=resource_id,
        actor_id=actor_id,
        details=_json_safe(dict(details or {})),
        old_value=_json_safe(old_value),
        new_value=_json_safe(new_value),
        timestamp=timestamp or datetime.now(timezone.utc),
        correlation_id=_build_correlation_id(resource_type, resource_id, action, actor_id),
    )
    # Audit records are durable.  Import lazily to keep this helper usable
    # during Django startup while ensuring normal application actions cannot
    # silently lose their audit trail.
    from .models import AuditEvent

    AuditEvent.objects.create(
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=str(entry.resource_id),
        actor_id=str(entry.actor_id),
        details=entry.details,
        old_value=entry.old_value,
        new_value=entry.new_value,
        correlation_id=entry.correlation_id,
        timestamp=entry.timestamp,
    )
    return entry


def audit_correction(
    *,
    action: str,
    resource_type: str,
    resource_id: Any,
    actor_id: Any,
    reason: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> AuditEntry:
    """Create a correction audit entry with standardized details.

    This function is designed for attendance and assessment edits that are not
    silent overwrites; the original state remains preserved and an explicit
    correction event is recorded.
    """
    details = {
        "correction": True,
        "reason": reason or "record corrected",
    }
    if metadata:
        details.update(metadata)

    return write_audit_entry(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        details=details,
        old_value=old_value,
        new_value=new_value,
        timestamp=timestamp,
    )


def audit_assessment_change(
    *,
    actor_id: Any,
    assessment_id: Any,
    reason: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> AuditEntry:
    """Record a significant assessment creation or modification."""
    # BR-132: every significant assessment creation or modification must be
    # traceable, which is exactly what this helper records.
    return audit_correction(
        action="assessment_updated",
        resource_type="assessment",
        resource_id=assessment_id,
        actor_id=actor_id,
        reason=reason or "assessment record changed",
        old_value=old_value,
        new_value=new_value,
        metadata=metadata,
        timestamp=timestamp,
    )


def ensure_audit_record_is_protected(record: Any) -> None:
    """Protect audit records from direct overwrite by ordinary actors.

    This is a guardrail function that services can call before mutating an audit
    record or after reading it from a persistence layer.
    """
    # BR-211: audit records are protected and must not be modified by ordinary
    # students or lecturers.
    if record is None:
        raise ProtectedAuditEntryError("Audit record is required")
    if hasattr(record, "is_audit_record"):
        if record.is_audit_record is False:
            raise ProtectedAuditEntryError("This record is not an audit record")


def summarize_audit_history(entries: Iterable[AuditEntry]) -> List[Dict[str, Any]]:
    """Return an audit trail in dict form for standard downstream processing."""
    return [entry.as_dict() for entry in entries]
