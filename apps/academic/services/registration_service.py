"""Server-owned course-offering discovery and self-registration rules.

The enrollment scope here is NOT whatever the student typed at signup.
Public registration collects a department and level as intake declarations,
but those values are client-supplied, so treating them as academic truth would
let any student post ``level=400`` and inherit 400-level course access (MVP
mandate s10/s12). The single authority is the administrator-owned
``StudentAcademicProfile``; a student without one gets an honest
INCOMPLETE_PROFILE state for authorized setup rather than an invented level.
"""

from typing import NamedTuple

from django.db import transaction
from django.utils import timezone

from core.audit import write_audit_entry

from ..models import (  # noqa: F401 - re-exported for callers that only need models
    CourseOffering,
    Department,
    Enrollment,
    Semester,
    StudentAcademicProfile,
)


class RegistrationError(ValueError):
    code = "REGISTRATION_ERROR"
    status = 400


class StudentOnlyError(RegistrationError):
    code = "FORBIDDEN"
    status = 403


class IncompleteProfileError(RegistrationError):
    code = "INCOMPLETE_PROFILE"


class NoActiveSemesterError(RegistrationError):
    code = "NO_ACTIVE_SEMESTER"


class RegistrationClosedError(RegistrationError):
    code = "REGISTRATION_CLOSED"


class OfferingUnavailableError(RegistrationError):
    code = "OFFERING_UNAVAILABLE"


class AcademicScope(NamedTuple):
    """The official enrollment scope resolved from administrator-owned data."""

    profile: StudentAcademicProfile
    department: Department
    level: str


def academic_scope(student) -> AcademicScope:
    """Resolve a student's official department and level, or refuse honestly.

    Only ``StudentAcademicProfile`` counts: it is written by an administrator
    through the curriculum configuration API, never by a public client.
    """
    profile = (
        StudentAcademicProfile.objects.select_related(
            "programme", "programme__department", "programme_level"
        )
        .filter(student=student)
        .first()
    )
    if profile is None:
        raise IncompleteProfileError(
            "Your academic programme and level must be assigned by an administrator."
        )
    department = profile.programme.department
    level = str(profile.programme_level.code or "").strip()
    if department is None or not level:
        raise IncompleteProfileError(
            "Your academic programme and level must be assigned by an administrator."
        )
    return AcademicScope(profile=profile, department=department, level=level)


def _registration_context(student):
    if getattr(student, "role", None) != "STUDENT":
        raise StudentOnlyError("Only students can register for courses.")
    scope = academic_scope(student)
    semester = Semester.objects.filter(is_current=True).first()
    if semester is None:
        raise NoActiveSemesterError("No active semester is available for registration.")
    today = timezone.localdate()
    if semester.registration_deadline and today > semester.registration_deadline:
        raise RegistrationClosedError("Course registration has closed for this semester.")
    return semester, today, scope


def eligible_offerings(student):
    semester, today, scope = _registration_context(student)
    queryset = CourseOffering.objects.filter(
        semester=semester,
        department_id=scope.department.pk,
        course__department_id=scope.department.pk,
        course__level=scope.level,
        course__status="ACTIVE",
        status="ACTIVE",
    ).select_related("course", "department", "semester", "lecturer")
    rows = [
        offering for offering in queryset
        if offering.registration_deadline is None or today <= offering.registration_deadline
    ]
    return semester, rows, scope


@transaction.atomic
def register_student(*, student, offering_ids):
    semester, available, _scope = eligible_offerings(student)
    available_by_id = {offering.id: offering for offering in available}
    requested = list(offering_ids)
    if any(offering_id not in available_by_id for offering_id in requested):
        raise OfferingUnavailableError(
            "One or more selected offerings are unavailable for your registration scope."
        )

    registered = []
    for offering_id in requested:
        offering = available_by_id[offering_id]
        enrollment, created = Enrollment.objects.select_for_update().get_or_create(
            student=student,
            course_offering=offering,
            defaults={
                "course": offering.course,
                "enrolled_by": student,
                "is_active": True,
                "status": "active",
            },
        )
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.status = "active"
            enrollment.enrolled_by = student
            enrollment.dropped_at = None
            enrollment.dropped_by = None
            enrollment.reason = ""
            enrollment.save(update_fields=[
                "is_active", "status", "enrolled_by", "dropped_at",
                "dropped_by", "reason", "updated_at",
            ])
        registered.append(enrollment)
        if created:
            write_audit_entry(
                action="course_offering_registered",
                resource_type="enrollment",
                resource_id=enrollment.id,
                actor_id=student.id,
                details={
                    "student_id": str(student.id),
                    "offering_id": str(offering.id),
                    "semester_id": str(semester.id),
                },
            )
    return registered
