"""Security-critical attendance workflows (BR-030 through BR-064)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.academic.models import ClassSession, Enrollment
from apps.academic.services.eligibility_service import is_student_eligible_for_class
from apps.accounts.models import User
from apps.attendance.models import (
    AttendanceCheckpoint,
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceSession,
)
from core.academic_access import is_admin_user, is_authorized_academic_user
from apps.attendance.utils.qr_tokens import (
    InvalidTokenError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    consume_token,
    generate_token,
)
from core.audit import write_audit_entry
from apps.notifications.services.notification_service import (
    notify_attendance_corrected,
    notify_suspicious_activity_flagged,
)


class AttendanceError(ValueError):
    """Base error for every rejected attendance operation."""


class SessionExpiredError(AttendanceError):
    """Session is inactive, closed, expired, or belongs to another token."""


class NotEligibleError(AttendanceError):
    """Authenticated student is not enrolled in the session's course."""


class AlreadyMarkedError(AttendanceError):
    """The student already has an attendance record in this session."""


class TokenStudentMismatchError(AttendanceError):
    """A checkpoint QR cannot be used to credit a different student."""


class LecturerNotAuthorizedError(AttendanceError):
    """Lecturer is not allowed to select checkpoints or correct attendance."""


class CheckpointNotEligibleError(AttendanceError):
    """A selected checkpoint student is not eligible for this class."""


class CorrectionAuthorizationError(AttendanceError):
    """An attendance correction lacks lecturer authority or an audit reason."""


class ClassSessionNotFoundError(AttendanceError):
    """The class the lecturer tried to open a session for does not exist."""


class SessionAlreadyActiveError(AttendanceError):
    """An unexpired active attendance session already exists for this class."""


class SessionNotActiveError(AttendanceError):
    """The session is closed or expired and no longer accepts actions."""


# BR-036: session windows stay short by design; the default comes from
# settings, and the lecturer may pick a duration inside this band.
ATTENDANCE_SESSION_MIN_SECONDS = 10
ATTENDANCE_SESSION_MAX_SECONDS = 600


def _session_is_active(session: AttendanceSession, now: Optional[datetime] = None) -> bool:
    now = now or timezone.now()
    return session.status == AttendanceSession.Status.ACTIVE and session.expires_at > now


def _ensure_active_matching_session(session: AttendanceSession, token_session_id: str) -> None:
    if str(session.id) != str(token_session_id) or not _session_is_active(session):
        raise SessionExpiredError("Attendance session is inactive, expired, or does not match this token")


def select_checkpoints(*, lecturer: User, session: AttendanceSession, student_ids: Iterable[Any]) -> List[AttendanceCheckpoint]:
    """Create session-scoped checkpoints after server-side eligibility checks."""
    if lecturer is None or session is None or str(lecturer.id) != str(session.lecturer_id):
        raise LecturerNotAuthorizedError("Only the session lecturer can select checkpoints")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot select checkpoints for an inactive session")

    selected = list(dict.fromkeys(student_ids or []))
    if not selected:
        raise CheckpointNotEligibleError("At least one eligible checkpoint student is required")

    checkpoints: List[AttendanceCheckpoint] = []
    for student_id in selected:
        eligible = is_student_eligible_for_class(
            student_id,
            class_id=session.class_session_id,
            ClassModel=ClassSession,
            EnrollmentModel=Enrollment,
        )
        if not eligible:
            raise CheckpointNotEligibleError("Checkpoint student is not eligible for this class")
        checkpoint, _ = AttendanceCheckpoint.objects.get_or_create(
            attendance_session=session, student_id=student_id
        )
        checkpoints.append(checkpoint)
    return checkpoints


def generate_checkpoint_token(*, lecturer: User, checkpoint: AttendanceCheckpoint) -> str:
    """Issue a ten-second token only for a valid, session-scoped checkpoint."""
    session = checkpoint.attendance_session
    if str(lecturer.id) != str(session.lecturer_id):
        raise LecturerNotAuthorizedError("Only the session lecturer can issue checkpoint tokens")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot issue a token for an inactive session")
    return generate_token(checkpoint_id=checkpoint.id, session_id=session.id)


