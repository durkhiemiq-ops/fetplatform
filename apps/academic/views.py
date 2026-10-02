"""Read endpoints for the academic module (frontend sync).

The frontend ACADEMIC_ENDPOINTS contract expects
/api/v1/{faculties,departments,courses}/ — these views fulfil it with the
project-standard {success, data, error} envelope.  Reads are open to any
authenticated user; school-year/semester writes are administrator-only.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.academic_access import is_admin_user
from core.audit import write_audit_entry

from apps.accounts.models import User

from .models import ClassSession, Course, Department, Enrollment, Faculty, SchoolYear, Semester
from .serializers import (
    ClassSessionSerializer,
    CourseSerializer,
    DepartmentSerializer,
    EnrollmentCreateSerializer,
    FacultySerializer,
    SchoolYearSerializer,
    SemesterSerializer,
)
from .services.enrollment_service import (
    AlreadyEnrolledError,
    CourseNotFoundError,
    EnrollmentError,
    NotEnrolledError,
    StudentNotFoundError,
    drop_student_from_course,
    enroll_student_in_course,
)


def _success_response(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


def _error_response(code, message, http_status):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


class FacultyListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        faculties = Faculty.objects.all()
        return _success_response(FacultySerializer(faculties, many=True).data)


class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        departments = Department.objects.select_related("faculty")
        return _success_response(DepartmentSerializer(departments, many=True).data)


class CourseListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        courses = Course.objects.select_related("department__faculty")
        return _success_response(CourseSerializer(courses, many=True).data)


class ClassSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = ClassSession.objects.select_related("course", "lecturer")
        return _success_response(ClassSessionSerializer(sessions, many=True).data)


class SchoolYearListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success_response(
            SchoolYearSerializer(SchoolYear.objects.all(), many=True).data
        )

    def post(self, request):
        if not is_admin_user(request.user):
            return _error_response(
                "UNAUTHORIZED", "Only administrators manage school years.", 403
            )
        serializer = SchoolYearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year = SchoolYear.objects.create(**serializer.validated_data)
        return _success_response(SchoolYearSerializer(year).data, 201)


class SemesterListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        semesters = Semester.objects.select_related("school_year")
        return _success_response(SemesterSerializer(semesters, many=True).data)

    def post(self, request):
        if not is_admin_user(request.user):
            return _error_response(
                "UNAUTHORIZED", "Only administrators manage semesters.", 403
            )
        serializer = SemesterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        semester = Semester.objects.create(**serializer.validated_data)
        return _success_response(SemesterSerializer(semester).data, 201)


class SemesterUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin_user(request.user):
            return _error_response(
                "UNAUTHORIZED", "Only administrators manage semesters.", 403
            )
        semester = Semester.objects.filter(pk=pk).first()
        if semester is None:
            return _error_response("NOT_FOUND", "Semester not found.", 404)
        serializer = SemesterSerializer(
            semester, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()  # model.save() keeps at most one is_current semester
        return _success_response(SemesterSerializer(semester).data)


def _enrollment_authorized(*, actor, student_id, action):
    """BR-010/BR-011/BR-013: a student may manage their own enrollment; an
    administrator may manage any student's. Lecturers may not — enrollment is
    not an attendance action."""
    if actor is None:
        return False
    if is_admin_user(actor):
        return True
    return (
        str(getattr(actor, "id", "")) == str(student_id)
        and str(getattr(actor, "role", "")).upper() == "STUDENT"
    )


class EnrollmentListCreateView(APIView):
    """GET  /academic/enrollments/ — the caller's own active enrollments.
    POST /academic/enrollments/ — enroll the caller in a course.

    BR-012: the course roster is defined by current enrollment, so a student
    needs to read their own set to render "My Courses".  The read is scoped to
    request.user; there is no parameter that can name another account (§25).

    BR-010: students enroll in courses; BR-011/BR-013: an active enrollment is
    the default source of class eligibility for FUTURE classes.  The enrollment
    row is the sole source of attendance eligibility, so this endpoint is what
    the frontend's Enrol/Drop control must call.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = Enrollment.objects.filter(student=request.user, is_active=True).select_related("course")
        return _success_response(
            [
                {
                    "id": str(row.id),
                    "course": str(row.course_id),
                    "course_code": row.course.code,
                    "course_name": row.course.name,
                    "is_active": row.is_active,
                    "status": row.status,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ]
        )

    def post(self, request):
        serializer = EnrollmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student_id = serializer.validated_data.get("student") or request.user.id
        course_id = serializer.validated_data["course"]
        try:
            record = enroll_student_in_course(
                student_id=student_id,
                course_id=course_id,
                EnrollmentModel=Enrollment,
                StudentModel=User,
                CourseModel=Course,
                actor_id=request.user.id,
                authorization_checker=lambda actor_id, student_id, course_id, action: (
                    _enrollment_authorized(
                        actor=request.user, student_id=student_id, action=action
                    )
                ),
            )
        except EnrollmentError as exc:
            # A duplicate enrollment is a conflict, not a permission problem,
            # and must be distinguishable from both.
            if isinstance(exc, AlreadyEnrolledError):
                return _error_response("ALREADY_ENROLLED", str(exc), 409)
            if isinstance(exc, (StudentNotFoundError, CourseNotFoundError)):
                return _error_response("NOT_FOUND", str(exc), 404)
            return _error_response("UNAUTHORIZED", str(exc), 403)

        # BR-210: enrollment changes a student's eligibility for future
        # attendance, so it is a significant academic action.
        write_audit_entry(
            action="course_enrolled",
            resource_type="enrollment",
            resource_id=record.id,
            actor_id=request.user.id,
            details={"course_id": str(course_id), "student_id": str(student_id)},
        )
        return _success_response(
            {"id": str(record.id), "course": str(course_id), "is_active": record.is_active},
            201,
        )


class EnrollmentDropView(APIView):
    """DELETE /academic/enrollments/<course_id>/ — end future eligibility.

    BR-014/BR-015: dropping deactivates the enrollment; it never deletes the row
    or any prior attendance/assessment history.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, course_id):
        # A non-administrator may only drop their OWN enrollment. Honouring a
        # client-supplied `?student=` for anyone else would let a student forge
        # a target and then receive a 404 that confirms the peer's state — so the
        # parameter is validated, not ignored.
        requested = request.query_params.get("student")
        if requested and not is_admin_user(request.user):
            return _error_response(
                "UNAUTHORIZED",
                "Only administrators may drop another student's enrollment.",
                403,
            )
        student_id = requested or request.user.id
        try:
            record = drop_student_from_course(
                student_id=student_id,
                course_id=course_id,
                EnrollmentModel=Enrollment,
                actor_id=request.user.id,
                authorization_checker=lambda actor_id, student_id, course_id, action: (
                    _enrollment_authorized(
                        actor=request.user, student_id=student_id, action=action
                    )
                ),
            )
        except EnrollmentError as exc:
            if isinstance(exc, NotEnrolledError):
                return _error_response("NOT_ENROLLED", str(exc), 404)
            if isinstance(exc, (StudentNotFoundError, CourseNotFoundError)):
                return _error_response("NOT_FOUND", str(exc), 404)
            return _error_response("UNAUTHORIZED", str(exc), 403)

        write_audit_entry(
            action="course_dropped",
            resource_type="enrollment",
            resource_id=record.id,
            actor_id=request.user.id,
            details={"course_id": str(course_id), "student_id": str(student_id)},
        )
        return _success_response(
            {"id": str(record.id), "course": str(course_id), "is_active": record.is_active}
        )
