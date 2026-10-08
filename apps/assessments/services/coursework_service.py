"""Coursework service — assignments, submissions, marks and groups.

This implements the **inferred** coursework contract (see ``models.py`` for
why it is inferred rather than specified). Business rules live here, not in
the views: the views translate HTTP to a call and translate the domain errors
back to the project's error envelope.

The rules this module owns:

* Staff only. Students never reach a coursework write, and the scoping in
  :mod:`coursework_access` returns them an empty offering set on reads too.
* Ownership. Only the lecturer who teaches an offering — or an
  administrator — may create, edit, or delete its coursework. A lecturer
  supplying another lecturer's offering id gets ``OfferingAccessDenied``,
  which the view turns into the same denial shape as an unknown id where the
  object should not be confirmed to exist.
* Attempt limits. ``max_submissions`` caps a student's attempts at an
  assignment. A RETURNED submission is resubmittable and does not count as
  consumed, because returning work is an invitation to submit again.
* Grades are written by staff, never by the submitting student.
* Every state-changing action writes a BR-210 audit entry.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Type

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.notifications.services.notification_service import (
    notify_student_enrolled,
)
from core.audit import write_audit_entry
from core.common import utc_now

from ..models import (
    AssessmentGroup,
    AssessmentMark,
    AssessmentSheet,
    Assignment,
    Submission,
)
from .coursework_access import (
    is_offering_lecturer,
    scoped_offerings,
    scoped_offerings_for_read,
)


class CourseworkError(ValueError):
    """Base domain error for the coursework surface."""


class OfferingNotFoundError(CourseworkError):
    """No offering with that id exists or is visible to the caller."""


class OfferingAccessDenied(CourseworkError):
    """The caller may see the offering but does not teach it."""


class AssignmentNotFoundError(CourseworkError):
    """No assignment with that id is visible to the caller."""


class SubmissionNotFoundError(CourseworkError):
    """No submission with that id is visible to the caller."""


class SheetNotFoundError(CourseworkError):
    """No assessment sheet with that id is visible to the caller."""


class GroupNotFoundError(CourseworkError):
    """No assessment group with that id is visible to the caller."""


class EmptyGroupError(CourseworkError):
    """A bulk release was asked for on a collection holding no sheets.

    Its own class — and therefore its own error code — so the client is told
    *why* the button was refused rather than receiving a generic invalid-input
    message. Not a subclass of ``InvalidInputError`` because ``_handle`` maps
    that to ``INVALID_INPUT``; this one has to reach the envelope as
    ``EMPTY_GROUP``.
    """


class SubmissionLimitError(CourseworkError):
    """The student has already used every permitted attempt."""


class MarkEditForbidden(CourseworkError):
    """The caller can see the mark but may not make this particular change.

    Distinct from the not-found errors on purpose: a student disputing their
    own released mark is looking at a resource they are allowed to see, so
    refusing an illegal field on it is a 403, not a 404. What it must never be
    is a success.
    """


class InvalidInputError(CourseworkError):
    """A field was missing, malformed, or out of range."""


class ExportForbidden(CourseworkError):
    """The caller can see the sheet but is not staff, so may not export it.

    Deliberately not a not-found error. The sheet is already visible to this
    caller — an enrolled student reading a published sheet — so §25's
    identical-denial rule does not apply and there is no existence to protect:
    refusing the export is a genuine 403 on a resource they may legitimately
    read by every other route.
    """


def _coerce_pk(value: Any, not_found: Type[CourseworkError], message: str) -> Any:
    """Return ``value`` as a UUID, or raise the caller's own not-found error.

    The compatibility paths accept a plain string for ``pk`` so a malformed id
    can reach the view and be answered *inside* the project's envelope rather
    than dying at the router. Without this guard the ORM raises
    ``django.core.exceptions.ValidationError`` for such a value, which is
    neither an ``APIException`` nor one of this module's domain errors — the
    custom exception handler has no mapping for it, so a bad id would come back
    as a 500 SERVER_ERROR. Answering with the same not-found shape a missing
    row produces keeps it closed, explicit, and indistinguishable from a
    nonexistent id.
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError, DjangoValidationError):
        raise not_found(message)


def _resolve_offering(user, offering_id, *, for_write: bool = False) -> Any:
    """Return the offering, scoped to what ``user`` may act on.

    Reads use :func:`scoped_offerings_for_read`, so a student reaches the
    coursework of their own enrolled offerings. Writes use
    :func:`scoped_offerings`, which is staff-only — the student path is closed
    before any field of the request is read.

    Whether the id does not exist or simply is not the caller's is deliberately
    indistinguishable in either case: both raise the same message, so a caller
    cannot probe for offerings they are not party to. A malformed id raises the
    same message a third time, for the same reason.
    """
    scope = scoped_offerings(user) if for_write else scoped_offerings_for_read(user)
    offering = scope.filter(
        pk=_coerce_pk(offering_id, OfferingNotFoundError, "That course offering does not exist.")
    ).select_related("course", "semester", "lecturer").first()
    if offering is None:
        raise OfferingNotFoundError("That course offering does not exist.")
    return offering


def _offering_is_enrolled(user, offering) -> bool:
    """Whether ``user`` holds an active enrollment on ``offering``."""
    from apps.academic.models import Enrollment

    return Enrollment.objects.filter(
        student=user,
        course_offering=offering,
        is_active=True,
        deleted_at__isnull=True,
    ).exists()


def _audit(*, action: str, resource_type: str, resource_id: Any, actor_id: Any, **details) -> None:
    write_audit_entry(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        details=details or None,
    )


# Sentinel distinguishing "no bulk latest-submission was supplied" from "the
# bulk lookup found no submission" (None) in ``_serialize_assignment``.
_UNSET = object()


def _serialize_assignment(
    assignment, *, is_staff: bool, student=None, latest_submission=_UNSET
) -> dict:
    # List reads annotate ``submissions_total`` / ``submissions_graded`` and
    # bulk-fetch the student's latest submission (see ``list_assignments``);
    # single-object callers have no annotations, so fall back to queries.
    total = getattr(assignment, "submissions_total", None)
    graded = getattr(assignment, "submissions_graded", None)
    payload = {
        "id": str(assignment.pk),
        "course_offering_id": str(assignment.course_offering_id),
        "title": assignment.title,
        "description": assignment.description,
        "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
        "allow_late": assignment.allow_late,
        "max_submissions": assignment.max_submissions,
        "status": assignment.status,
        "is_past_due": assignment.is_past_due,
        "submissions_count": total if total is not None else assignment.submissions.count(),
        "graded_count": (
            graded
            if graded is not None
            else assignment.submissions.filter(status=Submission.Status.GRADED).count()
        ),
    }
    attachment = assignment.attachment
    if attachment is not None:
        payload["attachment_info"] = {
            "id": str(attachment.pk),
            "original_name": attachment.original_name,
            "size_bytes": attachment.size_bytes,
            "mime_type": attachment.mime_type,
        }
    else:
        payload["attachment_info"] = None

    if student is not None:
        # ``list_assignments`` bulk-fetches the student's latest submission per
        # assignment and passes it in (None = no submission). Any other caller
        # leaves the sentinel, keeping the single lookup.
        if latest_submission is _UNSET:
            latest_submission = _latest_submission(assignment, student)
        payload["my_submission"] = _serialize_submission(latest_submission)
    return payload