def scan_attendance(*, authenticated_student: User, token: str) -> AttendanceRecord:
    """Consume one QR token and create exactly one authenticated attendance record.

    The ordered checks mirror BR-033/038/036/037/031/040.  Token consumption
    is atomic in the cache and database uniqueness is the final race defense.
    """
    if authenticated_student is None or not authenticated_student.is_authenticated:
        raise NotEligibleError("An authenticated student account is required")
    if authenticated_student.role != User.Role.STUDENT:
        raise NotEligibleError("Only student accounts can scan attendance")

    # 1–2. Missing/expired and replayed tokens are named token exceptions.
    payload = consume_token(token)

    with transaction.atomic():
        checkpoint = AttendanceCheckpoint.objects.select_related("attendance_session").filter(
            id=payload.get("checkpoint_id")
        ).first()
        if checkpoint is None:
            raise InvalidTokenError("Attendance checkpoint does not exist")

        # Lock the session so concurrent close/expiry operations cannot interleave
        # between validation and record insertion on PostgreSQL.
        session = AttendanceSession.objects.select_for_update().filter(id=checkpoint.attendance_session_id).first()
        if session is None:
            raise SessionExpiredError("Attendance session no longer exists")
        _ensure_active_matching_session(session, payload.get("session_id", ""))
        if str(checkpoint.attendance_session_id) != str(session.id):
            raise SessionExpiredError("Checkpoint belongs to a different attendance session")

        # This binding defeats screenshot sharing: a checkpoint token only credits
        # the exact student selected for that checkpoint, never an arbitrary peer.
        if str(checkpoint.student_id) != str(authenticated_student.id):
            raise TokenStudentMismatchError("QR token was issued for another student")

        eligible = is_student_eligible_for_class(
            authenticated_student.id,
            class_id=session.class_session_id,
            ClassModel=ClassSession,
            EnrollmentModel=Enrollment,
        )
        if not eligible:
            raise NotEligibleError("Student is not eligible for this class")

        if AttendanceRecord.objects.filter(
            attendance_session=session, student=authenticated_student
        ).exists():
            raise AlreadyMarkedError("Student is already marked for this session")

        try:
            record = AttendanceRecord.objects.create(
                attendance_session=session,
                student=authenticated_student,
                checkpoint=checkpoint,
            )
        except IntegrityError as exc:
            # BR-040 final race defense: UNIQUE(session, student) remains
            # authoritative if two transactions passed the fast-fail query.
            raise AlreadyMarkedError("Student is already marked for this session") from exc

        write_audit_entry(
            action="attendance_recorded",
            resource_type="attendance_record",
            resource_id=record.id,
            actor_id=authenticated_student.id,
            details={"session_id": str(session.id), "checkpoint_id": str(checkpoint.id)},
        )
    return record


def correct_attendance(*, record: AttendanceRecord, lecturer: User, reason: str) -> AttendanceCorrection:
    """Append a correction event; never silently overwrite original attendance.

    Default correction policy (BR-042 permits "an authorized lecturer or
    administrator"; the finer contours of §32 remain for institutional
    confirmation — see BUSINESS_REQUIREMENTS-1.md): the record's session
    lecturer or any administrator may append a correction.  The authorization
    check runs before any validation detail is revealed so callers can map a
    non-owner to the same shape as a missing record (§25 permission denial).
    """
    session_owner = str(record.attendance_session.lecturer_id) == str(lecturer.id)
    if not session_owner and not is_admin_user(lecturer):
        raise CorrectionAuthorizationError(
            "Only the session lecturer or an administrator can correct attendance"
        )
    if not reason or not reason.strip():
        raise CorrectionAuthorizationError("A correction reason is required")
    with transaction.atomic():
        correction = AttendanceCorrection.objects.create(
            attendance_record=record, corrected_by=lecturer, reason=reason.strip()
        )
        write_audit_entry(
            action="attendance_corrected",
            resource_type="attendance_record",
            resource_id=record.id,
            actor_id=lecturer.id,
            details={"correction_id": correction.id, "reason": correction.reason},
        )
    # BR §23 + API §45: the record's student is eligible to see the correction
    # on their own attendance (recipient is the record owner, not the reviewer).
    notify_attendance_corrected(record=record, correction=correction)
    return correction


