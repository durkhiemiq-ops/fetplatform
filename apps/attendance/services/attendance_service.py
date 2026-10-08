"""Security-critical attendance workflows (BR-030 through BR-064)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.academic.models import ClassSession, CourseOffering, Enrollment
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
    TokenExpiredError,
    generate_token,
    get_qr_token_ttl_seconds,
    validate_token,
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


class SelfScanRejectedError(AttendanceError):
    """A station owner cannot use their own station code to credit themselves."""


class ModeMismatchError(AttendanceError):
    """The credential does not belong to this session's attendance mode."""


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


@transaction.atomic
def select_checkpoints(*, lecturer: User, session: AttendanceSession, student_ids: Iterable[Any]) -> List[AttendanceCheckpoint]:
    """Seed session-scoped stations after validating the full selection.

    Seed selection only exists in STATION mode.  Selecting a seed grants
    scan-point authority and nothing else: it deliberately creates no
    attendance record, because physical presence is a lecturer's judgement
    made in the room, not something software can claim to have verified.
    """
    if (
        lecturer is None
        or not is_authorized_academic_user(lecturer)
        or session is None
        or str(lecturer.id) != str(session.lecturer_id)
    ):
        raise LecturerNotAuthorizedError("Only the session lecturer can select checkpoints")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot select checkpoints for an inactive session")
    if session.mode != AttendanceSession.Mode.STATIONS:
        raise ModeMismatchError(
            "Seeds can only be selected for a student-station session; a projected "
            "code is already scannable by every eligible student"
        )

    selected = list(dict.fromkeys(student_ids or []))
    if not selected:
        raise CheckpointNotEligibleError("At least one eligible checkpoint student is required")

    # Validate the complete request before writing anything. Otherwise a mixed
    # eligible/ineligible payload can persist its early rows before failing.
    for student_id in selected:
        eligible = is_student_eligible_for_class(
            student_id,
            class_id=session.class_session_id,
            ClassModel=ClassSession,
            EnrollmentModel=Enrollment,
        )
        if not eligible:
            raise CheckpointNotEligibleError("Checkpoint student is not eligible for this class")

    now = timezone.now()
    checkpoints: List[AttendanceCheckpoint] = []
    created_ids = []
    for student_id in selected:
        checkpoint, created = AttendanceCheckpoint.objects.get_or_create(
            attendance_session=session,
            student_id=student_id,
            defaults={
                "source": AttendanceCheckpoint.Source.SEED,
                "activated_by": lecturer,
                "activated_at": now,
            },
        )
        checkpoints.append(checkpoint)
        if created:
            created_ids.append(str(checkpoint.pk))

    if created_ids:
        write_audit_entry(
            action="attendance_checkpoints_selected",
            resource_type="attendance_session",
            resource_id=session.pk,
            actor_id=lecturer.pk,
            details={
                "checkpoint_ids": created_ids,
                "student_ids": [str(student_id) for student_id in selected],
            },
        )
    return checkpoints


@transaction.atomic
def auto_select_checkpoints(
    *, lecturer: User, session: AttendanceSession, count: int = 3
) -> List[AttendanceCheckpoint]:
    """Seed ``count`` eligible, not-yet-credited students, deterministically.

    Ordering is stable (username) so a retried or repeated call converges on
    the same roster instead of reshuffling seeds between attempts.
    """
    count = max(1, min(int(count or 3), 20))
    already = set(
        session.checkpoints.values_list("student_id", flat=True)
    )
    marked = set(
        session.records.values_list("student_id", flat=True)
    )
    candidates = [
        student.id
        for student in eligible_students_for_session(session=session)
        if str(student.id) not in {str(pk) for pk in already | marked}
    ][:count]
    if not candidates:
        raise CheckpointNotEligibleError("No unmarked eligible students are available to seed")
    return select_checkpoints(lecturer=lecturer, session=session, student_ids=candidates)