def _serialize_submission(submission) -> Optional[dict]:
    if submission is None:
        return None
    return {
        "id": str(submission.pk),
        "assignment_id": str(submission.assignment_id),
        "student": str(submission.student_id),
        "note": submission.note,
        "status": submission.status,
        "grade": submission.grade,
        "feedback": submission.feedback,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else None,
        "graded_at": submission.graded_at.isoformat() if submission.graded_at else None,
        "file": str(submission.file_id) if submission.file_id else None,
    }


def _latest_submission(assignment, student) -> Optional[Submission]:
    return (
        assignment.submissions.filter(student=student)
        .order_by("-submitted_at")
        .first()
    )


def _serialize_sheet(sheet) -> dict:
    # List reads annotate ``marks_total`` / ``marks_graded`` (see
    # ``list_sheets``); single-object callers have no annotations, so fall
    # back to queries. Both figures stay derived on read.
    total = getattr(sheet, "marks_total", None)
    graded = getattr(sheet, "marks_graded", None)
    return {
        "id": str(sheet.pk),
        "course_offering_id": str(sheet.course_offering_id),
        "title": sheet.title,
        "category": sheet.category,
        "maximum_score": str(sheet.maximum_score),
        "weight": str(sheet.weight),
        "status": sheet.status,
        "created_at": sheet.created_at.isoformat() if sheet.created_at else None,
        "updated_at": sheet.updated_at.isoformat() if sheet.updated_at else None,
        "marks_count": total if total is not None else sheet.marks.count(),
        # A mark sheet row is shown as "12/12 marked": the denominator is every
        # mark on the sheet, the numerator is the ones carrying a score. Both
        # are derived on read — a mark gains `graded_count` the moment it is
        # scored, with nothing extra stored to drift.
        "graded_count": (
            graded if graded is not None else sheet.marks.filter(score__isnull=False).count()
        ),
    }


def _serialize_mark(mark, *, include_student: bool = False) -> dict:
    payload = {
        "id": str(mark.pk),
        "assessment_id": str(mark.assessment_id),
        "score": str(mark.score) if mark.score is not None else None,
        "comment": mark.comment,
        "dispute_status": mark.dispute_status,
        "dispute_reason": mark.dispute_reason,
        "dispute_response": mark.dispute_response,
        "created_at": mark.created_at.isoformat() if mark.created_at else None,
    }
    if include_student:
        student = mark.student
        payload["student"] = str(student.pk)
        payload["student_name"] = f"{student.first_name} {student.last_name}".strip()
        payload["matricule"] = getattr(student, "matricule", None)
    return payload