def flag_suspicious_activity(*, actor_id: Any, reason: str, metadata: Optional[dict[str, Any]] = None) -> None:
    """Flag for review only; callers must never use this to block a valid scan."""
    write_audit_entry(
        action="attendance_suspicious_activity",
        resource_type="attendance_security_event",
        resource_id=f"{actor_id}:{timezone.now().isoformat()}",
        actor_id=actor_id,
        details={"reason": reason, **(metadata or {})},
    )
    # BR §23 + API §45: the flagged account is the only eligible recipient of
    # its own security flag (BR-064 flags for review; they never auto-deny).
    notify_suspicious_activity_flagged(
        actor_id=actor_id, reason=reason, metadata=metadata
    )


SUSPICIOUS_FAILURE_THRESHOLD = 3
SUSPICIOUS_FAILURE_WINDOW_SECONDS = 60


def evaluate_repeated_failure(
    *,
    cache_backend: Any,
    actor_id: Any,
    failure_code: str,
    request_ip: Optional[str] = None,
) -> bool:
    """BR-064: track repeated scan failures and flag suspicious patterns.

    Returns True if a suspicious activity flag was raised.
    This function decides when to flag — callers only supply the cache
    backend and identifiers; the threshold is owned by this service.
    """
    key = f"attendance:scan-failures:{actor_id}:{failure_code}"
    cache_backend.add(key, 0, timeout=SUSPICIOUS_FAILURE_WINDOW_SECONDS)
    try:
        failures = cache_backend.incr(key)
    except ValueError:
        failures = 1

    if failures >= SUSPICIOUS_FAILURE_THRESHOLD:
        metadata: dict[str, Any] = {"failure_code": failure_code}
        if request_ip:
            metadata["request_ip"] = request_ip
        flag_suspicious_activity(
            actor_id=actor_id,
            reason="repeated_invalid_attendance_scan",
            metadata=metadata,
        )
        return True
    return False


def _resolve_session_duration(duration_seconds: Optional[int]) -> int:
    """Return a validated session duration; default from settings (BR-036)."""
    if duration_seconds is None:
        value = int(getattr(settings, "ATTENDANCE_SESSION_TTL_SECONDS", 60))
    else:
        value = int(duration_seconds)
    if value < ATTENDANCE_SESSION_MIN_SECONDS or value > ATTENDANCE_SESSION_MAX_SECONDS:
        raise AttendanceError(
            f"Attendance session duration must be between "
            f"{ATTENDANCE_SESSION_MIN_SECONDS} and {ATTENDANCE_SESSION_MAX_SECONDS} seconds"
        )
    return value


def start_attendance_session(
    *,
    actor: User,
    class_session_id: Any,
    duration_seconds: Optional[int] = None,
) -> AttendanceSession:
    """BR-030/BR-036: open an attendance window on a lecturer's own class.

    Only academic users may start sessions, and (unless the actor is an
    administrator) only the lecturer who owns the class session may open it.
    At most one live session per class at a time; a lecturer re-opening the
    same class while a session is still unexpired is a conflict.
    """
    if actor is None or not actor.is_authenticated:
        raise LecturerNotAuthorizedError("Authentication is required to start an attendance session")
    if not is_authorized_academic_user(actor):
        raise LecturerNotAuthorizedError("Only academic users can start attendance sessions")

    try:
        class_session = ClassSession.objects.select_related("course").get(id=class_session_id)
    except (ClassSession.DoesNotExist, ValueError, TypeError):
        raise ClassSessionNotFoundError("Class session does not exist")

    if not is_admin_user(actor) and str(class_session.lecturer_id) != str(actor.id):
        raise LecturerNotAuthorizedError("Only the class lecturer can start this attendance session")

    duration = _resolve_session_duration(duration_seconds)
    now = timezone.now()

    live = AttendanceSession.objects.filter(
        class_session=class_session,
        status=AttendanceSession.Status.ACTIVE,
        expires_at__gt=now,
    ).first()
    if live is not None:
        raise SessionAlreadyActiveError("An active attendance session already exists for this class")

    session = AttendanceSession.objects.create(
        class_session=class_session,
        lecturer=actor,
        expires_at=now + timedelta(seconds=duration),
    )
    write_audit_entry(
        action="attendance_session_started",
        resource_type="attendance_session",
        resource_id=session.id,
        actor_id=actor.id,
        details={
            "class_session_id": str(class_session.id),
            "course_code": class_session.course.code,
            "duration_seconds": duration,
        },
    )
    return session


