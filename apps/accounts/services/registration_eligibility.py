"""Server-side resolution of a public registration request.

This module is the only place that decides which role a self-registering
applicant receives. The client may *ask* for an account type; it can never
grant itself a role. Nothing here trusts a payload field for authorization.

What is genuinely verifiable today
----------------------------------
The repository has **no authoritative university registry** for either
population -- no student registry, no staff roster, no institutional email
policy. So this service does not pretend to prove anybody is a real student or
a real member of staff. It enforces only what the system actually knows:

* the account type is one the platform recognises;
* an administrator can never be self-assigned (the value is simply not
  reachable from this path);
* the department named exists, so a student cannot enrol themselves into an
  invented department and thereby become eligible for its courses;
* the level is one the catalogue actually offers;
* identity fields (matricule, staffid) are unique across accounts, so an
  applicant cannot occupy an existing person's identity;
* email ownership is proven separately by the one-time-code flow.

Lecturer applicants are always created PENDING. Because no staff registry
exists, there is nothing to verify them against, and a PENDING account holds
no teaching privileges until an administrator approves it (see
``is_authorized_academic_user``).
"""

from __future__ import annotations

from typing import Any, Optional

from apps.academic.models import Course, Department
from apps.accounts.models import User

#: Values a public applicant may request. Deliberately excludes every
#: administrative role: an applicant cannot reach ADMINISTRATOR through this
#: path at all, so a forged payload cannot select one.
ACCOUNT_TYPES = ("student", "lecturer")


class EligibilityError(ValueError):
    """The request cannot be resolved to a role, or its identity conflicts."""

    code = "REGISTRATION_NOT_PERMITTED"

    def __init__(self, message: str, *, code: Optional[str] = None):
        super().__init__(message)
        if code:
            self.code = code


def normalize_account_type(value: Any) -> str:
    """Return the requested account type, rejecting anything unrecognised.

    A missing or unknown value is an error rather than a silent default: a
    caller sending ``account_type: "admin"`` must hear about it, not be quietly
    treated as a student.
    """
    text = str(value or "").strip().lower()
    if text not in ACCOUNT_TYPES:
        raise EligibilityError(
            "Choose either a student or a lecturer account.",
            code="INVALID_ACCOUNT_TYPE",
        )
    return text


def resolve_role(account_type: Any) -> str:
    """Map a requested account type onto the role the server will store."""
    if normalize_account_type(account_type) == "lecturer":
        return User.Role.LECTURER
    return User.Role.STUDENT


def resolve_lecturer_approval(account_type: Any) -> Optional[str]:
    """Lecturer applicants start PENDING; everyone else is not applicable."""
    if normalize_account_type(account_type) == "lecturer":
        return User.LecturerApproval.PENDING
    return None


def validate_department(department_id: Any, *, required: bool) -> Optional[Department]:
    """Resolve a department that actually exists.

    ``None`` is returned when no department was supplied and none is required
    (lecturers are not tied to one department at registration time).
    """
    if department_id in (None, ""):
        if required:
            raise EligibilityError("Select your department.", code="DEPARTMENT_REQUIRED")
        return None
    try:
        department = Department.objects.filter(pk=department_id).first()
    except (ValueError, TypeError):
        raise EligibilityError("Select a valid department.", code="INVALID_DEPARTMENT") from None
    if department is None:
        raise EligibilityError("Select a valid department.", code="INVALID_DEPARTMENT")
    return department


def validate_level(level: Any, *, required: bool) -> str:
    """Normalize a level and, when supplied, require the catalogue to offer it.

    No hardcoded list: the accepted values are read from the courses the
    institution actually runs, so a new level needs no code change.
    """
    text = str(level or "").strip().upper()
    if not text:
        if required:
            raise EligibilityError("Select your level.", code="LEVEL_REQUIRED")
        return ""
    offered = {
        str(value).strip().upper()
        for value in Course.objects.exclude(level="").values_list("level", flat=True).distinct()
    }
    if offered and text not in offered:
        raise EligibilityError("Select a valid level.", code="INVALID_LEVEL")
    return text


def validate_identity_free(matricule: Any = None, staffid: Any = None) -> None:
    """Refuse an applicant whose identity identifier is already taken.

    This is the impersonation check. It stops a new applicant from claiming an
    existing student's matricule or an existing lecturer's staff id, which
    would otherwise let them share -- or shadow -- somebody's identity.
    """
    matricule_text = str(matricule or "").strip()
    if matricule_text:
        if User.objects.filter(matricule__iexact=matricule_text).exists():
            raise EligibilityError(
                "That matricule number is already registered.",
                code="MATRICULE_TAKEN",
            )
    staffid_text = str(staffid or "").strip()
    if staffid_text:
        if User.objects.filter(staffid__iexact=staffid_text).exists():
            raise EligibilityError(
                "That staff number is already registered.",
                code="STAFFID_TAKEN",
            )