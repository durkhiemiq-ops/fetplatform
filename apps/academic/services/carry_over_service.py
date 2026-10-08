"""Carry-over application service.

A carry-over lets a student request a place on an offering they are not
enrolled in (for example repeating a course they failed). The student submits;
a member of staff decides; and **approval is what creates the enrollment**, so
attendance eligibility (BR-030/BR-031) only follows a real review.

Rules enforced here, all at the service layer rather than in the view:

* A student only ever sees and acts on their own applications. The list query
  is scoped by the caller, so there is no id to supply that reaches another
  student's rows.
* Reviewing is staff-only. A student calling the review action is rejected
  before any state changes.
* A decision is single-shot: once an application leaves ``PENDING`` it cannot
  be decided again, so a replayed request cannot re-run approval.
* Approval and enrollment creation happen in one transaction (BR-210): either
  both land or neither does.

Raises domain errors instead of returning HTTP responses, matching the other
services in this package.
"""

from __future__ import annotations

from typing import Any, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.services.notification_service import (
    notify_student_enrolled,
)
from core.audit import write_audit_entry
from core.academic_access import is_authorized_academic_user

from ..models import CarryOverApplication, CourseOffering, Enrollment

STAFF_ROLES = ("LECTURER", "ADMINISTRATOR")


class CarryOverError(ValueError):
    """Base domain error for carry-over workflows."""


class OfferingNotFoundError(CarryOverError):
    """The target offering does not exist (or is not selectable)."""


class ApplicationNotFoundError(CarryOverError):
    """No application with that id is visible to this caller."""


class InvalidDecisionError(CarryOverError):
    """Decision was not APPROVED or REJECTED."""


class NotReviewableError(CarryOverError):
    """The application has already been decided."""


class NotStaffError(CarryOverError):
    """Only teaching/administrative staff may review an application."""


class AlreadyEnrolledError(CarryOverError):
    """The student already holds an active place on that offering."""


class DuplicateApplicationError(CarryOverError):
    """A PENDING application for this student and offering already exists.

    Backed by a conditional unique constraint, so it is the database — not a
    read-then-write check — that makes it race-free.
    """


def is_staff(user) -> bool:
    """Whether ``user`` may act as teaching/administrative staff.

    Role alone is not authority. A lecturer who registered themselves is
    created PENDING and must be approved before acting as staff, so the
    central approval gate is consulted here rather than trusting the role
    label. Administrators are unaffected by that gate.
    """
    if user is None:
        return False
    if getattr(user, "role", None) == "ADMINISTRATOR":
        return True
    return is_authorized_academic_user(user)


def _offering_or_none(offering_id: Any) -> Optional[CourseOffering]:
    return (
        CourseOffering.objects.filter(pk=offering_id)
        .select_related("course", "semester", "department")
        .first()
    )


def list_applications(user, status: Optional[str] = None):
    """Applications visible to ``user``, newest first.

    Students are hard-scoped to their own rows; staff see the whole queue so
    they can review it. Filtering by status happens after the scope, never
    before, so a filter value cannot widen the result set.
    """
    queryset = CarryOverApplication.objects.select_related(
        "student",
        "course_offering__course",
        "reviewed_by",
    )
    if not is_staff(user):
        queryset = queryset.filter(student=user)

    if status:
        queryset = queryset.filter(status__iexact=str(status).strip().upper())
    return queryset


def serialize(application: CarryOverApplication) -> dict:
    student = application.student
    course = application.course_offering.course if application.course_offering else None
    return {
        "id": str(application.pk),
        "student": str(student.pk) if student else None,
        "student_name": f"{student.first_name} {student.last_name}".strip()
        if student
        else None,
        "matricule": getattr(student, "matricule", None),
        "student_email": getattr(student, "email", None),
        "course_offering_id": str(application.course_offering_id),
        "course_code": course.code if course else None,
        "course_title": course.name if course else None,
        "reason": application.reason,
        "status": application.status,
        "review_note": application.review_note,
        "created_at": application.created_at.isoformat()
        if application.created_at
        else None,
        "reviewed_at": application.reviewed_at.isoformat()
        if application.reviewed_at
        else None,
    }


