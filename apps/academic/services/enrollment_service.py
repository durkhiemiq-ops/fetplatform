"""Course enrollment service.

This module implements the course-based enrollment rules for the FET Platform.
It deliberately avoids framework-specific web objects and raises domain errors
instead of returning HTTP responses.

Business rules enforced here:
- BR-010: Students enroll in courses; class attendance is not created by
  manually enrolling in every class/session.
- BR-011: Active course enrollment makes a student eligible for future classes.
- BR-012: A course roster is the source of default class eligibility.
- BR-013: New enrollments apply to future classes under that course.
- BR-014: Dropping a course ends future eligibility without deleting history.
- BR-015: Historical records must remain intact when enrollment changes.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from django.core.exceptions import ValidationError as DjangoValidationError

from core.common import ConfigurationError, get_attr, utc_now
from apps.notifications.services.notification_service import notify_student_enrolled


class EnrollmentError(ValueError):
    """Base domain error raised by enrollment workflows."""


class StudentNotFoundError(EnrollmentError):
    """Raised when a student cannot be found for a requested enrollment."""


class CourseNotFoundError(EnrollmentError):
    """Raised when a course cannot be found for a requested enrollment."""


class AlreadyEnrolledError(EnrollmentError):
    """Raised when a student is already active in the course."""


class NotEnrolledError(EnrollmentError):
    """Raised when a student is not currently active in the course."""


class EnrollmentModelLike(Protocol):
    """Minimal shape expected from a Django-like enrollment model."""

    student_id: Any
    course_id: Any
    status: Any
    is_active: Any
    updated_at: Any
    deleted_at: Any
    reason: Any
    active_since: Any
    ended_at: Any

    def save(self) -> Any:
        ...


class StudentModelLike(Protocol):
    id: Any


class CourseModelLike(Protocol):
    id: Any


def _set_active_state(record: EnrollmentModelLike, *, is_active: bool) -> None:
    """Apply the active/inactive flag without deleting historical state."""
    if hasattr(record, "is_active"):
        record.is_active = is_active
    if hasattr(record, "status"):
        record.status = "active" if is_active else "inactive"
    if is_active and hasattr(record, "active_since"):
        record.active_since = utc_now()
    if not is_active and hasattr(record, "ended_at"):
        record.ended_at = utc_now()
    if hasattr(record, "updated_at"):
        record.updated_at = utc_now()


def _is_active_enrollment(record: Any) -> bool:
    if record is None:
        return False

    explicit = get_attr(record, "is_active", "active", "is_current")
    if explicit is not None:
        return bool(explicit)

    status = get_attr(record, "status", "state")
    if status is not None:
        return str(status).lower() in {"active", "enrolled", "current", "approved"}

    return False


def _set_fk_if_target_exists(record: Any, field_name: str, target_id: Any) -> None:
    """Set an optional audit FK only when the supplied actor is a real row."""
    if target_id is None or not hasattr(record, f"{field_name}_id"):
        return
    try:
        field = record._meta.get_field(field_name)
        normalized_id = field.target_field.to_python(target_id)
        if field.remote_field.model.objects.filter(pk=normalized_id).exists():
            setattr(record, f"{field_name}_id", normalized_id)
    except (AttributeError, TypeError, ValueError, DjangoValidationError):
        return


def is_student_enrolled_in_course(
    student_id: Any,
    course_id: Any,
    *,
    EnrollmentModel: type[EnrollmentModelLike],
) -> bool:
    """Return whether the student currently holds an active course enrollment.

    This is the core enrollment state used when deciding class eligibility.
    """
    # BR-010, BR-011, BR-013: Enrollment is course-level, and active course
    # enrollment is the source of default eligibility for future classes.
    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")

    queryset = EnrollmentModel.objects.filter(student_id=student_id, course_id=course_id)
    if hasattr(queryset, "order_by"):
        record = queryset.order_by("-updated_at", "-id").first()
    else:
        record = queryset[0] if queryset else None
    return _is_active_enrollment(record)


def get_course_enrollment(
    student_id: Any,
    course_id: Any,
    *,
    EnrollmentModel: type[EnrollmentModelLike],
) -> Optional[EnrollmentModelLike]:
    """Return the most recent enrollment row for the student/course pair."""
    # BR-014, BR-015: historical records are retained; this method reads the
    # most recent record without deleting earlier academic history.
    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")

    queryset = EnrollmentModel.objects.filter(student_id=student_id, course_id=course_id)
    if hasattr(queryset, "order_by"):
        return queryset.order_by("-updated_at", "-id").first()
    return queryset[0] if queryset else None


def enroll_student_in_course(
    student_id: Any,
    course_id: Any,
    *,
    EnrollmentModel: type[EnrollmentModelLike],
    StudentModel: Optional[type[StudentModelLike]] = None,
    CourseModel: Optional[type[CourseModelLike]] = None,
    actor_id: Optional[Any] = None,
    reason: Optional[str] = None,
    authorization_checker: Optional[Any] = None,
) -> EnrollmentModelLike:
    """Create or reactivate a course enrollment for a student.

    This preserves enrollment history and avoids a hard delete. When an inactive
    record already exists, it is reactivated instead of being removed from the
    database.
    """
    # BR-010, BR-011, BR-012, BR-013: Student course enrollment is the sole
    # default trigger for class eligibility; it applies to future classes in the
    # course and is not a per-class manual process.
    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")
    if actor_id is None or authorization_checker is None:
        raise EnrollmentError("An authorized actor and authorization check are required")
    try:
        authorized = authorization_checker(
            actor_id=actor_id,
            student_id=student_id,
            course_id=course_id,
            action="enroll",
        )
    except TypeError:
        authorized = authorization_checker(actor_id, student_id, course_id, "enroll")
    if not bool(authorized):
        raise EnrollmentError("Actor is not authorized to enroll this student")

    if StudentModel is not None:
        try:
            if not StudentModel.objects.filter(id=student_id).exists():
                raise StudentNotFoundError(f"Student {student_id} does not exist")
        except AttributeError as exc:  # pragma: no cover - model implementation may differ
            raise StudentNotFoundError(f"Student {student_id} does not exist") from exc

    if CourseModel is not None:
        try:
            if not CourseModel.objects.filter(id=course_id).exists():
                raise CourseNotFoundError(f"Course {course_id} does not exist")
        except AttributeError as exc:  # pragma: no cover - model implementation may differ
            raise CourseNotFoundError(f"Course {course_id} does not exist") from exc

    record = get_course_enrollment(student_id, course_id, EnrollmentModel=EnrollmentModel)
    if record is not None and _is_active_enrollment(record):
        raise AlreadyEnrolledError(f"Student {student_id} is already enrolled in course {course_id}")

    if record is None:
        record = EnrollmentModel()
        if hasattr(record, "student_id"):
            record.student_id = student_id
        if hasattr(record, "course_id"):
            record.course_id = course_id

    if hasattr(record, "student_id"):
        record.student_id = student_id
    if hasattr(record, "course_id"):
        record.course_id = course_id
    _set_fk_if_target_exists(record, "enrolled_by", actor_id)
    if reason is not None and hasattr(record, "reason"):
        record.reason = reason

    _set_active_state(record, is_active=True)
    if hasattr(record, "deleted_at"):
        record.deleted_at = None
    if hasattr(record, "ended_at"):
        record.ended_at = None
    if hasattr(record, "dropped_at"):
        record.dropped_at = None

    record.save()
    # BR §23 + API §45: the enrolled student is the only eligible recipient of
    # their own enrollment event (fires on create *and* on reactivation, which
    # is a genuine enroll action per BR-010/BR-013).
    notify_student_enrolled(student_id=student_id, course_id=course_id)
    return record


def drop_student_from_course(
    student_id: Any,
    course_id: Any,
    *,
    EnrollmentModel: type[EnrollmentModelLike],
    actor_id: Optional[Any] = None,
    reason: Optional[str] = None,
    authorization_checker: Optional[Any] = None,
) -> EnrollmentModelLike:
    """Deactivate a course enrollment without hard-deleting the historical record.

    This ends future eligibility while preserving past academic history and the
    enrollment trail for later audits.
    """
    # BR-014, BR-015: dropping a course removes future eligibility but must not
    # delete prior attendance/assessment/project records or the enrollment trail.
    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")
    if actor_id is None or authorization_checker is None:
        raise EnrollmentError("An authorized actor and authorization check are required")
    try:
        authorized = authorization_checker(
            actor_id=actor_id,
            student_id=student_id,
            course_id=course_id,
            action="drop",
        )
    except TypeError:
        authorized = authorization_checker(actor_id, student_id, course_id, "drop")
    if not bool(authorized):
        raise EnrollmentError("Actor is not authorized to drop this student")

    record = get_course_enrollment(student_id, course_id, EnrollmentModel=EnrollmentModel)
    if record is None or not _is_active_enrollment(record):
        raise NotEnrolledError(f"Student {student_id} is not enrolled in course {course_id}")

    _set_fk_if_target_exists(record, "dropped_by", actor_id)
    if reason is not None and hasattr(record, "reason"):
        record.reason = reason

    _set_active_state(record, is_active=False)
    if hasattr(record, "dropped_at"):
        record.dropped_at = utc_now()
    if hasattr(record, "deleted_at"):
        record.deleted_at = None

    record.save()
    return record


def get_enrolled_students(
    course_id: Any,
    *,
    EnrollmentModel: type[EnrollmentModelLike],
    active_only: bool = True,
) -> list[Any]:
    """Return active or all students for a given course.

    The default is active-only because a course roster is defined by current
    enrollments, while historical rows remain preserved for traceability.
    """
    # BR-010, BR-012, BR-014, BR-015: the course roster is determined by
    # active enrollment, but older records are retained for traceability.
    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")

    queryset = EnrollmentModel.objects.filter(course_id=course_id)
    if active_only:
        rows = []
        for record in queryset:
            if _is_active_enrollment(record):
                rows.append(record)
        return rows

    return list(queryset)
