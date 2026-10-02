"""Assessment service for authorized, traceable student grading workflow.

This service keeps evaluation rules simple and explicit. It does not import any
Django request/response object; instead it validates authorization, visibility,
and auditability.

Relevant rules:
- BR-130: only authorized academic users may create or modify official assessments.
- BR-131: students may view only their own released assessments.
- BR-132: assessment creation/modification must be traceable.
- BR-133: assessment decisions should not automatically judge student character.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from core.academic_access import is_authorized_academic_user
from core.audit import audit_assessment_change
from core.common import ConfigurationError, utc_now


class AssessmentError(ValueError):
    """Base error for assessment service operations."""


class UnauthorizedAssessmentActionError(AssessmentError):
    """Raised when a user is not authorized to modify or create assessment records."""


class AssessmentNotFoundError(AssessmentError):
    """Raised when a requested assessment record cannot be found."""


class AssessmentVisibilityError(AssessmentError):
    """Raised when a student tries to view a restricted assessment."""


class AssessmentRecordLike(Protocol):
    id: Any
    student_id: Any
    course_id: Any
    class_id: Any
    created_by_id: Any
    updated_by_id: Any
    released: Any
    private_notes: Any
    score: Any
    status: Any
    created_at: Any
    updated_at: Any

    def save(self) -> Any:
        ...


class AcademicUserLike(Protocol):
    id: Any
    role: Any
    is_staff: Any
    is_lecturer: Any
    is_student: Any
    course_ids: Any
    class_ids: Any


def _audit(
    audit_logger: Optional[Any],
    *,
    action: str,
    assessment: Any,
    actor: Any,
    details: Dict[str, Any],
) -> None:
    """Always create an audit entry, using an injected sink when provided."""
    if audit_logger is not None:
        audit_logger(
            action=action,
            resource_type="assessment",
            resource_id=getattr(assessment, "id", None),
            actor_id=getattr(actor, "id", None),
            details=details,
        )
        return
    audit_assessment_change(
        actor_id=getattr(actor, "id", None),
        assessment_id=getattr(assessment, "id", None),
        reason=action,
        metadata=details,
    )


def create_assessment(
    *,
    AssessmentModel: type[AssessmentRecordLike],
    student_id: Any,
    created_by: Optional[AcademicUserLike],
    score: Optional[Any] = None,
    private_notes: Optional[str] = None,
    released: bool = False,
    course_id: Optional[Any] = None,
    class_id: Optional[Any] = None,
    audit_logger: Optional[Any] = None,
) -> AssessmentRecordLike:
    """Create an official assessment only for authorized academic users."""
    # BR-130: only authorized academic users may create official assessments.
    if AssessmentModel is None:
        raise ConfigurationError("AssessmentModel is required")
    if created_by is None or not is_authorized_academic_user(created_by):
        raise UnauthorizedAssessmentActionError("Only authorized academic users can create an official assessment")
    if student_id is None:
        raise AssessmentError("Student id is required")

    assessment = AssessmentModel()
    if hasattr(assessment, "student_id"):
        assessment.student_id = student_id
    if hasattr(assessment, "course_id"):
        assessment.course_id = course_id
    if hasattr(assessment, "class_id"):
        assessment.class_id = class_id
    if hasattr(assessment, "score"):
        assessment.score = score
    if hasattr(assessment, "private_notes"):
        assessment.private_notes = private_notes
    if hasattr(assessment, "released"):
        assessment.released = bool(released)
    if hasattr(assessment, "status"):
        assessment.status = "draft" if score is None else "official"
    if hasattr(assessment, "created_by_id"):
        assessment.created_by_id = getattr(created_by, "id", None)
    if hasattr(assessment, "created_at"):
        assessment.created_at = utc_now()

    assessment.save()

    _audit(
        audit_logger,
        action="assessment_created",
        assessment=assessment,
        actor=created_by,
        details={
            "student_id": student_id,
            "course_id": course_id,
            "class_id": class_id,
            "released": bool(released),
        },
    )

    return assessment


def update_assessment(
    *,
    assessment: Any,
    actor: Optional[AcademicUserLike],
    new_score: Optional[Any] = None,
    private_notes: Optional[str] = None,
    released: Optional[bool] = None,
    audit_logger: Optional[Any] = None,
) -> AssessmentRecordLike:
    """Update an assessment only when the actor is authorized and the audit trail is kept."""
    # BR-130 and BR-132: assessment mutations require authorization and must be
    # traceable.
    if assessment is None:
        raise AssessmentNotFoundError("Assessment not found")
    if actor is None or not is_authorized_academic_user(actor):
        raise UnauthorizedAssessmentActionError("Only authorized academic users can modify an official assessment")

    if new_score is not None and hasattr(assessment, "score"):
        assessment.score = new_score
    if private_notes is not None and hasattr(assessment, "private_notes"):
        assessment.private_notes = private_notes
    if released is not None and hasattr(assessment, "released"):
        assessment.released = bool(released)
    if hasattr(assessment, "updated_by_id"):
        assessment.updated_by_id = getattr(actor, "id", None)
    if hasattr(assessment, "updated_at"):
        assessment.updated_at = utc_now()

    assessment.save()

    _audit(
        audit_logger,
        action="assessment_updated",
        assessment=assessment,
        actor=actor,
        details={
            "student_id": getattr(assessment, "student_id", None),
            "score": getattr(assessment, "score", None),
            "released": getattr(assessment, "released", None),
        },
    )
    return assessment


def get_student_released_assessment(
    *,
    student_id: Any,
    assessment: Any,
    viewer: Optional[AcademicUserLike],
) -> Any:
    """Return a released assessment only to the owning student or authorized academics."""
    # BR-131: students may view their own released assessments. They should not
    # automatically see other students' private details.
    if assessment is None:
        raise AssessmentNotFoundError("Assessment not found")
    viewer_id = getattr(viewer, "id", None)
    if viewer_id is None:
        raise AssessmentVisibilityError("Authenticated viewer identity is required")

    if getattr(assessment, "student_id", None) == viewer_id:
        if is_authorized_academic_user(viewer):
            return assessment
        if getattr(assessment, "released", False):
            return {
                "id": getattr(assessment, "id", None),
                "student_id": getattr(assessment, "student_id", None),
                "course_id": getattr(assessment, "course_id", None),
                "class_id": getattr(assessment, "class_id", None),
                "score": getattr(assessment, "score", None),
                "released": True,
                "status": getattr(assessment, "status", None),
            }
        raise AssessmentVisibilityError("Assessment has not been released for student viewing")

    if student_id != getattr(assessment, "student_id", None):
        raise AssessmentVisibilityError("Requested student does not match the assessment")
    if is_authorized_academic_user(viewer):
        return assessment

    raise AssessmentVisibilityError("Student cannot view another student's assessment")


def record_assessment_decision(
    *,
    assessment: Any,
    actor: Optional[AcademicUserLike],
    judgment: str,
    audit_logger: Optional[Any] = None,
) -> Dict[str, Any]:
    """Capture a decision as a record without auto-judging student character."""
    # BR-133: the platform records assessment decisions but must not infer
    # subjective judgments such as "lazy" or "serious" from the data.
    if assessment is None:
        raise AssessmentNotFoundError("Assessment not found")
    if actor is None or not is_authorized_academic_user(actor):
        raise UnauthorizedAssessmentActionError("Only authorized academic users can record assessment decisions")
    if not judgment or not str(judgment).strip():
        raise AssessmentError("Judgment text is required")

    outcome = {
        "assessment_id": getattr(assessment, "id", None),
        "student_id": getattr(assessment, "student_id", None),
        "actor_id": getattr(actor, "id", None),
        "judgment": judgment,
        "recorded_at": utc_now().isoformat(),
    }

    # BR-132, BR-210: assessment decisions are always auditable.
    _audit(
        audit_logger,
        action="assessment_decision_recorded",
        assessment=assessment,
        actor=actor,
        details={"judgment": judgment},
    )

    return outcome