@transaction.atomic
def apply_for_carry_over(*, student, course_offering_id: Any, reason: str = "") -> dict:
    """Submit a carry-over application for the student's own place."""
    offering = _offering_or_none(course_offering_id)
    if offering is None:
        raise OfferingNotFoundError("That course offering does not exist.")

    # Already holding a place: nothing to carry over into.
    already = Enrollment.objects.filter(
        student=student,
        course_offering=offering,
        is_active=True,
        deleted_at__isnull=True,
    ).exists()
    if already:
        raise AlreadyEnrolledError("You are already enrolled in that course.")

    try:
        # Nested atomic so the failed insert rolls back to a savepoint rather
        # than poisoning the outer transaction that is already open.
        with transaction.atomic():
            application = CarryOverApplication.objects.create(
                student=student,
                course_offering=offering,
                reason=reason or "",
            )
    except IntegrityError as exc:
        raise DuplicateApplicationError(
            "You already have an application for that course."
        ) from exc

    write_audit_entry(
        action="carry_over_applied",
        resource_type="carry_over_application",
        resource_id=application.pk,
        actor_id=student.pk,
        details={"course_offering_id": str(offering.pk)},
    )
    return serialize(application)


@transaction.atomic
def review_application(
    *, application: CarryOverApplication, actor, decision: str, note: str = ""
) -> dict:
    """Record a staff decision; approval enrolls the student.

    Both halves are in the same transaction: the enrollment must never exist
    without the approval that justified it, nor the approval without the
    enrollment the page promises ("Approved - the student is now enrolled").
    """
    if not is_staff(actor):
        raise NotStaffError("Only administrators and lecturers may review applications.")

    decision = str(decision or "").strip().upper()
    if decision not in (
        CarryOverApplication.Status.APPROVED,
        CarryOverApplication.Status.REJECTED,
    ):
        raise InvalidDecisionError("Decision must be APPROVED or REJECTED.")

    if application.status != CarryOverApplication.Status.PENDING:
        raise NotReviewableError("This application has already been decided.")

    application.status = decision
    application.review_note = note or ""
    application.reviewed_by = actor
    application.reviewed_at = timezone.now()
    application.save(
        update_fields=["status", "review_note", "reviewed_by", "reviewed_at", "updated_at"]
    )

    enrolled = False
    if decision == CarryOverApplication.Status.APPROVED:
        enrolled = _enroll_on_approval(application=application, actor=actor)

    write_audit_entry(
        action="carry_over_reviewed",
        resource_type="carry_over_application",
        resource_id=application.pk,
        actor_id=actor.pk,
        details={
            "decision": decision,
            "student_id": str(application.student_id),
            "course_offering_id": str(application.course_offering_id),
            "enrolled": enrolled,
        },
    )
    payload = serialize(application)
    payload["enrolled"] = enrolled
    return payload


def _enroll_on_approval(*, application: CarryOverApplication, actor) -> bool:
    """Create (or reactivate) the enrollment this approval authorises.

    Returns True when an active enrollment exists as a result. Re-approval of
    an already-enrolled student is impossible (the application is single-shot),
    but a student who re-enrolled through another route is handled without
    raising, because the approval itself is what matters to the record.
    """
    offering = application.course_offering
    student = application.student

    existing = Enrollment.objects.filter(
        student=student, course_offering=offering
    ).first()

    if existing is not None:
        if existing.is_active and existing.deleted_at is None:
            return True
        existing.is_active = True
        existing.status = "active"
        existing.deleted_at = None
        existing.dropped_at = None
        existing.enrolled_by = actor
        existing.reason = f"Carry-over approved ({application.pk})"
        existing.save(
            update_fields=[
                "is_active",
                "status",
                "deleted_at",
                "dropped_at",
                "enrolled_by",
                "reason",
                "updated_at",
            ]
        )
        record = existing
    else:
        record = Enrollment.objects.create(
            student=student,
            course=offering.course,
            course_offering=offering,
            is_active=True,
            status="active",
            enrolled_by=actor,
            reason=f"Carry-over approved ({application.pk})",
            source="LEGACY",
        )

    write_audit_entry(
        action="course_enrolled",
        resource_type="enrollment",
        resource_id=record.pk,
        actor_id=actor.pk,
        details={
            "course_id": str(offering.course_id),
            "student_id": str(student.pk),
            "source": "carry_over",
        },
    )
    notify_student_enrolled(
        student_id=str(student.pk), course_id=str(offering.course_id)
    )
    return True