@transaction.atomic
def remove_checkpoint(
    *, lecturer: User, session: AttendanceSession, checkpoint: AttendanceCheckpoint
) -> None:
    """Withdraw a seed that has not yet relayed any attendance."""
    if (
        lecturer is None
        or not is_authorized_academic_user(lecturer)
        or str(lecturer.id) != str(session.lecturer_id)
    ):
        raise LecturerNotAuthorizedError("Only the session lecturer can remove checkpoints")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot change checkpoints for an inactive session")
    if checkpoint.attendance_session_id != session.id:
        raise CheckpointNotEligibleError("Checkpoint does not belong to this session")
    if checkpoint.attendance_records.exists():
        # Records point at the scan point; deleting it would erase evidence of
        # how real attendances were produced. Withdrawal is for unused seeds.
        raise AttendanceError("This station has already relayed attendance and cannot be removed")
    write_audit_entry(
        action="attendance_checkpoint_removed",
        resource_type="attendance_session",
        resource_id=session.pk,
        actor_id=lecturer.pk,
        details={"checkpoint_id": str(checkpoint.pk), "student_id": str(checkpoint.student_id)},
    )
    checkpoint.delete()

def generate_projected_token(*, lecturer: User, session: AttendanceSession) -> str:
    """Issue the shared 10-second code the whole room scans (PROJECTOR mode).

    The code carries no student identity: whoever scans it is credited as
    themselves, and only if they are enrolled in this class.
    """
    if (
        lecturer is None
        or not is_authorized_academic_user(lecturer)
        or str(lecturer.id) != str(session.lecturer_id)
    ):
        raise LecturerNotAuthorizedError("Only the session lecturer can issue QR codes")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot issue a token for an inactive session")
    if session.mode != AttendanceSession.Mode.PROJECTOR:
        raise ModeMismatchError(
            "This session uses student stations; issue a station code instead"
        )
    token = generate_token(session_id=session.id)
    write_audit_entry(
        action="attendance_token_issued",
        resource_type="attendance_session",
        resource_id=session.pk,
        actor_id=lecturer.pk,
        details={"scope": "PROJECTOR"},
    )
    return token


def generate_checkpoint_token(*, lecturer: User, checkpoint: AttendanceCheckpoint) -> str:
    """Issue a ten-second shared station code for a valid, session-scoped scan point."""
    session = checkpoint.attendance_session
    if (
        not is_authorized_academic_user(lecturer)
        or str(lecturer.id) != str(session.lecturer_id)
    ):
        raise LecturerNotAuthorizedError("Only the session lecturer can issue checkpoint tokens")
    if not _session_is_active(session):
        raise SessionExpiredError("Cannot issue a token for an inactive session")
    if session.mode != AttendanceSession.Mode.STATIONS:
        raise ModeMismatchError(
            "This session projects a single code; station codes only exist for "
            "student-station sessions"
        )
    token = generate_token(checkpoint_id=checkpoint.id, session_id=session.id)
    write_audit_entry(
        action="attendance_token_issued",
        resource_type="attendance_checkpoint",
        resource_id=checkpoint.pk,
        actor_id=lecturer.pk,
        details={"attendance_session_id": str(session.pk), "scope": "STATION"},
    )
    return token


