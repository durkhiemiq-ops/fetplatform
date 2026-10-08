"""Read-only academic surfaces shared by the student and classroom pages.

Both views here are pure aggregations over models that already exist. Neither
invents data: a counter is zero when there is nothing to count, and an absent
value stays ``None`` rather than being filled with a plausible-looking default.

Scope rules are decided from the caller's role and their own records, never
from a request parameter, so no field in either request can name another
student, another lecturer, or another department.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academic.models import (
    ClassSchedule,
    CourseOffering,
    Enrollment,
    Semester,
)
from apps.announcements.models import Announcement
from apps.assessments.models import Assessment
from apps.files.models import LearningMaterial
from apps.projects.models import Project

from core.academic_access import is_admin_user, is_authorized_academic_user


def _success(data, status=200):
    return Response({"success": True, "data": data}, status=status)


def _error(message, code, status=400):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _iso(value):
    return value.isoformat() if value else None


def _course_of(offering):
    return offering.course if offering else None


def _lecturer_name(offering):
    lecturer = getattr(offering, "lecturer", None)
    if lecturer is None:
        return None
    return f"{lecturer.first_name} {lecturer.last_name}".strip() or lecturer.email


def _serialize_offering(
    offering,
    *,
    enrolled_students=None,
    materials_count=0,
    assignments_count=0,
    assessments_count=0,
    announcements_count=0,
):
    course = _course_of(offering)
    payload = {
        "offering_id": str(offering.pk) if offering else None,
        "course_offering_id": str(offering.pk) if offering else None,
        "course_id": str(course.pk) if course else None,
        "course_code": course.code if course else None,
        "course_title": course.name if course else None,
        "lecturer_name": _lecturer_name(offering),
        "lecturer": str(offering.lecturer_id) if offering else None,
        "semester": getattr(offering.semester, "name", None),
        "department": getattr(getattr(offering, "department", None), "name", None),
        "materials_count": materials_count,
        # The client reads this to open an assignment list. Assignment
        # persistence is not part of the converged MVP scope, so the honest
        # figure is 0 rather than a count of rows that do not exist.
        "assignments_count": assignments_count,
        "assessments_count": assessments_count,
        "announcements_count": announcements_count,
    }
    if enrolled_students is not None:
        payload["enrolled_students"] = enrolled_students
    return payload


def _materials_counts(offering_ids):
    counts = dict(
        LearningMaterial.objects.filter(course_offering_id__in=offering_ids)
        .values("course_offering_id")
        .annotate(n=Count("id"))
        .values_list("course_offering_id", "n")
    )
    return {str(k): v for k, v in counts.items()}


def _assessment_counts(offering_ids):
    counts = dict(
        Assessment.objects.filter(course__offerings__in=offering_ids)
        .values("course_id")
        .annotate(n=Count("id", distinct=True))
        .values_list("course_id", "n")
    )
    return {str(k): v for k, v in counts.items()}


def _announcement_counts(user_course_ids):
    counts = dict(
        Announcement.objects.filter(
            course_id__in=user_course_ids,
            is_published=True,
            is_archived=False,
        )
        .values("course_id")
        .annotate(n=Count("id"))
        .values_list("course_id", "n")
    )
    return {str(k): v for k, v in counts.items()}


class StudentAssessmentsView(APIView):
    """``GET /api/v1/students/me/assessments/`` — the student's own results.

    Reuses the same visibility rule as the assessments collection (BR-131):
    only *released* assessments that belong to this student are returned, and
    ``private_notes`` is suppressed on the student path. A draft result is not
    shown early, and no lecturer-only note ever leaves through this endpoint.

    Everything is keyed to the caller, so there is no parameter that can be
    turned into a read of somebody else's marks.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if getattr(user, "role", None) != "STUDENT":
            return _error(
                "This endpoint returns a student's own assessment results.",
                "FORBIDDEN",
                403,
            )

        # BR-131: released only, own records only.
        assessments = (
            Assessment.objects.filter(student=user, released=True)
            .select_related("course", "class_session", "created_by")
            .order_by("-created_at")
        )

        course_ids = {a.course_id for a in assessments if a.course_id}
        courses_by_id = {
            str(c.pk): {"code": c.code, "name": c.name}
            for c in _courses_for(course_ids)
        }

        results = []
        for assessment in assessments:
            course = courses_by_id.get(str(assessment.course_id) or "")
            results.append(
                {
                    "id": str(assessment.pk),
                    # Per-row attribution. The client renders the applicant
                    # beside the mark, and this value must come from the
                    # record rather than from anything in the request.
                    "student": str(assessment.student_id),
                    "course_id": str(assessment.course_id)
                    if assessment.course_id
                    else None,
                    "course_code": course["code"] if course else None,
                    "course_title": course["name"] if course else None,
                    "class_session_id": str(assessment.class_session_id)
                    if assessment.class_session_id
                    else None,
                    "score": str(assessment.score) if assessment.score is not None else None,
                    "status": assessment.status,
                    "released": assessment.released,
                    # Suppressed on the student path by design (BR-131); the
                    # key is present so the shape stays stable.
                    "private_notes": None,
                    "created_at": _iso(assessment.created_at),
                    "released_at": _iso(assessment.updated_at),
                }
            )

        # Keep the aggregate in one object so the page can render its summary
        # cards without a second request.
        total = len(results)
        scores = [
            float(r["score"])
            for r in results
            if r["score"] is not None
        ]
        summary = {
            "total_assessments": total,
            "released_count": total,
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "courses": [
                {"id": cid, "code": c["code"], "name": c["name"]}
                for cid, c in courses_by_id.items()
            ],
        }
        return _success({"assessments": results, "summary": summary})


