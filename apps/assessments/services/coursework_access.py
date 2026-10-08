"""Authorization and scoping for the inferred coursework surface.

The coursework endpoints are all scoped to a course offering, and every write
is confined to the lecturer who owns that offering. Keeping that rule here —
rather than repeating a role test in each view — means there is one definition
of "may this person act on this offering", and one definition of "which
offering rows may this person even see". A view cannot accidentally widen a
queryset, because it is built by ``scoped_offerings`` rather than assembled
in place.

This is deliberately separate from :func:`is_offering_lecturer` in
``views.py``. That helper cannot be imported from here (it lives in the views
module, which imports this service), and re-deriving a second definition of
the same rule would let the two drift apart silently. ``views.py`` has been
updated to delegate to :func:`is_offering_lecturer` below.
"""

from django.db.models import QuerySet

from apps.academic.models import CourseOffering

from core.academic_access import (
    is_admin_user,
    is_authorized_academic_user,
)


def is_offering_lecturer(user, offering) -> bool:
    """True when ``user`` may act on ``offering``.

    Two conditions, both required:

    1. The user must be an *authorized* academic user. This consults the
       central lecturer-approval gate, so a lecturer whose application is
       still PENDING or was REJECTED is refused here even though their role
       says LECTURER. Role alone is not authority.
    2. The user must teach this specific offering, or be an administrator.

    A student is never authorized, regardless of any other attribute.
    """
    if user is None:
        return False
    if getattr(user, "role", None) == "STUDENT":
        return False
    if not is_authorized_academic_user(user):
        return False
    if is_admin_user(user):
        return True
    if offering is None:
        return False
    return offering.lecturer_id == user.pk


def scoped_offerings(user) -> QuerySet:
    """Offerings this user is allowed to **write** coursework against.

    Administrators see everything; lecturers see only their own; anyone else
    (students included) gets an empty set, because creating, editing and
    deleting coursework is a staff surface. The empty set is returned rather
    than raising so that a caller can filter uniformly and simply receive no
    rows.

    A lecturer whose approval is PENDING or REJECTED is treated as staff of
    no offering: the approval gate is consulted before any queryset is built,
    so an unapproved applicant cannot enumerate coursework by role alone.

    Reading is a different question and has its own scope — see
    :func:`scoped_offerings_for_read`. A student must be able to read the
    coursework of the courses they are enrolled in, or the assignments tab of
    a course page would render empty for every student in the system.
    """
    queryset = CourseOffering.objects.all()
    if user is None:
        return queryset.none()
    if is_admin_user(user):
        return queryset
    if getattr(user, "role", None) == "LECTURER" and is_authorized_academic_user(user):
        return queryset.filter(lecturer=user)
    return queryset.none()


def scoped_offerings_for_read(user) -> QuerySet:
    """Offerings whose coursework ``user`` may read.

    Staff scope exactly as :func:`scoped_offerings`. A student may read the
    offerings they are **actively enrolled** on, and no others: enrollment is
    the sole source of eligibility in this system, so a student who guessed an
    offering id still resolves nothing and is told only that it does not
    exist. An unapproved lecturer reads nothing, as on the write path.
    """
    from apps.academic.models import Enrollment

    queryset = CourseOffering.objects.all()
    if user is None:
        return queryset.none()
    if is_admin_user(user):
        return queryset
    if getattr(user, "role", None) == "LECTURER" and is_authorized_academic_user(user):
        return queryset.filter(lecturer=user)
    if getattr(user, "role", None) == "STUDENT":
        enrolled = Enrollment.objects.filter(
            student=user,
            is_active=True,
            deleted_at__isnull=True,
        ).exclude(course_offering__isnull=True).values_list("course_offering_id", flat=True)
        return queryset.filter(pk__in=list(enrolled))
    return queryset.none()