def scan_attendance(*, authenticated_student: User, token: str) -> AttendanceRecord:
    """Validate one shared QR and create exactly one authenticated record.

    The ordered checks mirror BR-033/038/036/037/031/040.  The token answers
    "which class, which mode" and nothing else: the credited student is always
    ``authenticated_student`` (BR-039), so a forwarded or screenshotted code can
    only ever mark the person actually holding the phone.

    Two scopes, matching the two MVP modes:

    ``PROJECTOR``
        One code for the room.  Every enrolled scanner credits themselves and
        there is no per-student scan point, so the record's ``checkpoint`` is
        ``NULL``.

    ``STATION``
        The scanned station's owner relays the scan.  The scanner is marked
        PRESENT **and** activated as a station for this session inside the same
        transaction — the seed -> B -> C cascade.  Activation is server-issued,
        session-scoped, and dies with the session; it is never a role on the
        account.

    A second credit for the same student/session is refused here *and* by the
    UNIQUE(session, student) constraint, which stays authoritative under races.
    """
    if authenticated_student is None or not authenticated_student.is_authenticated:
        raise NotEligibleError("An authenticated student account is required")
    if authenticated_student.role != User.Role.STUDENT:
        raise NotEligibleError("Only student accounts can scan attendance")

    # 1-2. Missing/expired tokens are named token exceptions.
    payload = validate_token(token)
    scope = str(payload.get("scope") or "")

    with transaction.atomic():
        # Lock the session so concurrent close/expiry operations cannot interleave
        # between validation and record insertion on PostgreSQL.
        session = AttendanceSession.objects.select_for_update().filter(
            id=payload.get("session_id")
        ).first()
        if session is None:
            raise SessionExpiredError("Attendance session no longer exists")
        if not _session_is_active(session):
            raise SessionExpiredError("Attendance session is inactive, expired, or does not match this token")

        station: Optional[AttendanceCheckpoint] = None
        if scope == "STATION":
            if session.mode != AttendanceSession.Mode.STATIONS:
                raise ModeMismatchError("This session projects a single code, not a station code")
            station = AttendanceCheckpoint.objects.filter(
                id=payload.get("checkpoint_id"), attendance_session=session
            ).first()
            if station is None:
                raise InvalidTokenError("Attendance scan point does not exist")
            # A station owner cannot relay their own code: presence is claimed
            # by scanning somebody else's, never by producing a QR.
            if str(station.student_id) == str(authenticated_student.id):
                raise SelfScanRejectedError(
                    "This is your own station code; scan another station to be marked"
                )
        elif scope == "PROJECTOR":
            if session.mode != AttendanceSession.Mode.PROJECTOR:
                raise ModeMismatchError("This session uses student stations, not a projected code")
        else:
            raise InvalidTokenError("Attendance token payload is invalid")

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
                checkpoint=station,
            )
        except IntegrityError as exc:
            # BR-040 final race defense: UNIQUE(session, student) remains
            # authoritative if two transactions passed the fast-fail query.
            raise AlreadyMarkedError("Student is already marked for this session") from exc

        # Cascade: one atomic business operation — a student who just proved
        # themselves present by scanning a station can relay scans too. If the
        # row already exists (the scanner was a seeded station) nothing changes.
        station_activated = False
        if station is not None:
            _, station_activated = AttendanceCheckpoint.objects.get_or_create(
                attendance_session=session,
                student=authenticated_student,
                defaults={
                    "source": AttendanceCheckpoint.Source.CASCADE,
                    "activated_by": authenticated_student,
                    "activated_at": timezone.now(),
                },
            )

        write_audit_entry(
            action="attendance_recorded",
            resource_type="attendance_record",
            resource_id=record.id,
            actor_id=authenticated_student.id,
            details={
                "session_id": str(session.id),
                "mode": session.mode,
                "scope": scope,
                "station_id": str(station.id) if station is not None else None,
                "station_activated": station_activated,
            },
        )

    # Transient presentation hints for the scan response; never persisted.
    record.station_activated = station_activated
    record.scope = scope
    return record


def correct_attendance(
    *, record: AttendanceRecord, lecturer: User, new_status: str, reason: str
) -> AttendanceCorrection:
    """Append a correction event; never silently overwrite original attendance.

    Default correction policy (BR-042 permits "an authorized lecturer or
    administrator"; the finer contours of §32 remain for institutional
    confirmation — see BUSINESS_REQUIREMENTS-1.md): the record's session
    lecturer or any administrator may append a correction.  The authorization
    check runs before any validation detail is revealed so callers can map a
    non-owner to the same shape as a missing record (§25 permission denial).
    """
    if not is_authorized_academic_user(lecturer):
        raise CorrectionAuthorizationError(
            "Only an authorized academic user can correct attendance"
        )
    session_owner = str(record.attendance_session.lecturer_id) == str(lecturer.id)
    if not session_owner and not is_admin_user(lecturer):
        raise CorrectionAuthorizationError(
            "Only the session lecturer or an administrator can correct attendance"
        )
    if not reason or not reason.strip():
        raise CorrectionAuthorizationError("A correction reason is required")
    valid_statuses = {value for value, _ in AttendanceRecord.Status.choices}
    if new_status not in valid_statuses:
        raise AttendanceError("Invalid attendance status")
    old_status = record.status
    if new_status == old_status:
        raise AttendanceError("The corrected status must differ from the current status")
    with transaction.atomic():
        record.status = new_status
        record.save(update_fields=["status"])
        correction = AttendanceCorrection.objects.create(
            attendance_record=record,
            corrected_by=lecturer,
            old_status=old_status,
            new_status=new_status,
            reason=reason.strip(),
        )
        write_audit_entry(
            action="attendance_corrected",
            resource_type="attendance_record",
            resource_id=record.id,
            actor_id=lecturer.id,
            old_value={"status": old_status},
            new_value={"status": new_status},
            details={"correction_id": correction.id, "reason": correction.reason},
        )
    # BR §23 + API §45: the record's student is eligible to see the correction
    # on their own attendance (recipient is the record owner, not the reviewer).
    notify_attendance_corrected(record=record, correction=correction)
    return correction