def _serialize_group(group) -> dict:
    """One collection plus its **derived** publication state.

    Accepted project decision B: ``AssessmentGroup`` is a collection of
    assessment sheets and stores no publication state of its own. Every value
    a client sees about release is recomputed from the child sheets' existing
    lifecycle (``AssessmentSheet.status`` DRAFT/PUBLISHED) on each read, so
    there is no stored duplicate of domain truth to drift, and a sheet added
    later makes a finished collection partial again without anyone editing a
    group row.

    ``sheets_count`` is kept because it predates this decision and other
    readers may still ask for it; it is the same measurement as
    ``sheet_count``, not a second opinion.
    """
    sheets = list(group.sheets.all())
    sheet_count = len(sheets)
    published_count = sum(
        1 for sheet in sheets if sheet.status == AssessmentSheet.Status.PUBLISHED
    )
    if sheet_count == 0 or published_count == 0:
        publication_state = "DRAFT"
    elif published_count == sheet_count:
        publication_state = "PUBLISHED"
    else:
        publication_state = "PARTIALLY_PUBLISHED"

    return {
        "id": str(group.pk),
        "course_offering_id": str(group.course_offering_id),
        "title": group.title,
        "sheets": [str(sheet.pk) for sheet in sheets],
        "sheets_count": sheet_count,
        "sheet_count": sheet_count,
        "published_sheet_count": published_count,
        "publication_state": publication_state,
        "sheets_detail": [
            {
                "id": str(sheet.pk),
                "title": sheet.title,
                "category": sheet.category,
                "status": sheet.status,
            }
            for sheet in sheets
        ],
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "updated_at": group.updated_at.isoformat() if group.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


def _parse_due_at(value):
    """Turn a client-supplied due date into an aware datetime.

    The payload arrives as an ISO 8601 string, and Django leaves the model
    attribute holding whatever it was given until the row is re-read. Without
    this parse the assignment would be saved holding a *string*, and the very
    next ``is_past_due`` comparison would raise ``TypeError: '<' not supported
    between instances of 'str' and 'datetime'`` — a 500 on the request that
    created it. Parsing here also means a malformed date becomes a 400 the
    client can correct, instead of a 500 it cannot.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise InvalidInputError("due_at must be an ISO 8601 date-time.")
    if timezone.is_naive(parsed):
        # A bare wall-clock time has no zone; interpret it in the active
        # timezone rather than silently comparing it against UTC.
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def list_assignments(*, user, offering_id) -> list[dict]:
    """Assignments on ``offering_id`` for the caller.

    Staff see every assignment with its submission counts. A student sees the
    assignments, plus their own submission rendered into ``my_submission``;
    other students' submissions are never included.
    """
    offering = _resolve_offering(user, offering_id)
    is_staff = is_offering_lecturer(user, offering)
    queryset = (
        offering.assignments.select_related("attachment")
        .annotate(
            submissions_total=models.Count("submissions"),
            submissions_graded=models.Count(
                "submissions",
                filter=models.Q(submissions__status=Submission.Status.GRADED),
            ),
        )
        .order_by("-created_at")
    )
    if not is_staff:
        # A student may only read coursework for an offering they are on.
        if not _offering_is_enrolled(user, offering):
            raise OfferingAccessDenied("You are not enrolled in that course.")
        # One query for every assignment's latest own submission, instead of
        # one per assignment inside the serializer.
        latest_by_assignment: dict = {}
        for submission in (
            Submission.objects.filter(
                assignment__course_offering=offering, student=user
            ).order_by("-submitted_at")
        ):
            latest_by_assignment.setdefault(submission.assignment_id, submission)
    else:
        latest_by_assignment = {}
    return [
        _serialize_assignment(
            a,
            is_staff=is_staff,
            student=None if is_staff else user,
            latest_submission=None if is_staff else latest_by_assignment.get(a.pk),
        )
        for a in queryset
    ]


def list_my_assignments(*, user) -> dict:
    """Everything one student must hand in, across their active offerings.

    The public service behind ``GET /students/me/assignments/``. The view
    stays an HTTP adapter (role gate + envelope); the enrollment lookup, the
    annotated counts and the single bulk latest-submission fetch live here so
    no view reaches into the private ``_serialize_assignment``.
    """
    from apps.academic.models import Enrollment

    offering_ids = list(
        Enrollment.objects.filter(
            student=user,
            is_active=True,
            deleted_at__isnull=True,
        )
        .exclude(course_offering__isnull=True)
        .values_list("course_offering_id", flat=True)
    )
    assignments = (
        Assignment.objects.filter(course_offering_id__in=offering_ids)
        .select_related("course_offering", "course_offering__course", "attachment")
        .annotate(
            submissions_total=models.Count("submissions"),
            submissions_graded=models.Count(
                "submissions",
                filter=models.Q(submissions__status=Submission.Status.GRADED),
            ),
        )
        .order_by("-due_at", "-created_at")
    )
    latest_by_assignment: dict = {}
    for submission in Submission.objects.filter(
        assignment__course_offering_id__in=offering_ids, student=user
    ).order_by("-submitted_at"):
        latest_by_assignment.setdefault(submission.assignment_id, submission)
    results = []
    for assignment in assignments:
        payload = _serialize_assignment(
            assignment,
            is_staff=False,
            student=user,
            latest_submission=latest_by_assignment.get(assignment.pk),
        )
        course = assignment.course_offering.course
        payload["course_code"] = course.code
        payload["course_title"] = course.name
        results.append(payload)
    return {"assignments": results, "count": len(results)}


@transaction.atomic
def create_assignment(
    *,
    user,
    offering_id,
    title: str,
    description: str = "",
    due_at: Any = None,
    allow_late: bool = False,
    max_submissions: int = 1,
    attachment=None,
) -> dict:
    offering = _resolve_offering(user, offering_id, for_write=True)
    if not is_offering_lecturer(user, offering):
        raise OfferingAccessDenied("Only the offering's lecturer may add coursework.")

    title = (title or "").strip()
    if not title:
        raise InvalidInputError("title is required.")
    if len(title) > 255:
        raise InvalidInputError("title must be 255 characters or fewer.")
    try:
        max_submissions = int(max_submissions)
    except (TypeError, ValueError):
        raise InvalidInputError("max_submissions must be a whole number.")
    if max_submissions < 1 or max_submissions > 20:
        raise InvalidInputError("max_submissions must be between 1 and 20.")

    assignment = Assignment.objects.create(
        course_offering=offering,
        title=title,
        description=description or "",
        due_at=_parse_due_at(due_at),
        allow_late=bool(allow_late),
        max_submissions=max_submissions,
        attachment=attachment,
        created_by=user,
    )
    _audit(
        action="assignment_created",
        resource_type="assignment",
        resource_id=assignment.pk,
        actor_id=user.pk,
        course_offering_id=str(offering.pk),
        title=title,
    )
    return _serialize_assignment(assignment, is_staff=True)


@transaction.atomic
def update_assignment(*, user, assignment_id, **fields) -> dict:
    assignment = _get_assignment_for_write(user, assignment_id)
    changed = {}

    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise InvalidInputError("title cannot be empty.")
        if len(title) > 255:
            raise InvalidInputError("title must be 255 characters or fewer.")
        assignment.title = title
        changed["title"] = title

    if "description" in fields:
        assignment.description = fields["description"] or ""
        changed["description"] = True

    if "due_at" in fields:
        assignment.due_at = _parse_due_at(fields["due_at"])
        changed["due_at"] = fields["due_at"]

    if "allow_late" in fields:
        assignment.allow_late = bool(fields["allow_late"])
        changed["allow_late"] = assignment.allow_late

    if "status" in fields:
        status = str(fields["status"]).upper()
        if status not in Assignment.Status.values:
            raise InvalidInputError("status must be ACTIVE, CLOSED or ARCHIVED.")
        assignment.status = status
        changed["status"] = status

    if not changed:
        raise InvalidInputError("No updatable fields were supplied.")

    assignment.updated_at = utc_now()
    assignment.save()
    _audit(
        action="assignment_updated",
        resource_type="assignment",
        resource_id=assignment.pk,
        actor_id=user.pk,
        changed=sorted(changed),
    )
    return _serialize_assignment(assignment, is_staff=True)


@transaction.atomic
def delete_assignment(*, user, assignment_id) -> None:
    assignment = _get_assignment_for_write(user, assignment_id)
    _audit(
        action="assignment_deleted",
        resource_type="assignment",
        resource_id=assignment.pk,
        actor_id=user.pk,
        course_offering_id=str(assignment.course_offering_id),
        title=assignment.title,
    )
    assignment.delete()


def _get_assignment_for_write(user, assignment_id) -> Assignment:
    assignment_id = _coerce_pk(
        assignment_id, AssignmentNotFoundError, "That assignment does not exist."
    )
    try:
        assignment = (
            Assignment.objects.select_related("course_offering", "course_offering__lecturer")
            .get(pk=assignment_id)
        )
    except Assignment.DoesNotExist:
        raise AssignmentNotFoundError("That assignment does not exist.")
    if not is_offering_lecturer(user, assignment.course_offering):
        # §25: the assignment *does* exist, so answering with a different
        # message than the missing case above would confirm which ids are real.
        # Both collapse onto the same not-found shape instead.
        raise AssignmentNotFoundError("That assignment does not exist.")
    return assignment


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


def list_submissions(*, user, assignment_id) -> list[dict]:
    """Submissions for one assignment.

    Staff see every submission with the student named. A student sees only
    their own — the queryset is scoped to them rather than filtered after
    the fact, so another student's work is never fetched at all.
    """
    assignment = _get_assignment_for_read(user, assignment_id)
    if is_offering_lecturer(user, assignment.course_offering):
        queryset = assignment.submissions.select_related("student", "file")
        return [
            _serialize_submission(s)
            for s in queryset
        ]
    if not _offering_is_enrolled(user, assignment.course_offering):
        # §25: identical to a missing id, so an unenrolled student probing a
        # real assignment id cannot tell it apart from a made-up one.
        raise AssignmentNotFoundError("That assignment does not exist.")
    return [
        _serialize_submission(s)
        for s in assignment.submissions.filter(student=user).select_related("file")
    ]


def _get_assignment_for_read(user, assignment_id) -> Assignment:
    assignment_id = _coerce_pk(
        assignment_id, AssignmentNotFoundError, "That assignment does not exist."
    )
    try:
        assignment = (
            Assignment.objects.select_related("course_offering", "course_offering__lecturer")
            .get(pk=assignment_id)
        )
    except Assignment.DoesNotExist:
        raise AssignmentNotFoundError("That assignment does not exist.")
    return assignment


@transaction.atomic
def submit_work(
    *,
    user,
    assignment_id,
    note: str = "",
    file=None,
) -> dict:
    """Record a student's attempt at an assignment."""
    assignment = _get_assignment_for_read(user, assignment_id)
    offering = assignment.course_offering

    if not _offering_is_enrolled(user, offering):
        # §25: an unenrolled student must not learn that this assignment
        # exists, so the denial is byte-identical to a missing id rather than
        # a 403 that confirms it.
        raise AssignmentNotFoundError("That assignment does not exist.")

    if assignment.status != Assignment.Status.ACTIVE:
        raise InvalidInputError("This assignment is not accepting submissions.")

    if assignment.is_past_due and not assignment.allow_late:
        raise InvalidInputError("The submission deadline for this assignment has passed.")

    if len((note or "").strip()) > 4000:
        raise InvalidInputError("note must be 4000 characters or fewer.")

    # A RETURNED submission is an invitation to resubmit and is superseded by
    # the new attempt rather than counted against the limit.
    prior = assignment.submissions.filter(student=user).exclude(
        status=Submission.Status.RETURNED
    ).count()

    if prior >= assignment.max_submissions:
        raise SubmissionLimitError(
            f"You have already used all {assignment.max_submissions} permitted attempts."
        )

    submission = Submission.objects.create(
        assignment=assignment,
        student=user,
        note=(note or "").strip(),
        file=file,
        status=Submission.Status.SUBMITTED,
    )
    _audit(
        action="assignment_submitted",
        resource_type="submission",
        resource_id=submission.pk,
        actor_id=user.pk,
        assignment_id=str(assignment.pk),
        course_offering_id=str(offering.pk),
    )
    return _serialize_submission(submission)


@transaction.atomic
def grade_submission(
    *,
    user,
    submission_id,
    grade: Optional[str] = None,
    feedback: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Record a lecturer's grade on one submission.

    The submitting student can never reach this: the offering ownership check
    rules out a student before any field is read.
    """
    submission_id = _coerce_pk(
        submission_id, SubmissionNotFoundError, "That submission does not exist."
    )
    try:
        submission = Submission.objects.select_related(
            "assignment", "assignment__course_offering", "student"
        ).get(pk=submission_id)
    except Submission.DoesNotExist:
        raise SubmissionNotFoundError("That submission does not exist.")

    if not is_offering_lecturer(user, submission.assignment.course_offering):
        # §25: byte-identical to the missing case above, so a caller cannot
        # tell a submission they may not grade from one that was never made.
        raise SubmissionNotFoundError("That submission does not exist.")

    changed = []
    if grade is not None:
        submission.grade = str(grade).strip()
        changed.append("grade")
    if feedback is not None:
        submission.feedback = str(feedback).strip()
        changed.append("feedback")
    if status is not None:
        normalised = str(status).upper()
        if normalised not in Submission.Status.values:
            raise InvalidInputError("status must be SUBMITTED, GRADED or RETURNED.")
        submission.status = normalised
        changed.append("status")

    if not changed:
        raise InvalidInputError("No grade, feedback or status was supplied.")

    if "status" in changed or "grade" in changed:
        submission.graded_at = timezone.now()
        submission.graded_by = user
    submission.save()
    _audit(
        action="submission_graded",
        resource_type="submission",
        resource_id=submission.pk,
        actor_id=user.pk,
        changed=changed,
    )
    return _serialize_submission(submission)


# ---------------------------------------------------------------------------
# Assessment sheets and marks
# ---------------------------------------------------------------------------


def list_sheets(*, user, offering_id) -> list[dict]:
    offering = _resolve_offering(user, offering_id)
    queryset = offering.assessment_sheets.annotate(
        marks_total=models.Count("marks"),
        marks_graded=models.Count(
            "marks", filter=models.Q(marks__score__isnull=False)
        ),
    ).order_by("-created_at")
    if not is_offering_lecturer(user, offering):
        if not _offering_is_enrolled(user, offering):
            raise OfferingAccessDenied("You are not enrolled in that course.")
        # Students only ever see published sheets; a draft is not yet a
        # result they are entitled to.
        queryset = queryset.filter(status=AssessmentSheet.Status.PUBLISHED)
    return [_serialize_sheet(s) for s in queryset]


@transaction.atomic
def create_sheet(
    *,
    user,
    offering_id,
    title: str,
    category: str = "CA",
    maximum_score: Any = "100",
    weight: Any = "100",
) -> dict:
    offering = _resolve_offering(user, offering_id, for_write=True)
    if not is_offering_lecturer(user, offering):
        raise OfferingAccessDenied("Only the offering's lecturer may create a sheet.")

    title = (title or "").strip()
    if not title:
        raise InvalidInputError("title is required.")
    if len(title) > 255:
        raise InvalidInputError("title must be 255 characters or fewer.")

    category = str(category).upper()
    if category not in AssessmentSheet.Category.values:
        raise InvalidInputError("category must be CA or EXAM.")

    try:
        maximum_score = Decimal(str(maximum_score))
    except (InvalidOperation, ValueError, TypeError):
        raise InvalidInputError("maximum_score must be a number.")
    if maximum_score <= 0 or maximum_score > 1000:
        raise InvalidInputError("maximum_score must be between 0 and 1000.")

    try:
        weight = Decimal(str(weight))
    except (InvalidOperation, ValueError, TypeError):
        raise InvalidInputError("weight must be a number.")
    if weight < 0 or weight > 100:
        raise InvalidInputError("weight must be between 0 and 100.")

    sheet = AssessmentSheet.objects.create(
        course_offering=offering,
        title=title,
        category=category,
        maximum_score=maximum_score,
        weight=weight,
        created_by=user,
    )
    _audit(
        action="assessment_sheet_created",
        resource_type="assessment_sheet",
        resource_id=sheet.pk,
        actor_id=user.pk,
        course_offering_id=str(offering.pk),
        title=title,
    )
    return _serialize_sheet(sheet)


def _get_sheet_for_write(user, sheet_id) -> AssessmentSheet:
    sheet_id = _coerce_pk(
        sheet_id, SheetNotFoundError, "That assessment sheet does not exist."
    )
    try:
        sheet = AssessmentSheet.objects.select_related(
            "course_offering", "course_offering__lecturer"
        ).get(pk=sheet_id)
    except AssessmentSheet.DoesNotExist:
        raise SheetNotFoundError("That assessment sheet does not exist.")
    if not is_offering_lecturer(user, sheet.course_offering):
        # §25: the sheet exists, so a message about the *offering* would answer
        # differently from a sheet that was never created. Both give the same
        # not-found answer, so ownership cannot be probed.
        raise SheetNotFoundError("That assessment sheet does not exist.")
    return sheet


def _get_sheet_for_read(user, sheet_id) -> AssessmentSheet:
    sheet_id = _coerce_pk(
        sheet_id, SheetNotFoundError, "That assessment sheet does not exist."
    )
    try:
        return AssessmentSheet.objects.select_related(
            "course_offering", "course_offering__lecturer"
        ).get(pk=sheet_id)
    except AssessmentSheet.DoesNotExist:
        raise SheetNotFoundError("That assessment sheet does not exist.")


def _visible_sheet_for_read(user, sheet_id) -> AssessmentSheet:
    """Resolve one sheet and apply the read-visibility rule exactly once.

    :func:`get_sheet` and the CSV export both stand on this, so "who may see
    this sheet" has one definition and an export can never be reached by
    somebody who could not read the sheet by any other route.

    A detail read leaks more than a list ever can: answering "forbidden" for a
    real id and "not found" for a made-up one confirms which ids exist. Every
    caller who is not entitled to the sheet therefore receives the same
    not-found error a missing sheet produces, so entitlement is never
    distinguishable from absence (§25).
    """
    sheet = _get_sheet_for_read(user, sheet_id)
    offering = sheet.course_offering
    if is_offering_lecturer(user, offering):
        return sheet
    if not _offering_is_enrolled(user, offering):
        raise SheetNotFoundError("That assessment sheet does not exist.")
    if sheet.status != AssessmentSheet.Status.PUBLISHED:
        # A draft is not yet a result the student is entitled to see (BR-131).
        raise SheetNotFoundError("That assessment sheet does not exist.")
    return sheet


def get_sheet(*, user, sheet_id) -> dict:
    """Read one sheet under exactly the rules :func:`list_sheets` applies."""
    return _serialize_sheet(_visible_sheet_for_read(user, sheet_id))


@transaction.atomic
def update_sheet(*, user, sheet_id, **fields) -> dict:
    """Edit a sheet's metadata. Marks are untouched by this."""
    sheet = _get_sheet_for_write(user, sheet_id)
    changed = []

    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise InvalidInputError("title cannot be empty.")
        if len(title) > 255:
            raise InvalidInputError("title must be 255 characters or fewer.")
        sheet.title = title
        changed.append("title")

    if "category" in fields:
        category = str(fields["category"]).upper()
        if category not in AssessmentSheet.Category.values:
            raise InvalidInputError("category must be CA or EXAM.")
        sheet.category = category
        changed.append("category")

    if "maximum_score" in fields:
        try:
            maximum_score = Decimal(str(fields["maximum_score"]))
        except (InvalidOperation, ValueError, TypeError):
            raise InvalidInputError("maximum_score must be a number.")
        if maximum_score <= 0 or maximum_score > 1000:
            raise InvalidInputError("maximum_score must be between 0 and 1000.")
        # Lowering the ceiling below marks already recorded would silently
        # invalidate them, so it is refused rather than quietly truncating.
        highest = sheet.marks.aggregate(models.Max("score"))["score__max"]
        if highest is not None and maximum_score < highest:
            raise InvalidInputError(
                "maximum_score cannot be lower than a mark already recorded."
            )
        sheet.maximum_score = maximum_score
        changed.append("maximum_score")

    if "weight" in fields:
        try:
            weight = Decimal(str(fields["weight"]))
        except (InvalidOperation, ValueError, TypeError):
            raise InvalidInputError("weight must be a number.")
        if weight < 0 or weight > 100:
            raise InvalidInputError("weight must be between 0 and 100.")
        sheet.weight = weight
        changed.append("weight")

    if not changed:
        raise InvalidInputError("No updatable fields were supplied.")

    sheet.updated_at = utc_now()
    sheet.save()
    _audit(
        action="assessment_sheet_updated",
        resource_type="assessment_sheet",
        resource_id=sheet.pk,
        actor_id=user.pk,
        changed=changed,
    )
    return _serialize_sheet(sheet)


@transaction.atomic
def delete_sheet(*, user, sheet_id) -> None:
    """Remove a sheet and the marks recorded against it.

    The marks have no meaning without the sheet they were entered against, so
    they are removed with it rather than left orphaned. Both halves happen in
    one transaction and both are audited.
    """
    sheet = _get_sheet_for_write(user, sheet_id)
    marks_removed = sheet.marks.count()
    _audit(
        action="assessment_sheet_deleted",
        resource_type="assessment_sheet",
        resource_id=sheet.pk,
        actor_id=user.pk,
        course_offering_id=str(sheet.course_offering_id),
        title=sheet.title,
        marks_removed=marks_removed,
    )
    sheet.delete()


def list_marks(*, user, sheet_id) -> dict:
    """The marks held against one sheet.

    Staff see every mark with the student named, so they can type or correct
    a whole sheet. A student sees only their own row, and only when the sheet
    has been published — a draft is not a result they are entitled to.
    """
    sheet = _get_sheet_for_read(user, sheet_id)
    if is_offering_lecturer(user, sheet.course_offering):
        marks = sheet.marks.select_related("student")
        return {
            "sheet": _serialize_sheet(sheet),
            "marks": [_serialize_mark(m, include_student=True) for m in marks],
        }

    if not _offering_is_enrolled(user, sheet.course_offering):
        # §25: same envelope as a missing sheet (and as an unpublished one,
        # just below), so neither enrollment nor draft status is confirmed.
        raise SheetNotFoundError("That assessment sheet does not exist.")
    if sheet.status != AssessmentSheet.Status.PUBLISHED:
        raise SheetNotFoundError("That assessment sheet does not exist.")

    own = sheet.marks.filter(student=user)
    return {
        "sheet": _serialize_sheet(sheet),
        "marks": [_serialize_mark(m, include_student=False) for m in own],
    }


@transaction.atomic
def save_marks(*, user, sheet_id, marks: list) -> dict:
    """Replace the marks held against one sheet.

    ``marks`` is a list of ``{student, score, comment}``. Rows are upserted by
    ``(sheet, student)``, so re-typing a sheet's marks updates rather than
    duplicates them. The whole operation is atomic: a half-typed sheet is
    never left visible.
    """
    sheet = _get_sheet_for_write(user, sheet_id)
    if not isinstance(marks, list):
        raise InvalidInputError("marks must be a list.")

    from apps.accounts.models import User

    created = 0
    updated = 0
    for row in marks:
        if not isinstance(row, dict):
            raise InvalidInputError("each mark must be an object.")
        student_id = row.get("student")
        if not student_id:
            raise InvalidInputError("each mark must name a student.")

        try:
            student = User.objects.get(pk=student_id)
        except (
            User.DoesNotExist,
            DjangoValidationError,
            ValueError,
            TypeError,
        ):
            # A malformed student id reaches the ORM as a Django
            # ValidationError, which has no envelope mapping — it must land
            # here as a 400 like any other bad payload field, not a 500.
            raise InvalidInputError("That student does not exist.")
        if student.role != User.Role.STUDENT:
            raise InvalidInputError("Marks can only be recorded against students.")

        score = row.get("score")
        if score is not None:
            try:
                score = Decimal(str(score))
            except (InvalidOperation, ValueError, TypeError):
                raise InvalidInputError("score must be a number.")
            if score < 0 or score > sheet.maximum_score:
                raise InvalidInputError(
                    f"score must be between 0 and {sheet.maximum_score}."
                )

        comment = str(row.get("comment") or "").strip()
        if len(comment) > 4000:
            raise InvalidInputError("comment must be 4000 characters or fewer.")

        _, was_created = AssessmentMark.objects.update_or_create(
            assessment=sheet,
            student=student,
            defaults={
                "score": score,
                "comment": comment,
                "created_by": user,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    _audit(
        action="assessment_marks_saved",
        resource_type="assessment_sheet",
        resource_id=sheet.pk,
        actor_id=user.pk,
        created=created,
        updated=updated,
    )
    payload = _serialize_sheet(sheet)
    payload["marks"] = [
        _serialize_mark(m, include_student=True) for m in sheet.marks.all()
    ]
    return payload


@transaction.atomic
def update_mark(*, user, mark_id, **fields) -> dict:
    mark_id = _coerce_pk(mark_id, SheetNotFoundError, "That mark does not exist.")
    try:
        mark = AssessmentMark.objects.select_related(
            "assessment", "assessment__course_offering", "student"
        ).get(pk=mark_id)
    except AssessmentMark.DoesNotExist:
        raise SheetNotFoundError("That mark does not exist.")

    sheet = mark.assessment
    staff = is_offering_lecturer(user, sheet.course_offering)

    if staff:
        changed = _apply_staff_mark_fields(mark, sheet, fields)
        include_student = True
    else:
        changed = _apply_student_dispute(mark, sheet, user, fields)
        include_student = False

    if not changed:
        raise InvalidInputError("No mark fields were supplied.")

    mark.save()
    _audit(
        action="assessment_mark_updated",
        resource_type="assessment_mark",
        resource_id=mark.pk,
        actor_id=user.pk,
        changed=changed,
    )
    return _serialize_mark(mark, include_student=include_student)


def _apply_staff_mark_fields(mark, sheet, fields) -> list:
    """The offering's lecturer may change every field of a mark."""
    changed = []
    if "score" in fields and fields["score"] is not None:
        try:
            score = Decimal(str(fields["score"]))
        except (InvalidOperation, ValueError, TypeError):
            raise InvalidInputError("score must be a number.")
        if score < 0 or score > sheet.maximum_score:
            raise InvalidInputError(f"score must be between 0 and {sheet.maximum_score}.")
        mark.score = score
        changed.append("score")

    if "comment" in fields:
        mark.comment = str(fields["comment"] or "").strip()
        changed.append("comment")

    if "dispute_reason" in fields:
        reason = str(fields["dispute_reason"] or "").strip()
        mark.dispute_reason = reason
        mark.dispute_status = (
            AssessmentMark.DisputeStatus.OPEN
            if reason
            else AssessmentMark.DisputeStatus.RESOLVED
        )
        changed.append("dispute_reason")

    if "dispute_response" in fields:
        mark.dispute_response = str(fields["dispute_response"] or "").strip()
        if mark.dispute_response:
            mark.dispute_status = AssessmentMark.DisputeStatus.RESOLVED
        changed.append("dispute_response")

    return changed


def _apply_student_dispute(mark, sheet, user, fields) -> list:
    """A student may raise a dispute about their own released mark, and that is all.

    Four separate refusals, each for its own reason:

    * **another student's mark**, or **an unpublished sheet** — reported as
      absent rather than forbidden, so a student cannot use this route to
      discover which marks exist (§25), matching what ``list_marks`` already
      withholds;
    * **any field but ``dispute_reason``** — a student must never be able to
      move their own score, write their own feedback, or supply the lecturer's
      response to their dispute;
    * **an empty reason** — clearing the reason is precisely what closes a
      dispute, and only the lecturer may close one. Without this check a
      student could raise a dispute and immediately mark it resolved
      themselves, which would defeat the audit trail the dispute exists for.
    """
    if (
        getattr(user, "role", None) != "STUDENT"
        or mark.student_id != user.pk
        or sheet.status != AssessmentSheet.Status.PUBLISHED
    ):
        raise SheetNotFoundError("That mark does not exist.")

    if set(fields) - {"dispute_reason"}:
        raise MarkEditForbidden(
            "Only a dispute about your own released mark may be submitted here."
        )

    reason = str(fields.get("dispute_reason") or "").strip()
    if not reason:
        raise MarkEditForbidden(
            "A dispute needs a reason; only the lecturer may close one."
        )
    if len(reason) > 4000:
        raise InvalidInputError("dispute_reason must be 4000 characters or fewer.")

    mark.dispute_reason = reason
    mark.dispute_status = AssessmentMark.DisputeStatus.OPEN
    return ["dispute_reason"]


@transaction.atomic
def _release_sheet_transition(*, user, sheet, target_status: str) -> bool:
    """Apply the canonical sheet-release transition to one already-scoped row.

    The single-sheet ``PATCH /assessment-sheets/{id}/publish/`` route and the
    group bulk release both stand on this, so "release a sheet" has exactly
    one implementation: the status flip plus its BR-132 audit record, and
    nothing else. Scores are never invented, changed or back-filled here — a
    release changes visibility, never a mark.

    Returns ``True`` only when the row actually moved. That is what makes a
    repeated request safe: an already-published sheet produces no second
    transition and no duplicate successful-transition audit entry.
    """
    if sheet.status == target_status:
        return False
    sheet.status = target_status
    sheet.save()
    _audit(
        action=(
            "assessment_sheet_published"
            if target_status == AssessmentSheet.Status.PUBLISHED
            else "assessment_sheet_unpublished"
        ),
        resource_type="assessment_sheet",
        resource_id=sheet.pk,
        actor_id=user.pk,
        status=target_status,
    )
    return True


@transaction.atomic
def publish_sheet(*, user, sheet_id, status: str) -> dict:
    """Move a sheet between DRAFT and PUBLISHED."""
    sheet = _get_sheet_for_write(user, sheet_id)
    normalised = str(status).upper()
    if normalised not in AssessmentSheet.Status.values:
        raise InvalidInputError("status must be DRAFT or PUBLISHED.")
    # Re-read under the row lock so a bulk release of a group that contains
    # this sheet serialises against this write instead of interleaving with
    # it. Only this sheet's row is locked.
    sheet = AssessmentSheet.objects.select_for_update().get(pk=sheet.pk)
    _release_sheet_transition(user=user, sheet=sheet, target_status=normalised)
    return _serialize_sheet(sheet)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def list_groups(*, user, offering_id) -> list[dict]:
    offering = _resolve_offering(user, offering_id)
    if not is_offering_lecturer(user, offering):
        raise OfferingAccessDenied("Assessment groups are a staff surface.")
    # Prefetched because every row's derived state is computed from its sheets.
    groups = offering.assessment_groups.prefetch_related("sheets").order_by("-created_at")
    return [_serialize_group(g) for g in groups]


def _get_group_for_read(user, group_id) -> AssessmentGroup:
    """Resolve one group for a read, refusing everyone else with 404.

    ``list_groups`` refuses non-staff with 403 because a list names no
    particular row. A detail lookup does: returning 403 to an unauthorized
    caller while a missing row returns 404 would confirm that a guessed id
    exists. §25 requires the two to be indistinguishable, so both collapse
    onto the same not-found error and no entitlement is ever confirmed.
    """
    group_id = _coerce_pk(
        group_id, GroupNotFoundError, "That assessment group does not exist."
    )
    try:
        group = AssessmentGroup.objects.select_related(
            "course_offering", "course_offering__lecturer"
        ).get(pk=group_id)
    except AssessmentGroup.DoesNotExist:
        raise GroupNotFoundError("That assessment group does not exist.")
    if not is_offering_lecturer(user, group.course_offering):
        raise GroupNotFoundError("That assessment group does not exist.")
    return group


def get_group(*, user, group_id) -> dict:
    """Read one assessment group the caller is entitled to see."""
    return _serialize_group(_get_group_for_read(user, group_id))


@transaction.atomic
def create_group(*, user, offering_id, title: str, sheets: Optional[list] = None) -> dict:
    offering = _resolve_offering(user, offering_id, for_write=True)
    if not is_offering_lecturer(user, offering):
        raise OfferingAccessDenied("Only the offering's lecturer may create a group.")

    title = (title or "").strip()
    if not title:
        raise InvalidInputError("title is required.")
    if len(title) > 255:
        raise InvalidInputError("title must be 255 characters or fewer.")

    group = AssessmentGroup.objects.create(
        course_offering=offering, title=title, created_by=user
    )
    if sheets:
        group.sheets.set(_resolve_sheets(user, offering, sheets))
    _audit(
        action="assessment_group_created",
        resource_type="assessment_group",
        resource_id=group.pk,
        actor_id=user.pk,
        course_offering_id=str(offering.pk),
        title=title,
    )
    return _serialize_group(group)


def _resolve_sheets(user, offering, sheet_ids) -> list:
    if not isinstance(sheet_ids, (list, tuple, set)):
        raise InvalidInputError("sheets must be a list of ids.")
    try:
        wanted = {uuid.UUID(str(one)) for one in sheet_ids}
    except (ValueError, TypeError, AttributeError, DjangoValidationError):
        # A malformed id inside the payload would otherwise raise straight out
        # of the ORM as a Django ValidationError and come back as a 500.
        raise InvalidInputError("One or more sheets do not belong to that offering.")
    resolved = list(offering.assessment_sheets.filter(pk__in=wanted))
    if len(resolved) != len(wanted):
        raise InvalidInputError("One or more sheets do not belong to that offering.")
    return resolved


def _get_group_for_write(user, group_id) -> AssessmentGroup:
    group_id = _coerce_pk(
        group_id, GroupNotFoundError, "That assessment group does not exist."
    )
    try:
        group = AssessmentGroup.objects.select_related(
            "course_offering", "course_offering__lecturer"
        ).get(pk=group_id)
    except AssessmentGroup.DoesNotExist:
        raise GroupNotFoundError("That assessment group does not exist.")
    if not is_offering_lecturer(user, group.course_offering):
        # §25: same answer as a group that was never created, so ownership
        # cannot be probed one id at a time.
        raise GroupNotFoundError("That assessment group does not exist.")
    return group


@transaction.atomic
def update_group(*, user, group_id, fields) -> dict:
    """Edit a collection's supported metadata: its title and its sheets.

    ``fields`` is the raw request body, not a filtered subset: anything the
    client sends that is not ``title`` or ``sheets`` is named back as
    unsupported rather than silently dropped. In particular the retired
    ``{status: ...}`` body has no meaning here — a collection holds no
    publication state of its own (accepted decision B) — so the caller is told
    so instead of being allowed to believe it worked.

    Locking: the group row is taken first and the target sheet rows second,
    which is the same order the bulk release uses, so a membership edit and a
    bulk release serialise instead of deadlocking. Nothing outside this
    collection is locked.
    """
    fields = dict(fields or {})
    group = _get_group_for_write(user, group_id)
    allowed = {"title", "sheets"}
    unexpected = set(fields) - allowed
    if unexpected:
        raise InvalidInputError(
            "Unsupported field(s): {}. Group metadata supports title and sheets "
            "only.".format(", ".join(sorted(str(key) for key in unexpected)))
        )

    group = AssessmentGroup.objects.select_for_update().get(pk=group.pk)
    changed = []
    if "title" in fields:
        title = (fields["title"] or "").strip()
        if not title:
            raise InvalidInputError("title cannot be empty.")
        group.title = title
        changed.append("title")
    if "sheets" in fields:
        targets = _resolve_sheets(user, group.course_offering, fields["sheets"])
        # Take the member-row locks in the same group-then-sheets order the
        # bulk release uses, so the two never interleave on the same rows.
        list(
            AssessmentSheet.objects.select_for_update().filter(
                pk__in=[sheet.pk for sheet in targets]
            )
        )
        group.sheets.set(targets)
        changed.append("sheets")
    if not changed:
        raise InvalidInputError("No updatable fields were supplied.")
    group.save()
    _audit(
        action="assessment_group_updated",
        resource_type="assessment_group",
        resource_id=group.pk,
        actor_id=user.pk,
        changed=changed,
    )
    return _serialize_group(group)


@transaction.atomic
def publish_group(*, user, group_id) -> dict:
    """Release every unpublished sheet in one collection.

    Accepted project decision B, and an explicit MVP product decision rather
    than institutional grading policy: a collection holds no publication state
    of its own, so "publish the group" means *release its sheets* through the
    canonical sheet lifecycle — never a second, parallel notion of published.

    Guarantees, in the order they are enforced:

    * **Authority.** ``_get_group_for_write`` applies the central
      approved-lecturer/admin + offering-scope policy to the collection, and
      every member sheet's offering is then checked against the same
      :func:`is_offering_lecturer` predicate. Sign-in alone is never enough.
    * **Snapshot validation before any write.** The whole membership is read
      and validated first, so a single unreachable or foreign child fails the
      request *before* the first row changes — no partial release, and nothing
      is "repaired" by inventing scores.
    * **One lock order.** Collection row first, member sheet rows second: the
      same order ``update_group`` takes, so a membership edit and a bulk
      release serialise instead of racing. Nothing outside this collection is
      locked.
    * **One release implementation.** Each sheet goes through
      :func:`_release_sheet_transition`, so the effect and the BR-132 audit of
      a sheet released here are identical to the single-sheet route's.
    * **Idempotent.** An already-released sheet is counted, not re-released:
      a repeated request reports ``newly_published: 0`` and writes no second
      transition, no second transition audit, and no summary audit at all.
    * **No side effects on failure.** Everything runs in one transaction and
      the only side effect is the audit row, which lives in the same database;
      there is no cache or mail step to fall outside a rollback.
    """
    group = _get_group_for_write(user, group_id)
    # `group` already carries the select_related offering used for the scope
    # check; a second instance is fetched only to hold the row lock, so no
    # joined table (offering, lecturer) is locked along with it.
    locked_group = AssessmentGroup.objects.select_for_update().get(pk=group.pk)
    offering = group.course_offering
    sheets = list(locked_group.sheets.select_for_update().all())

    if not sheets:
        raise EmptyGroupError("This collection has no assessment sheets to publish.")

    # Full membership snapshot validated before a single row is written.
    # Comparing ids needs no queries and proves every member sits inside the
    # collection's own offering; the one authority check that follows is then
    # made against that same offering, so it is simultaneously authority over
    # the collection *and* over every sheet it contains — a sheet elsewhere can
    # only fail the first loop, which aborts the request before any release.
    for sheet in sheets:
        if sheet.course_offering_id != offering.pk:
            # Belt-and-braces behind `_resolve_sheets`: a member that escaped
            # its offering must fail the whole request, not be released anyway.
            raise InvalidInputError(
                "One or more sheets in this collection do not belong to its "
                "course offering."
            )
    if not is_offering_lecturer(user, offering):
        raise InvalidInputError(
            "One or more sheets in this collection cannot be released by this "
            "account."
        )

    unpublished = [
        sheet for sheet in sheets if sheet.status != AssessmentSheet.Status.PUBLISHED
    ]
    already_published = len(sheets) - len(unpublished)

    newly_published = 0
    for sheet in unpublished:
        if _release_sheet_transition(
            user=user, sheet=sheet, target_status=AssessmentSheet.Status.PUBLISHED
        ):
            newly_published += 1

    if newly_published:
        # Only on a real change: a repeat of a completed request has no side
        # effects at all, and never claims work that did not happen.
        _audit(
            action="assessment_group_published",
            resource_type="assessment_group",
            resource_id=locked_group.pk,
            actor_id=user.pk,
            sheet_count=len(sheets),
            newly_published=newly_published,
            already_published=already_published,
        )

    payload = _serialize_group(locked_group)
    payload["newly_published"] = newly_published
    payload["already_published"] = already_published
    return payload


@transaction.atomic
def delete_group(*, user, group_id) -> None:
    group = _get_group_for_write(user, group_id)
    _audit(
        action="assessment_group_deleted",
        resource_type="assessment_group",
        resource_id=group.pk,
        actor_id=user.pk,
        course_offering_id=str(group.course_offering_id),
        title=group.title,
    )
    group.delete()


# ---------------------------------------------------------------------------
# Export — the one authoritative CSV capability
# ---------------------------------------------------------------------------


#: Fixed column order for every coursework CSV. Two exports of the same data
#: must line up column for column, so this is a constant rather than something
#: assembled from whichever keys happen to be populated.
EXPORT_COLUMNS = (
    "course_offering_id",
    "sheet_id",
    "sheet_title",
    "sheet_category",
    "student_id",
    "matricule",
    "student_name",
    "score",
    "maximum_score",
    "comment",
    "dispute_status",
    "dispute_reason",
    "dispute_response",
    "mark_updated_at",
)

# Characters a spreadsheet reads as the start of a formula rather than as
# text. A mark's comment and a student's name are untrusted input; written
# through unchanged they would be *executed* by whatever spreadsheet opens the
# file instead of displayed.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value) -> str:
    """Render one untrusted value as a CSV cell with formulas neutralised."""
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_LEAD:
        # The standard mitigation: a leading apostrophe tells the spreadsheet
        # to treat the cell as literal text rather than evaluate it.
        return "'" + text
    return text


def _amount(value) -> str:
    """Render a decimal at the field's declared two-place scale.

    A freshly built row can still hold ``Decimal('100')`` while a row read
    back from the table holds ``Decimal('100.00')``. Quantising here means the
    same mark always renders as the same text, whatever path produced it.
    """
    if value is None:
        return ""
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError, TypeError):  # noqa: BLE001 - never let a display quirk fail an export
        return str(value)


def _export_slug(label: str) -> str:
    """Turn a sheet or group title into a filename-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return (slug or "marks")[:60]


def _render_marks_csv(sheets) -> str:
    """Render the given sheets and every mark on them as CSV text."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)  # default line terminator is RFC 4180 CRLF
    writer.writerow(EXPORT_COLUMNS)
    for sheet in sheets:
        offering_id = str(sheet.course_offering_id)
        sheet_id = str(sheet.pk)
        maximum = _amount(sheet.maximum_score)
        # Ordered, not incidental: without an explicit sort the row order
        # follows whatever the database happens to return, and two exports of
        # identical data would differ.
        marks = sheet.marks.select_related("student").order_by(
            "student__matricule",
            "student__last_name",
            "student__first_name",
            "student_id",
            "id",
        )
        for mark in marks:
            student = mark.student
            writer.writerow(
                [
                    offering_id,
                    sheet_id,
                    _csv_cell(sheet.title),
                    _csv_cell(sheet.category),
                    str(student.pk),
                    _csv_cell(getattr(student, "matricule", None)),
                    _csv_cell(
                        f"{student.first_name} {student.last_name}".strip()
                    ),
                    _amount(mark.score),
                    maximum,
                    _csv_cell(mark.comment),
                    _csv_cell(mark.dispute_status),
                    _csv_cell(mark.dispute_reason),
                    _csv_cell(mark.dispute_response),
                    mark.updated_at.isoformat() if mark.updated_at else "",
                ]
            )
    return buffer.getvalue()


def _build_export(sheets, *, label: str, scope_id) -> dict:
    return {
        "filename": f"fet-{_export_slug(label)}-{scope_id}.csv",
        "content_type": "text/csv; charset=utf-8",
        "content": _render_marks_csv(sheets),
    }


def export_sheet_marks_csv(*, user, sheet_id) -> dict:
    """Export one sheet's marks. The canonical export on this surface.

    Authorization is not re-derived here: visibility comes from
    :func:`_visible_sheet_for_read`, the very call a plain read of the sheet
    makes, so an export can never be reached by somebody who could not read
    the sheet by another route and a stranger is told only that it does not
    exist. Only once the sheet is known to be visible does the staff-only
    rule apply, and that refusal is a genuine 403 (see
    :class:`ExportForbidden`) because the caller may legitimately read the
    sheet itself.

    The dataset is one sheet's recorded marks and nothing else — no derived
    totals, no weighting. What a mark *is* is defined by the model; what a
    weighted rollup would be is defined nowhere, so none is invented here.
    """
    sheet = _visible_sheet_for_read(user, sheet_id)
    if not is_offering_lecturer(user, sheet.course_offering):
        raise ExportForbidden("Only teaching staff may export marks.")
    return _build_export([sheet], label=sheet.title, scope_id=sheet.pk)


def export_group_marks_csv(*, user, group_id) -> dict:
    """Export every sheet belonging to one assessment group, as one CSV.

    A group is a *collection of sheets*, so its export is the same dataset as
    :func:`export_sheet_marks_csv` with the scope widened to the member
    sheets — which is what makes this one capability rather than two. The
    rows are still confined to the group's own offering, so a group id from
    one course can never pull marks from another.

    This is deliberately **not** a weighted rollup. The combined-grade table
    the client renders alongside it expects per-student totals against a
    weight, a marking scale, and unit conversion — concepts that appear in no
    specification and nowhere in the backend. Producing those columns would
    mean inventing the grading arithmetic, so the export reports what is
    actually recorded and stops there.
    """
    group = _get_group_for_read(user, group_id)
    sheets = list(
        group.sheets.filter(course_offering_id=group.course_offering_id)
        .select_related("course_offering")
        .order_by("title", "id")
    )
    return _build_export(sheets, label=group.title, scope_id=group.pk)
