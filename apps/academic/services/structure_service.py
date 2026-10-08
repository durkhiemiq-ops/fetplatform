"""State-changing academic structure operations."""

from django.db import IntegrityError, transaction

from core.academic_access import is_admin_user, is_authorized_academic_user
from core.audit import write_audit_entry

from ..models import ClassSchedule, CourseOffering, Department, SchoolYear


class AcademicStructureError(ValueError):
    pass


class AcademicStructureAuthorizationError(AcademicStructureError):
    pass


class AcademicStructureConflictError(AcademicStructureError):
    pass


@transaction.atomic
def create_school_year(*, actor, data):
    """Create an academic year and its required audit record atomically."""
    if not is_admin_user(actor):
        raise AcademicStructureAuthorizationError(
            "Only administrators manage school years."
        )
    year = SchoolYear.objects.create(**dict(data))
    write_audit_entry(
        action="school_year_created",
        resource_type="school_year",
        resource_id=year.pk,
        actor_id=actor.pk,
        new_value={
            "name": year.name,
            "start_date": year.start_date,
            "end_date": year.end_date,
        },
    )
    return year


@transaction.atomic
def create_course_offering(*, actor, data):
    """Create an offering and its BR-210 audit record in one transaction."""
    if not is_admin_user(actor):
        raise AcademicStructureAuthorizationError(
            "Only administrators create offerings."
        )
    offering = CourseOffering.objects.create(**dict(data))
    write_audit_entry(
        action="course_offering_created",
        resource_type="course_offering",
        resource_id=offering.pk,
        actor_id=actor.pk,
        details={
            "course_id": str(offering.course_id),
            "semester_id": str(offering.semester_id),
        },
    )
    return offering


@transaction.atomic
def update_course_offering(*, actor, offering, changes):
    """Persist an offering edit only if its audit entry can also be stored."""
    if not is_admin_user(actor):
        raise AcademicStructureAuthorizationError(
            "Only administrators update offerings."
        )
    changed_fields = sorted(changes)
    for field, value in changes.items():
        setattr(offering, field, value)
    if changed_fields:
        offering.save(update_fields=[*changed_fields, "updated_at"])
    write_audit_entry(
        action="course_offering_updated",
        resource_type="course_offering",
        resource_id=offering.pk,
        actor_id=actor.pk,
        details={"changed_fields": changed_fields},
    )
    return offering


@transaction.atomic
def create_department(*, actor, name, code, faculty):
    """Create and audit a department through an administrator-only path."""
    if not is_admin_user(actor):
        raise AcademicStructureAuthorizationError(
            "Only administrators create departments."
        )
    clean_name = str(name or "").strip()
    clean_code = str(code or "").strip().upper()
    if not clean_name or not clean_code or faculty is None:
        raise AcademicStructureError("Name, code, and faculty are required.")
    try:
        department = Department.objects.create(
            name=clean_name,
            code=clean_code,
            faculty=faculty,
        )
    except IntegrityError as exc:
        raise AcademicStructureConflictError(
            "A department with this code already exists."
        ) from exc
    write_audit_entry(
        action="department_created",
        resource_type="department",
        resource_id=department.pk,
        actor_id=actor.pk,
        new_value={
            "name": department.name,
            "code": department.code,
            "faculty_id": str(department.faculty_id),
        },
    )
    return department


def _can_manage_offering(actor, offering):
    return (
        is_authorized_academic_user(actor)
        and (
            is_admin_user(actor)
            or str(offering.lecturer_id) == str(getattr(actor, "pk", ""))
        )
    )


def _lock_managed_offering(actor, offering, *, denial_message):
    """Lock an offering and confirm ``actor`` may write to it.

    Shared by both class-writing surfaces so the scope rule has one
    definition: the caller must pass the central authorization gate
    (:func:`core.academic_access.is_authorized_academic_user`, which is where a
    PENDING/REJECTED lecturer is refused) *and* own the offering, or be an
    administrator. The offering row is locked so two concurrent class writes
    against it serialise instead of interleaving.

    The offering itself is resolved from the caller-scoped queryset in the
    view first, so an unrelated caller never reaches this function: they get
    the same 404 an unknown id produces.
    """
    if offering is None:
        raise AcademicStructureError("Course offering is required.")
    try:
        # Lock the offering row alone. `select_related("lecturer")` cannot be
        # combined with FOR UPDATE here: `CourseOffering.lecturer` is nullable,
        # so the join is a LEFT OUTER JOIN and PostgreSQL refuses
        # "FOR UPDATE cannot be applied to the nullable side of an outer join"
        # (SQLite silently allows it, which is why this only shows up against
        # the real database). The lecturer is read straight afterwards, which
        # the ORM fetches in a second query — it does not need to be locked,
        # only the offering row that serialises concurrent class writes.
        offering = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    except CourseOffering.DoesNotExist as exc:
        raise AcademicStructureError("Course offering does not exist.") from exc
    if not _can_manage_offering(actor, offering):
        raise AcademicStructureAuthorizationError(denial_message)
    lecturer = offering.lecturer
    if lecturer is None or not is_authorized_academic_user(lecturer):
        # No new bypass for a legacy NULL assignment: the offering still has
        # to name an authorized lecturer, exactly as the timetable path does.
        raise AcademicStructureError(
            "The course offering must have an authorized lecturer."
        )
    return offering, lecturer


