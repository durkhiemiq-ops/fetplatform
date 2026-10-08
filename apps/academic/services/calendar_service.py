"""Transactional academic-calendar state changes."""

from django.db import IntegrityError, transaction

from core.audit import write_audit_entry

from ..models import Semester


class SemesterCalendarError(ValueError):
    pass


class SemesterNotFoundError(SemesterCalendarError):
    pass


class SemesterActivationConflictError(SemesterCalendarError):
    pass


def _audit_value(semester):
    return {
        "id": str(semester.pk),
        "school_year": str(semester.school_year_id),
        "name": semester.name,
        "start_date": semester.start_date,
        "end_date": semester.end_date,
        "registration_deadline": semester.registration_deadline,
        "status": semester.status,
        "is_current": semester.is_current,
    }


@transaction.atomic
def create_semester(*, data, actor_id):
    """Create a semester and safely honor an initial current-semester request."""
    values = dict(data)
    activate_requested = values.pop("is_current", False)
    semester = Semester.objects.create(**values, is_current=False)
    write_audit_entry(
        action="semester_created",
        resource_type="semester",
        resource_id=semester.pk,
        actor_id=actor_id,
        new_value=_audit_value(semester),
    )
    if activate_requested:
        semester = activate_semester(semester_id=semester.pk, actor_id=actor_id)
    return semester


@transaction.atomic
def update_semester(*, semester_id, changes, actor_id):
    """Update calendar fields, routing activation through the locked transition."""
    semester = Semester.objects.select_for_update().filter(pk=semester_id).first()
    if semester is None:
        raise SemesterNotFoundError("Semester not found.")

    old_value = _audit_value(semester)
    values = dict(changes)
    current_change = values.pop("is_current", None)
    for field, value in values.items():
        setattr(semester, field, value)
    if current_change is False:
        semester.is_current = False
    update_fields = [*values]
    if current_change is False:
        update_fields.append("is_current")
    if update_fields:
        semester.save(update_fields=update_fields)

    if current_change is True:
        semester = activate_semester(semester_id=semester.pk, actor_id=actor_id)

    write_audit_entry(
        action="semester_updated",
        resource_type="semester",
        resource_id=semester.pk,
        actor_id=actor_id,
        details={"changed_fields": sorted(changes)},
        old_value=old_value,
        new_value=_audit_value(semester),
    )
    return semester


def activate_semester(*, semester_id, actor_id):
    """Make one semester current and audit every displaced current semester.

    Row locks serialize updates to existing current rows. The partial unique
    constraint on Semester.is_current is the final guard when concurrent
    transactions start while no row is current.
    """
    try:
        with transaction.atomic():
            target = Semester.objects.select_for_update().filter(pk=semester_id).first()
            if target is None:
                raise SemesterNotFoundError("Semester not found.")

            previous = list(
                Semester.objects.select_for_update()
                .filter(is_current=True)
                .exclude(pk=target.pk)
            )
            if target.is_current and not previous and target.status == "ACTIVE":
                return target

            old_value = {
                "is_current": target.is_current,
                "status": target.status,
                "displaced_semester_ids": [str(row.pk) for row in previous],
            }
            if previous:
                Semester.objects.filter(pk__in=[row.pk for row in previous]).update(
                    is_current=False
                )
            target.is_current = True
            target.status = "ACTIVE"
            target.save(update_fields=["is_current", "status"])

            write_audit_entry(
                action="semester_activated",
                resource_type="semester",
                resource_id=target.pk,
                actor_id=actor_id,
                old_value=old_value,
                new_value={"is_current": True, "status": target.status},
            )
            return target
    except IntegrityError as exc:
        raise SemesterActivationConflictError(
            "Another semester activation completed concurrently. Reload and try again."
        ) from exc
