"""Server-owned course-offering discovery and self-registration rules."""

from django.db import transaction
from django.utils import timezone

from core.audit import write_audit_entry

from ..models import CourseOffering, Enrollment, Semester


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


def _registration_context(student):
    if getattr(student, "role", None) != "STUDENT":
        raise StudentOnlyError("Only students can register for courses.")
    if not student.department_id or not str(getattr(student, "level", "")).strip():
        raise IncompleteProfileError(
            "Your institution-assigned department or level is missing. Contact an administrator."
        )
    semester = Semester.objects.filter(is_current=True).first()
    if semester is None:
        raise NoActiveSemesterError("No active semester is available for registration.")
    today = timezone.localdate()
    if semester.registration_deadline and today > semester.registration_deadline:
        raise RegistrationClosedError("Course registration has closed for this semester.")
    return semester, today


def eligible_offerings(student):
    semester, today = _registration_context(student)
    queryset = CourseOffering.objects.filter(
        semester=semester,
        department_id=student.department_id,
        course__department_id=student.department_id,
        course__level=student.level,
        course__status="ACTIVE",
        status="ACTIVE",
    ).select_related("course", "department", "semester", "lecturer")
    rows = [
        offering for offering in queryset
        if offering.registration_deadline is None or today <= offering.registration_deadline
    ]
    return semester, rows


@transaction.atomic
def register_student(*, student, offering_ids):
    semester, available = eligible_offerings(student)
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