def _assert_no_schedule_conflict(offering, values):
    """Refuse a weekly slot that overlaps one already on this offering."""
    conflict = ClassSchedule.objects.filter(
        course_offering=offering,
        day_of_week=values["day_of_week"],
        is_active=True,
        start_time__lt=values["end_time"],
        end_time__gt=values["start_time"],
    ).exists()
    if conflict:
        raise AcademicStructureConflictError(
            "This course offering already has an overlapping timetable slot."
        )


@transaction.atomic
def create_class_schedule(*, actor, offering, data):
    """Create one conflict-free weekly slot for an assigned offering."""
    offering, lecturer = _lock_managed_offering(
        actor,
        offering,
        denial_message=(
            "Only the assigned lecturer or an administrator may manage this timetable."
        ),
    )

    values = dict(data)
    _assert_no_schedule_conflict(offering, values)

    schedule = ClassSchedule.objects.create(
        course_offering=offering,
        lecturer=lecturer,
        is_active=True,
        **values,
    )
    write_audit_entry(
        action="class_schedule_created",
        resource_type="class_schedule",
        resource_id=schedule.pk,
        actor_id=actor.pk,
        details={"course_offering_id": str(offering.pk)},
    )
    return schedule


@transaction.atomic
def create_class_definition(*, actor, offering, data):
    """Create a class definition under an authorized offering (API §22).

    Accepted project decision A: this is the meaning of the lecturer's
    "Create class" action — an academic class definition belonging to an
    existing course offering, not a new course, offering, enrollment list or
    student workspace. Eligibility stays derived from active enrollment in the
    offering (BR-011/BR-022), so nothing here copies a roster.

    The weekly slot is optional: ``day_of_week``/``start_time``/``end_time``
    are accepted only when supplied, and then only as a complete triple. There
    is deliberately no name-uniqueness rule — repeated lecture/tutorial
    definitions under one offering are legitimate — and no recurrence parser.
    """
    offering, lecturer = _lock_managed_offering(
        actor,
        offering,
        denial_message=(
            "Only the assigned lecturer or an administrator may create a class "
            "for this course offering."
        ),
    )

    values = dict(data)
    name = str(values.pop("name", "") or "").strip()
    if not name:
        raise AcademicStructureError("name is required.")
    if len(name) > 255:
        raise AcademicStructureError("name must be 255 characters or fewer.")

    class_type = str(values.get("class_type") or ClassSchedule.ClassType.LECTURE)
    if class_type not in ClassSchedule.ClassType.values:
        raise AcademicStructureError("class_type is not a supported class type.")
    location = str(values.get("location") or "").strip()
    if len(location) > 255:
        raise AcademicStructureError("location must be 255 characters or fewer.")

    slot_keys = ("day_of_week", "start_time", "end_time")
    supplied = {key: values.get(key) for key in slot_keys}
    given = [key for key in slot_keys if supplied[key] is not None]
    if given and len(given) != len(slot_keys):
        raise AcademicStructureError(
            "day_of_week, start_time and end_time must be supplied together."
        )
    if given:
        _assert_no_schedule_conflict(offering, supplied)

    class_definition = ClassSchedule.objects.create(
        course_offering=offering,
        lecturer=lecturer,
        is_active=True,
        name=name,
        class_type=class_type,
        location=location,
        **supplied,
    )
    write_audit_entry(
        action="class_definition_created",
        resource_type="class_definition",
        resource_id=class_definition.pk,
        actor_id=actor.pk,
        details={
            "course_offering_id": str(offering.pk),
            "class_type": class_definition.class_type,
            "scheduled": bool(given),
        },
    )
    return class_definition


@transaction.atomic
def archive_class_schedule(*, actor, schedule):
    """Deactivate a timetable slot while preserving its academic history."""
    if schedule is None:
        raise AcademicStructureError("Class schedule is required.")
    try:
        # Lock only the schedule row: the related chain ends in the nullable
        # `CourseOffering.lecturer`, so a joined FOR UPDATE is rejected by
        # PostgreSQL (see `_lock_managed_offering`). The offering and its
        # lecturer are read by the ORM straight after, unlocked.
        schedule = ClassSchedule.objects.select_for_update().get(pk=schedule.pk)
    except ClassSchedule.DoesNotExist as exc:
        raise AcademicStructureError("Class schedule does not exist.") from exc
    if not _can_manage_offering(actor, schedule.course_offering):
        raise AcademicStructureAuthorizationError(
            "Only the assigned lecturer or an administrator may manage this timetable."
        )
    if schedule.is_active:
        schedule.is_active = False
        schedule.save(update_fields=["is_active", "updated_at"])
        write_audit_entry(
            action="class_schedule_archived",
            resource_type="class_schedule",
            resource_id=schedule.pk,
            actor_id=actor.pk,
            details={"course_offering_id": str(schedule.course_offering_id)},
        )
    return schedule