@transaction.atomic
def start_flexible_attendance_session(
    *, actor: User, offering_id: Any, duration_seconds: Optional[int] = None,
    mode: Optional[str] = None,
) -> AttendanceSession:
    """Open an unscheduled class occurrence for one assigned course offering."""
    if not is_authorized_academic_user(actor):
        raise LecturerNotAuthorizedError(
            "Only authorized academic users can start attendance sessions"
        )
    offerings = CourseOffering.objects.select_for_update().select_related("course")
    if not is_admin_user(actor):
        offerings = offerings.filter(lecturer=actor)
    try:
        offering = offerings.get(pk=offering_id, status="ACTIVE")
    except (CourseOffering.DoesNotExist, ValueError, TypeError):
        raise ClassSessionNotFoundError("Course offering does not exist")

    if AttendanceSession.objects.filter(
        lecturer=actor,
        class_session__course_offering=offering,
        status=AttendanceSession.Status.ACTIVE,
        expires_at__gt=timezone.now(),
    ).exists():
        raise SessionAlreadyActiveError(
            "An active attendance session already exists for this course"
        )

    class_session = ClassSession.objects.create(
        course=offering.course,
        course_offering=offering,
        lecturer=offering.lecturer or actor,
        starts_at=timezone.now(),
    )
    return start_attendance_session(
        actor=actor,
        class_session_id=class_session.pk,
        duration_seconds=duration_seconds,
        mode=mode,
    )


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

    if failures == SUSPICIOUS_FAILURE_THRESHOLD:
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


def _resolve_session_mode(mode: Optional[str]) -> str:
    """Return a validated attendance mode; projected code is the default."""
    if mode is None:
        return AttendanceSession.Mode.PROJECTOR
    value = str(mode).strip().upper()
    valid = {choice for choice, _ in AttendanceSession.Mode.choices}
    if value not in valid:
        raise AttendanceError(
            "Attendance mode must be one of: " + ", ".join(sorted(valid))
        )
    return value


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


