"""Institution-owned curriculum configuration and atomic student completion."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.academic_access import is_admin_user
from core.audit import write_audit_entry
from apps.notifications.services.notification_service import notify_student_enrolled

from ..models import (
    AcademicTerm, Programme, ProgrammeLevel, Specialization, Curriculum,
    CurriculumCourse, StudentAcademicProfile, CurriculumRegistration,
    Semester, CourseOffering, Enrollment,
)


class CurriculumError(ValueError):
    def __init__(self, message, *, code="CURRICULUM_CONFIGURATION_ERROR", status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def _deny():
    raise CurriculumError("You do not have permission to perform this action.", code="FORBIDDEN", status=403)


def _admin(actor):
    if not actor or not actor.is_authenticated or not is_admin_user(actor):
        _deny()


def _audit(actor, action, obj, **details):
    write_audit_entry(
        action=action, resource_type=obj._meta.model_name,
        resource_id=obj.pk, actor_id=actor.pk, details=details,
    )


def _notify_after_commit(student_id, course_id):
    # A named callback is required by Django's robust-callback error logging.
    def deliver():
        notify_student_enrolled(student_id=student_id, course_id=course_id)

    transaction.on_commit(deliver, robust=True)


def _validate_requirement(row):
    curriculum = row.curriculum
    programme = curriculum.programme
    if row.programme_level.programme_id != programme.pk:
        raise CurriculumError("The requirement level belongs to another programme.")
    if row.course.department_id != programme.department_id or row.course.level != row.programme_level.code:
        raise CurriculumError("The required course must match the programme department and configured level.")
    if row.specialization_id and row.specialization.programme_id != programme.pk:
        raise CurriculumError("The specialization belongs to another programme.")
    if row.classification == CurriculumCourse.Classification.ELECTIVE and row.is_required:
        raise CurriculumError("Electives must be optional; elective selection is not configured.")
    if row.classification == CurriculumCourse.Classification.PROGRAMME_CORE and row.specialization_id:
        raise CurriculumError("Programme core courses apply without a specialization.")
    if row.classification == CurriculumCourse.Classification.SPECIALIZATION_CORE and not row.specialization_id:
        raise CurriculumError("Specialization core courses require a specialization.")


# This is a fixed service allow-list, not a model/field name supplied by a client.
CONFIG_RESOURCES = {
    "programmes": (Programme, {"department", "code", "name", "is_active"}),
    "levels": (ProgrammeLevel, {"programme", "code", "name", "specialization_required"}),
    "terms": (AcademicTerm, {"code", "name"}),
    "specializations": (Specialization, {"programme", "code", "name", "is_active"}),
    "curricula": (Curriculum, {"programme", "version", "cohort_from", "cohort_to"}),
    "requirements": (CurriculumCourse, {
        "curriculum", "programme_level", "academic_term", "course",
        "specialization", "classification", "is_required",
    }),
    "profiles": (StudentAcademicProfile, {"student", "programme", "programme_level", "cohort"}),
}


@transaction.atomic
def create_configuration(*, actor, resource, data):
    _admin(actor)
    if resource not in CONFIG_RESOURCES:
        raise CurriculumError("Configuration resource not found.", code="NOT_FOUND", status=404)
    model, allowed = CONFIG_RESOURCES[resource]
    if set(data) - allowed:
        raise CurriculumError("Unknown or server-owned configuration fields.", code="INVALID_INPUT")
    values = dict(data)
    if resource == "requirements":
        curriculum = Curriculum.objects.select_for_update().get(pk=values["curriculum"].pk)
        if curriculum.is_published:
            raise CurriculumError("Published curricula are immutable. Create a new version.", code="CURRICULUM_FROZEN", status=409)
        values["curriculum"] = curriculum
    if resource == "profiles":
        student = get_user_model().objects.select_for_update().get(pk=values["student"].pk)
        programme = values["programme"]
        if student.role != "STUDENT" or not student.is_active:
            raise CurriculumError("Academic profiles require an active student.")
        if student.department_id != programme.department_id:
            raise CurriculumError("Student department does not match the programme.")
        if values["programme_level"].programme_id != programme.pk:
            raise CurriculumError("The assigned academic level must belong to the student's programme.")
        values["student"] = student
    obj = model(**values)
    if resource == "requirements":
        _validate_requirement(obj)
    try:
        obj.full_clean()
        with transaction.atomic():
            obj.save()
    except (ValidationError, IntegrityError) as exc:
        raise CurriculumError("Configuration is invalid or conflicts with an existing record.", code="INVALID_CONFIGURATION") from exc
    _audit(actor, "curriculum_configuration_created", obj, resource=resource)
    return obj


@transaction.atomic
def publish_curriculum(*, actor, curriculum_id):
    _admin(actor)
    preliminary = Curriculum.objects.filter(pk=curriculum_id).first()
    if preliminary is None:
        raise CurriculumError("Curriculum not found.", code="NOT_FOUND", status=404)
    # The programme lock serializes cohort overlap checks and version resolution.
    Programme.objects.select_for_update().get(pk=preliminary.programme_id)
    curriculum = Curriculum.objects.select_for_update().get(pk=curriculum_id)
    if curriculum.is_published:
        return curriculum
    if Curriculum.objects.filter(
        programme=curriculum.programme, is_published=True,
        cohort_from__lte=curriculum.cohort_to, cohort_to__gte=curriculum.cohort_from,
    ).exclude(pk=curriculum.pk).exists():
        raise CurriculumError("Published curriculum cohort ranges cannot overlap.", code="COHORT_CONFLICT", status=409)
    rows = list(curriculum.requirements.select_related(
        "programme_level", "course", "specialization", "curriculum__programme",
    ))
    if not rows or not any(row.is_required for row in rows):
        raise CurriculumError("A curriculum needs required courses before publication.")
    for row in rows:
        _validate_requirement(row)
    curriculum.is_published = True
    curriculum.published_at = timezone.now()
    curriculum.save(update_fields=["is_published", "published_at"])
    _audit(actor, "curriculum_published", curriculum, version=curriculum.version)
    return curriculum


@transaction.atomic
def assign_semester_term(*, actor, semester_id, academic_term):
    _admin(actor)
    semester = Semester.objects.select_for_update().filter(pk=semester_id).first()
    if semester is None:
        raise CurriculumError("Semester not found.", code="NOT_FOUND", status=404)
    if semester.academic_term_id == academic_term.pk:
        return semester
    if semester.curriculum_registrations.exists():
        raise CurriculumError("A registered semester's curriculum term is locked.", code="TERM_LOCKED", status=409)
    previous = semester.academic_term_id
    # Avoid Semester.save's unrelated current-semester switching behavior.
    Semester.objects.filter(pk=semester.pk).update(academic_term=academic_term)
    semester.academic_term = academic_term
    _audit(actor, "semester_curriculum_term_assigned", semester, previous_term=previous, academic_term=academic_term.pk)
    return semester


_UNSET = object()


def _principal(actor, *, lock=False):
    if not actor or not actor.is_authenticated:
        _deny()
    student = get_user_model().objects.get(pk=actor.pk)
    if student.role != "STUDENT" or not student.is_active:
        _deny()
    profiles = StudentAcademicProfile.objects.all()
    if lock:
        profiles = profiles.select_for_update()
    profile = profiles.filter(student=student).first()
    if profile is None:
        raise CurriculumError("Your academic programme and cohort must be assigned by an administrator.", code="INCOMPLETE_ACADEMIC_PROFILE")
    semester = Semester.objects.filter(is_current=True).first()
    if semester is None:
        raise CurriculumError("No current semester is configured.", code="NO_ACTIVE_SEMESTER")
    return student, profile, semester


def _stored_registration(principal, specialization=_UNSET):
    _, profile, semester = principal
    registration = CurriculumRegistration.objects.filter(profile=profile, semester=semester).first()
    if registration is None:
        return None
    if specialization is not _UNSET:
        selected_id = str(specialization) if specialization is not None else None
        recorded_id = str(registration.specialization_id) if registration.specialization_id else None
        if selected_id is not None and not registration.programme_level.specialization_required:
            raise CurriculumError("Specialization selection is not available at this programme level.", code="SPECIALIZATION_NOT_AVAILABLE")
        if selected_id != recorded_id:
            raise CurriculumError("Changing an existing specialization requires institutional review.", code="SPECIALIZATION_LOCKED", status=409)
    if not registration.summary:
        raise CurriculumError("The completed registration has no stored summary. Contact an administrator.")
    return {**registration.summary, "created_enrollments": []}


def _context(actor, specialization=_UNSET, *, completing=False, principal=None):
    student, profile, semester = principal or _principal(actor)
    programme = Programme.objects.get(pk=profile.programme_id)
    if not programme.is_active or not student.department_id or student.department_id != programme.department_id:
        raise CurriculumError("Your assigned programme and department are inconsistent.", code="INCOMPLETE_ACADEMIC_PROFILE")
    level = ProgrammeLevel.objects.filter(programme=programme, pk=profile.programme_level_id).first()
    if level is None:
        raise CurriculumError("Your institution-assigned level is not configured for this programme.", code="INCOMPLETE_ACADEMIC_PROFILE")
    if completing and semester.status != "ACTIVE":
        raise CurriculumError("No active semester is configured.", code="NO_ACTIVE_SEMESTER")
    today = timezone.localdate()
    if semester.academic_term_id is None:
        raise CurriculumError("The current semester has no curriculum term configured.")
    if completing and semester.registration_deadline and today > semester.registration_deadline:
        raise CurriculumError("Registration has closed for this semester.", code="REGISTRATION_CLOSED")
    if profile.curriculum_id:
        curriculum = Curriculum.objects.get(pk=profile.curriculum_id)
    else:
        versions = list(Curriculum.objects.filter(
            programme=programme, is_published=True,
            cohort_from__lte=profile.cohort, cohort_to__gte=profile.cohort,
        )[:2])
        if len(versions) != 1:
            raise CurriculumError("Exactly one published curriculum must apply to your cohort.")
        curriculum = versions[0]
    if (
        curriculum.programme_id != programme.pk or not curriculum.is_published
        or not curriculum.cohort_from <= profile.cohort <= curriculum.cohort_to
    ):
        raise CurriculumError("Your pinned curriculum does not match the institution-assigned profile.")
    if not level.specialization_required and specialization is not _UNSET and specialization is not None:
        raise CurriculumError("Specialization selection is not available at this programme level.", code="SPECIALIZATION_NOT_AVAILABLE")
    options = list(Specialization.objects.filter(programme=programme, is_active=True).order_by("name", "pk")) if level.specialization_required else []
    options_by_id = {str(option.pk): option for option in options}
    if specialization is _UNSET:
        selected_id = str(profile.specialization_id) if profile.specialization_id and level.specialization_required else None
    else:
        selected_id = str(specialization) if specialization is not None else None
        if level.specialization_required and profile.specialization_id and selected_id != str(profile.specialization_id):
            raise CurriculumError("Changing an existing specialization requires institutional review.", code="SPECIALIZATION_LOCKED", status=409)
    selected = options_by_id.get(selected_id) if selected_id else None
    if selected_id and selected is None:
        raise CurriculumError("Select an available specialization for your programme.", code="INVALID_SPECIALIZATION")
    if level.specialization_required and not options:
        raise CurriculumError("No active specialization is configured for this programme.")
    if completing and level.specialization_required and selected is None:
        raise CurriculumError("Choose a specialization to complete registration.", code="SPECIALIZATION_REQUIRED")
    return student, profile, programme, level, semester, curriculum, options, selected


def _required_offerings(*, programme, level, semester, curriculum, selected, completing):
    scope = Q(classification=CurriculumCourse.Classification.PROGRAMME_CORE, specialization__isnull=True)
    if selected is not None:
        scope |= Q(classification=CurriculumCourse.Classification.SPECIALIZATION_CORE, specialization=selected)
    requirements = list(CurriculumCourse.objects.filter(
        scope, curriculum=curriculum, programme_level=level,
        academic_term_id=semester.academic_term_id, is_required=True,
    ).select_related("course", "programme_level", "specialization", "curriculum__programme").order_by("course__code", "pk"))
    if not requirements and (completing or not level.specialization_required or selected):
        raise CurriculumError("No required curriculum courses are configured for your level and term.")
    for requirement in requirements:
        _validate_requirement(requirement)
    course_ids = {requirement.course_id for requirement in requirements}
    offerings_query = CourseOffering.objects.filter(
        semester=semester, course_id__in=course_ids, department=programme.department,
        course__department=programme.department, course__level=level.code,
    )
    if completing:
        offerings_query = offerings_query.filter(course__status="ACTIVE", status="ACTIVE")
    offerings = list(offerings_query.select_related("course").order_by("pk"))
    by_course = {offering.course_id: offering for offering in offerings}
    if set(by_course) != course_ids:
        raise CurriculumError("An active current-semester offering is missing for a required course.", code="REQUIRED_OFFERING_UNAVAILABLE")
    today = timezone.localdate()
    if completing and any(offering.registration_deadline and today > offering.registration_deadline for offering in offerings):
        raise CurriculumError("Registration has closed for a required course.", code="REGISTRATION_CLOSED")
    # Common and specialized requirements may intentionally refer to the same course.
    unique = {}
    for requirement in requirements:
        unique.setdefault(requirement.course_id, (requirement, by_course[requirement.course_id]))
    return list(unique.values())


def _existing_enrollments(student, pairs, *, lock=False):
    rows = Enrollment.objects.filter(
        student=student, course_offering_id__in=[offering.pk for _, offering in pairs],
    )
    if lock:
        rows = rows.select_for_update()
    return {
        row.course_offering_id: row for row in rows
    }


def _is_active(row):
    return row.is_active and row.status == "active" and row.deleted_at is None and row.dropped_at is None


def _state(context, pairs, existing):
    student, profile, programme, level, semester, curriculum, options, selected = context
    registration = CurriculumRegistration.objects.filter(profile=profile, semester=semester).first()
    today = timezone.localdate()
    required = [
        {
            "course": str(requirement.course_id), "course_code": requirement.course.code,
            "course_name": requirement.course.name, "offering": str(offering.pk),
            "classification": requirement.classification,
            "is_enrolled": offering.pk in existing and _is_active(existing[offering.pk]),
            "is_available": offering.status == "ACTIVE" and offering.course.status == "ACTIVE" and (
                offering.registration_deadline is None or today <= offering.registration_deadline
            ),
        }
        for requirement, offering in pairs
    ]
    return {
        "programme": {"id": str(programme.pk), "code": programme.code, "name": programme.name},
        "level": level.code, "cohort": profile.cohort, "department": str(student.department_id),
        "semester": str(semester.pk), "academic_term": str(semester.academic_term_id),
        "registration_deadline": semester.registration_deadline.isoformat() if semester.registration_deadline else None,
        "registration_open": registration is None and semester.status == "ACTIVE" and (
            semester.registration_deadline is None or today <= semester.registration_deadline
        ) and all(item["is_available"] for item in required),
        "curriculum": {"id": str(curriculum.pk), "version": curriculum.version, "is_pinned": bool(profile.curriculum_id)},
        "specialization_required": level.specialization_required,
        "specializations": [{"id": str(option.pk), "code": option.code, "name": option.name} for option in options],
        "specialization": str(selected.pk) if selected else None,
        "required_offerings": required,
        "completed": registration is not None and bool(required) and all(item["is_enrolled"] for item in required),
        "registration": str(registration.pk) if registration else None,
    }


def registration_state(*, actor):
    principal = _principal(actor)
    stored = _stored_registration(principal)
    if stored is not None:
        return stored
    context = _context(actor, principal=principal)
    _, _, programme, level, semester, curriculum, _, selected = context
    pairs = _required_offerings(
        programme=programme, level=level, semester=semester,
        curriculum=curriculum, selected=selected, completing=False,
    )
    return _state(context, pairs, _existing_enrollments(context[0], pairs))


@transaction.atomic
def complete_registration(*, actor, specialization=_UNSET):
    principal = _principal(actor, lock=True)
    stored = _stored_registration(principal, specialization)
    if stored is not None:
        return stored
    context = _context(actor, specialization, completing=True, principal=principal)
    student, profile, programme, level, semester, curriculum, _, selected = context
    pairs = _required_offerings(
        programme=programme, level=level, semester=semester,
        curriculum=curriculum, selected=selected, completing=True,
    )
    existing = _existing_enrollments(student, pairs, lock=True)
    if any(not _is_active(row) or row.course_id != row.course_offering.course_id for row in existing.values()):
        raise CurriculumError("A required enrollment is inactive or inconsistent. Contact an administrator.", code="ENROLLMENT_CONFLICT", status=409)
    registration = CurriculumRegistration.objects.filter(profile=profile, semester=semester).first()
    offering_ids = sorted(str(offering.pk) for _, offering in pairs)
    selected_id = selected.pk if selected else None
    if registration is not None and (
        registration.curriculum_id != curriculum.pk or registration.programme_level_id != level.pk
        or registration.specialization_id != selected_id or sorted(registration.offering_ids) != offering_ids
    ):
        raise CurriculumError("This semester's registration is already pinned to different academic data.", code="REGISTRATION_LOCKED", status=409)
    # All academic configuration, eligibility, history and offering checks finish before writes.
    created_ids = []
    for requirement, offering in pairs:
        row = existing.get(offering.pk)
        if row is None:
            row, created = Enrollment.objects.select_for_update().get_or_create(
                student=student, course_offering=offering,
                defaults={
                    "course": offering.course, "enrolled_by": student,
                    "source": "CURRICULUM", "curriculum_requirement": requirement,
                    "status": "active", "is_active": True,
                },
            )
            if not _is_active(row) or row.course_id != offering.course_id:
                raise CurriculumError("A required enrollment changed during registration.", code="ENROLLMENT_CONFLICT", status=409)
            if created:
                created_ids.append(str(row.pk))
                _audit(student, "curriculum_course_enrolled", row, offering=offering.pk, curriculum=curriculum.pk)
                _notify_after_commit(student.pk, offering.course_id)
            existing[offering.pk] = row
    changed = profile.curriculum_id is None or (selected_id is not None and profile.specialization_id != selected_id)
    if changed:
        profile.curriculum = curriculum
        if selected is not None:
            profile.specialization = selected
        if profile.pinned_at is None:
            profile.pinned_at = timezone.now()
        profile.save(update_fields=["curriculum", "specialization", "pinned_at"])
        _audit(student, "student_curriculum_pinned", profile, curriculum=curriculum.pk, specialization=selected_id)
    if registration is None:
        registration = CurriculumRegistration.objects.create(
            profile=profile, semester=semester, programme_level=level,
            curriculum=curriculum, specialization=selected, offering_ids=offering_ids,
        )
        _audit(student, "curriculum_registration_completed", registration, curriculum=curriculum.pk, offerings=offering_ids)
    result = _state(context, pairs, existing)
    registration.summary = result
    registration.save(update_fields=["summary"])
    result["created_enrollments"] = created_ids
    return result