def _courses_for(course_ids):
    if not course_ids:
        return []
    from apps.academic.models import Course

    return Course.objects.filter(pk__in=course_ids)


class ClassroomAvailableCoursesView(APIView):
    """``GET /api/v1/classrooms/available-courses/`` — offerings teachable here.

    A lecturer (or an administrator) sees the offerings they are attached to.
    Nothing is returned to a student: this is the *create-a-classroom* picker,
    not a course catalogue.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = getattr(user, "role", None)

        if role == "STUDENT":
            # A student cannot open a classroom; answer with an empty list
            # rather than leaking which offerings exist.
            return _success({"semester": None, "courses": []})

        queryset = (
            CourseOffering.objects.select_related(
                "course", "semester", "department", "lecturer"
            )
            .order_by("course__code")
        )
        if is_admin_user(user):
            pass
        elif role == "LECTURER" and is_authorized_academic_user(user):
            queryset = queryset.filter(lecturer=user)
        else:
            # Students, staff of other kinds, and lecturers whose approval is
            # still PENDING or was REJECTED all land here. The role label alone
            # is not authority to see an offering.
            return _success({"semester": None, "courses": []})

        semester = _active_semester()
        offerings = list(queryset)
        materials = _materials_counts([o.pk for o in offerings])

        courses = [
            _serialize_offering(
                offering,
                materials_count=materials.get(str(offering.pk), 0),
            )
            for offering in offerings
        ]
        return _success({"semester": getattr(semester, "name", None), "courses": courses})


def _active_semester():
    return (
        Semester.objects.filter(is_current=True, status="ACTIVE").order_by("name").first()
        or Semester.objects.filter(is_current=True).order_by("name").first()
    )


class ClassroomListView(APIView):
    """``GET /api/v1/classrooms/`` — the caller's classrooms.

    Students get the offerings they are enrolled in, with the counters their
    card renders. Staff get the offerings they teach, with the staffing
    figures the staff card renders instead. The two shapes are deliberately
    different because the two cards show different things; the endpoint never
    mixes them, so a student cannot reach a staff-shaped payload.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        semester = _active_semester()
        role = getattr(user, "role", None)

        if role == "STUDENT":
            return _success(self._student_body(user, semester))
        if is_admin_user(user):
            return _success(self._staff_body(user, semester, is_admin=True))
        if role == "LECTURER" and is_authorized_academic_user(user):
            return _success(self._staff_body(user, semester, is_admin=False))
        # Neither a student nor an approved member of teaching staff: an empty
        # payload, so an unapproved lecturer's application status is not
        # confirmed or denied by what comes back.
        return _success({"semester": getattr(semester, "name", None), "courses": []})

    def _student_body(self, user, semester):
        offerings = list(
            CourseOffering.objects.filter(
                enrollments__student=user,
                enrollments__is_active=True,
                enrollments__deleted_at__isnull=True,
            )
            .select_related("course", "semester", "department", "lecturer")
            .distinct()
            .order_by("course__code")
        )
        if semester is not None:
            offerings = [
                o for o in offerings if o.semester_id == semester.pk
            ] or offerings

        course_ids = {o.course_id for o in offerings}
        materials = _materials_counts([o.pk for o in offerings])
        announcements = _announcement_counts(course_ids)

        courses = [
            _serialize_offering(
                offering,
                materials_count=materials.get(str(offering.pk), 0),
                announcements_count=announcements.get(str(offering.course_id), 0),
            )
            for offering in offerings
        ]
        return {"semester": getattr(semester, "name", None), "courses": courses}

    def _staff_body(self, user, semester, *, is_admin):
        queryset = CourseOffering.objects.select_related(
            "course", "semester", "department", "lecturer"
        ).order_by("course__code")
        if is_admin:
            pass
        else:
            queryset = queryset.filter(lecturer=user)

        offerings = list(queryset)
        if semester is not None:
            scoped = [o for o in offerings if o.semester_id == semester.pk]
            offerings = scoped or offerings

        offering_ids = [o.pk for o in offerings]
        materials = _materials_counts(offering_ids)
        assessments = _assessment_counts(offering_ids)
        enrollments = _enrollment_counts(offering_ids)

        courses = []
        for offering in offerings:
            courses.append(
                _serialize_offering(
                    offering,
                    enrolled_students=enrollments.get(str(offering.pk), 0),
                    materials_count=materials.get(str(offering.pk), 0),
                    assessments_count=assessments.get(str(offering.course_id), 0),
                )
            )
        return {"semester": getattr(semester, "name", None), "courses": courses}


def _enrollment_counts(offering_ids):
    """One grouped COUNT for every offering on the staff card.

    The per-row ``_enrollment_count`` issued one query per offering; with the
    same filter so the figure is unchanged.
    """
    counts = dict(
        Enrollment.objects.filter(
            course_offering_id__in=offering_ids,
            is_active=True,
            deleted_at__isnull=True,
        )
        .values("course_offering_id")
        .annotate(n=Count("id"))
        .values_list("course_offering_id", "n")
    )
    return {str(k): v for k, v in counts.items()}


def _enrollment_count(offering_id):
    return _enrollment_counts([offering_id]).get(str(offering_id), 0)