@transaction.atomic
def start_attendance_session(
    *,
    actor: User,
    class_session_id: Any,
    duration_seconds: Optional[int] = None,
    mode: Optional[str] = None,
) -> AttendanceSession:
    """BR-030/BR-036: open an attendance window on a lecturer's own class.

    Only academic users may start sessions, and (unless the actor is an
    administrator) only the lecturer who owns the class session may open it.
    At most one live session per class at a time; a lecturer re-opening the
    same class while a session is still unexpired is a conflict.

    ``mode`` picks between the two first-class MVP modes and is stored, not
    inferred: which code a scan accepts must be a server-side fact.
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
    resolved_mode = _resolve_session_mode(mode)
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
        mode=resolved_mode,
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
            "mode": resolved_mode,
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


@transaction.atomic
def close_attendance_session(*, actor: User, session: AttendanceSession) -> AttendanceSession:
    """Close a live session; only the session lecturer (or an admin) may do so."""
    if actor is None or not actor.is_authenticated:
        raise LecturerNotAuthorizedError("Authentication is required to close an attendance session")
    if not is_authorized_academic_user(actor):
        raise LecturerNotAuthorizedError(
            "Only authorized academic users can close attendance sessions"
        )
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
    enrollments = Enrollment.objects.filter(
        course_id=session.class_session.course_id,
        is_active=True,
    )
    if session.class_session.course_offering_id is not None:
        enrollments = enrollments.filter(
            course_offering_id=session.class_session.course_offering_id
        )
    return list(
        User.objects.filter(
            role=User.Role.STUDENT,
            id__in=enrollments.values("student_id"),
        )
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


def my_active_station(*, student: User) -> Optional[AttendanceCheckpoint]:
    """Return the student's live station, or ``None``.

    Authority is session-scoped and temporary: it exists only while some
    STATION-mode session is ACTIVE and unexpired, so nothing here can outlive
    the class or become a standing role on the account.
    """
    if student is None or not getattr(student, "is_authenticated", False):
        return None
    return (
        AttendanceCheckpoint.objects.select_related(
            "attendance_session__class_session__course"
        )
        .filter(
            student=student,
            attendance_session__mode=AttendanceSession.Mode.STATIONS,
            attendance_session__status=AttendanceSession.Status.ACTIVE,
            attendance_session__expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def station_summary(*, student: User) -> Optional[dict[str, Any]]:
    """Presentation payload for the student's station banner, or ``None``."""
    station = my_active_station(student=student)
    if station is None:
        return None
    session = station.attendance_session
    course = session.class_session.course
    return {
        "attendance_session_id": str(session.id),
        "session_expires_at": session.expires_at,
        "course_code": course.code,
        "class_name": course.name,
        "status": session.status,
        "mode": session.mode,
        "source": station.source,
    }


def station_token(*, student: User, session_id: Any) -> dict[str, Any]:
    """Issue a fresh 10-second station code for a student who *is* a station.

    Called on a short poll by the station's own device; the code relays scans
    from other students, and expires like any other QR (BR-035).
    """
    station = (
        AttendanceCheckpoint.objects.select_related(
            "attendance_session__class_session__course"
        )
        .filter(student=student, attendance_session_id=session_id)
        .first()
    )
    if station is None:
        # No station row for this caller: refusing must not confirm whether the
        # session or the other student exists (§25).
        raise NotEligibleError("You are not an active station for this session")

    session = refresh_session_status(station.attendance_session)
    if not _session_is_active(session):
        raise SessionExpiredError("The attendance window has closed")
    if session.mode != AttendanceSession.Mode.STATIONS:
        raise ModeMismatchError("This session projects a single code, not a station code")

    token = generate_token(checkpoint_id=station.id, session_id=session.id)
    course = session.class_session.course
    return {
        "token": token,
        "expires_in_seconds": get_qr_token_ttl_seconds(),
        "scans_at_station": session.records.filter(checkpoint=station).count(),
        # No scan cap exists in the MVP contract, so this stays null rather
        # than inventing one; the UI hides the field when it is null.
        "scans_remaining": None,
        "total_checked_in": session.records.count(),
        "expected_headcount": len(eligible_students_for_session(session=session)),
        "course_code": course.code,
        "class_name": course.name,
    }


def expected_headcount(*, session: AttendanceSession) -> int:
    """Eligible headcount for one session, from the same enrollment truth.

    Deliberately derived from ``eligible_students_for_session`` rather than a
    second query with its own assumptions: the progress bar the lecturer reads
    and the gate a scan passes must never disagree.
    """
    return len(eligible_students_for_session(session=session))


def list_review_flags(*, actor: User, limit: int = 100) -> List[dict[str, Any]]:
    """BR-064 review surface.

    Suspicious-activity flags are audit events (never denials).  A lecturer
    sees flags raised for students in classes they teach; an administrator
    sees all flags, newest first.
    """
    from core.models import AuditEvent

    if actor is None or not actor.is_authenticated:
        raise LecturerNotAuthorizedError("Authentication is required to review attendance flags")
    if not is_authorized_academic_user(actor):
        raise LecturerNotAuthorizedError(
            "Only authorized academic users can review attendance flags"
        )

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
