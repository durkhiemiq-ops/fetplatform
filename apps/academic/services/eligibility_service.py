"""Class eligibility service.

This module determines whether a student is eligible for a given class or
attendance session. Eligibility is never granted manually: it is always derived
from an active course enrollment, which is the single source of truth for the
default class roster.

It deliberately avoids framework-specific web objects and raises domain errors
instead of returning HTTP responses. Views own the HTTP layer; this service only
decides eligibility.

Business rules enforced here:
- BR-011: Active course enrollment automatically makes a student eligible for
  classes under that course.
- BR-012: Lecturers are not required to bulk-enroll students per class; the
  course roster is the default.
- BR-020: A class must belong to a valid course; eligibility checks against
  orphaned/invalid classes are rejected.
- BR-021: A lecturer only manages classes they are assigned to.
- BR-022: A class roster is derived from the applicable course enrollment.
- BR-031: Only a student eligible for the relevant class/course may submit
  attendance.
- BR-070: A student's active course enrollment determines their default access
  to course-related classes and materials.
- BR-071: A student may only access materials for classes they are eligible for
  (``is_student_eligible_for_class`` is the check ``file_service`` calls).
- BR-072: A lecturer may only manage courses/classes they are assigned to,
  unless they hold broader administrative authorization.

"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from core.common import ConfigurationError, get_attr
from core.academic_access import (
    ROLE_ACADEMIC_STAFF,
    ROLE_LECTURER,
    ROLE_STAFF,
    is_admin_user,
    normalize_role,
)
from .enrollment_service import (
    get_enrolled_students,
    is_student_enrolled_in_course,
)


class EligibilityError(ValueError):
    """Base domain error raised by eligibility workflows."""


class ClassNotFoundError(EligibilityError):
    """Raised when a class cannot be resolved for an eligibility check."""


class CourseNotResolvedError(EligibilityError):
    """Raised when the course backing a class/session cannot be determined."""


class ClassLike(Protocol):
    """Minimal shape expected from a Django-like class model."""

    id: Any
    course_id: Any


class AttendanceSessionLike(Protocol):
    """Minimal shape expected from a Django-like attendance session model."""

    id: Any
    course_id: Any
    class_id: Any
    status: Any
    is_active: Any


class EnrollmentModelLike(Protocol):
    """Minimal shape expected from a Django-like enrollment model."""

    student_id: Any
    course_id: Any
    status: Any
    is_active: Any


def _resolve_class_record(
    class_id: Any,
    *,
    ClassModel: Optional[type[ClassLike]],
) -> Optional[ClassLike]:
    if ClassModel is None or class_id is None:
        return None
    if not hasattr(ClassModel, "objects"):
        return None
    queryset = ClassModel.objects.filter(id=class_id)
    if hasattr(queryset, "first"):
        return queryset.first()
    return queryset[0] if queryset else None


def _resolve_course_id(
    *,
    session: Optional[AttendanceSessionLike] = None,
    class_id: Optional[Any] = None,
    ClassModel: Optional[type[ClassLike]] = None,
    course_id: Optional[Any] = None,
) -> Any:
    """Determine the course on which eligibility depends.

    The course can be discovered from an active attendance session, from the
    class record, or supplied directly by the caller.
    """

    session_course = get_attr(session, "course_id", "course")
    session_class = get_attr(session, "class_id", "class")
    requested_class_id = class_id if class_id is not None else session_class
    class_record = None
    if requested_class_id is not None:
        class_record = _resolve_class_record(
            requested_class_id,
            ClassModel=ClassModel,
        )
        if class_record is None:
            raise ClassNotFoundError(f"Class {requested_class_id} was not found")
        class_course = get_attr(class_record, "course_id", "course")
        if class_course is None:
            raise CourseNotResolvedError(
                f"Class {requested_class_id} is not attached to a course"
            )
        if session_course is not None and str(session_course) != str(class_course):
            raise CourseNotResolvedError(
                "Attendance session class does not belong to its course"
            )
        if course_id is not None and str(course_id) != str(class_course):
            raise CourseNotResolvedError(
                "Requested class does not belong to the requested course"
            )
        return class_course

    if course_id is not None:
        if CourseModel is not None and hasattr(CourseModel, "objects"):
            queryset = CourseModel.objects.filter(id=course_id)
            exists = queryset.exists() if hasattr(queryset, "exists") else bool(queryset)
            if not exists:
                raise CourseNotResolvedError(
                    f"Course {course_id} was not found"
                )
        return course_id

    if session_course is not None:
        return session_course

    raise CourseNotResolvedError(
        "Could not determine the course behind the requested class/session"
    )


def can_lecturer_manage_class(
    lecturer: Any,
    *,
    class_id: Any = None,
    course_id: Any = None,
    assigned_class_ids: Optional[Any] = None,
    assigned_course_ids: Optional[Any] = None,
) -> bool:
    """Return whether a lecturer has server-side assignment for a class/course."""
    # BR-021, BR-072: lecturers may manage only assigned academic scopes;
    # administrators may use broader authorization from their stored role.
    if lecturer is None:
        return False
    role = normalize_role(get_attr(lecturer, "role", "account_role"))
    if is_admin_user(lecturer) or bool(get_attr(lecturer, "is_administrator")):
        return True
    if role not in {ROLE_LECTURER, ROLE_ACADEMIC_STAFF, ROLE_STAFF}:
        return False

    classes = set(assigned_class_ids or get_attr(lecturer, "class_ids") or [])
    courses = set(assigned_course_ids or get_attr(lecturer, "course_ids") or [])
    if class_id is not None:
        return class_id in classes
    if course_id is not None:
        return course_id in courses
    return False


def _check_enrollment(
    student_id: Any,
    course_id: Any,
    *,
    EnrollmentModel: Optional[type[EnrollmentModelLike]],
    enrollment_checker: Optional[Any],
) -> bool:
    if enrollment_checker is not None:
        try:
            return bool(
                enrollment_checker(student_id=student_id, course_id=course_id)
            )
        except TypeError:
            return bool(enrollment_checker(student_id, course_id))

    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel or enrollment_checker is required")

    # BR-011, BR-070: eligibility is derived from an active course enrollment.
    return is_student_enrolled_in_course(
        student_id,
        course_id,
        EnrollmentModel=EnrollmentModel,
    )


def is_student_eligible_for_class(
    student_id: Any,
    session: Optional[AttendanceSessionLike] = None,
    class_id: Optional[Any] = None,
    *,
    ClassModel: Optional[type[ClassLike]] = None,
    CourseModel: Optional[type[Any]] = None,
    EnrollmentModel: Optional[type[EnrollmentModelLike]] = None,
    enrollment_checker: Optional[Any] = None,
    course_id: Optional[Any] = None,
) -> bool:
    """Return whether a student is eligible for a class or attendance session.

    Eligibility is never manual: it is resolved from the course that the class
    or session belongs to and whether the student holds an active enrollment in
    that course. This function is designed to be usable directly as the
    ``eligibility_checker`` dependency of the attendance service.
    """

    if student_id is None:
        raise EligibilityError("Student id is required")

    # BR-011, BR-070: course enrollment is the only default trigger for class
    # eligibility; the course behind the class has to be resolved first.
    resolved_course = _resolve_course_id(
        session=session,
        class_id=class_id,
        ClassModel=ClassModel,
        course_id=course_id,
    )

    # BR-031, BR-022: only students with active enrollment in the relevant
    # course are eligible; the roster is derived from enrollment, never a manual
    # per-class list.
    return _check_enrollment(
        student_id,
        resolved_course,
        EnrollmentModel=EnrollmentModel,
        enrollment_checker=enrollment_checker,
    )


def get_eligible_students(
    course_id: Optional[Any] = None,
    session: Optional[AttendanceSessionLike] = None,
    class_id: Optional[Any] = None,
    *,
    ClassModel: Optional[type[ClassLike]] = None,
    CourseModel: Optional[type[Any]] = None,
    EnrollmentModel: type[EnrollmentModelLike],
) -> list[Any]:
    """Return the students eligible for a course, class, or attendance session.

    The list is always derived from active course enrollments, so there is no
    need to maintain a duplicate per-class student roster.
    """

    if EnrollmentModel is None:
        raise ConfigurationError("EnrollmentModel is required")

    resolved_course = _resolve_course_id(
        session=session,
        class_id=class_id,
        ClassModel=ClassModel,
        course_id=course_id,
    )

    # BR-011, BR-012, BR-022: the class roster is derived from applicable course
    # enrollment; active enrollments are the source of default eligibility.
    return get_enrolled_students(
        resolved_course,
        EnrollmentModel=EnrollmentModel,
        active_only=True,
    )