def refresh_session_status(session: AttendanceSession) -> AttendanceSession:
    """Lazily flip an over-time ACTIVE session to EXPIRED (BR-036/BR-041)."""
    if (
        session.status == AttendanceSession.Status.ACTIVE
        and session.expires_at <= timezone.now()
    ):
        session.status = AttendanceSession.Status.EXPIRED
        session.save(update_fields=["status"])
    return session


def close_attendance_session(*, actor: User, session: AttendanceSession) -> AttendanceSession:
    """Close a live session; only the session lecturer (or an admin) may do so."""
    if actor is None or not actor.is_authenticated:
        raise LecturerNotAuthorizedError("Authentication is required to close an attendance session")
    if not is_admin_user(actor) and str(actor.id) != str(session.lecturer_id):
        raise LecturerNotAuthorizedError("Only the session lecturer can close this session")

    if session.status == AttendanceSession.Status.CLOSED:
        raise SessionNotActiveError("Attendance session is already closed")

    refresh_session_status(session)
    if session.status != AttendanceSession.Status.ACTIVE:
        raise SessionNotActiveError("Only an active attendance session can be closed")

    session.status = AttendanceSession.Status.CLOSED
    session.save(update_fields=["status"])
    write_audit_entry(
        action="attendance_session_closed",
        resource_type="attendance_session",
        resource_id=session.id,
        actor_id=actor.id,
        details={"class_session_id": str(session.class_session_id)},
    )
    return session


def eligible_students_for_session(*, session: AttendanceSession) -> List[User]:
    """BR-031/BR-050: the checkpoint roster is the active course enrollment.

    Eligibility is never manual: the same enrollment-derived rule the scan
    path enforces powers the lecturer's checkpoint picker.
    """
    return list(
        User.objects.filter(
            role=User.Role.STUDENT,
            enrollments__course_id=session.class_session.course_id,
            enrollments__is_active=True,
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def list_review_flags(*, actor: User, limit: int = 100) -> List[dict[str, Any]]:
    """BR-064 review surface.

    Suspicious-activity flags are audit events (never denials).  A lecturer
    sees flags raised for students in classes they teach; an administrator
    sees all flags, newest first.
    """
    from core.models import AuditEvent

    if actor is None or not actor.is_authenticated:
        raise LecturerNotAuthorizedError("Authentication is required to review attendance flags")

    flag_events = AuditEvent.objects.filter(
        action="attendance_suspicious_activity"
    ).order_by("-timestamp")

    if not is_admin_user(actor):
        my_course_ids = set(
            ClassSession.objects.filter(lecturer=actor).values_list("course_id", flat=True)
        )
        my_student_ids = {
            str(sid)
            for sid in Enrollment.objects.filter(
                course_id__in=my_course_ids, is_active=True
            ).values_list("student_id", flat=True)
        }
        flag_events = [
            event for event in flag_events[:500] if str(event.actor_id) in my_student_ids
        ]
    else:
        flag_events = list(flag_events[:limit])

    students = {
        str(user.id): f"{user.first_name} {user.last_name}".strip() or user.username
        for user in User.objects.filter(id__in=[event.actor_id for event in flag_events])
    }
    return [
        {
            "id": str(event.id),
            "student_id": str(event.actor_id),
            "student_name": students.get(str(event.actor_id), "Unknown student"),
            "reason": (event.details or {}).get("reason"),
            "failure_code": (event.details or {}).get("failure_code"),
            "request_ip": (event.details or {}).get("request_ip"),
            "timestamp": event.timestamp,
        }
        for event in flag_events[:limit]
    ]
