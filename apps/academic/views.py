"""Read endpoints for the academic module (frontend sync).

The frontend ACADEMIC_ENDPOINTS contract expects
/api/v1/{faculties,departments,courses}/ — these views fulfil it with the
project-standard {success, data, error} envelope.  Reads are open to any
authenticated user; school-year/semester writes are administrator-only.
"""

from django.db.models import Q

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.academic_access import is_admin_user, is_authorized_academic_user

from apps.accounts.models import User

from .models import (
    ClassSchedule, ClassSession, Course, CourseOffering, Department,
    Enrollment, Faculty, SchoolYear, Semester,
)
from .serializers import (
    ClassDefinitionCreateSerializer,
    ClassDefinitionSerializer,
    ClassScheduleCreateSerializer,
    ClassScheduleSerializer,
    ClassSessionSerializer,
    CourseOfferingSerializer,
    CourseSerializer,
    DepartmentCreateSerializer,
    DepartmentSerializer,
    EnrollmentCreateSerializer,
    FacultySerializer,
    SchoolYearSerializer,
    SemesterSerializer,
    StudentRegistrationSerializer,
)
from .services.calendar_service import (
    SemesterActivationConflictError,
    SemesterNotFoundError,
    activate_semester,
    create_semester,
    update_semester,
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
from .services.registration_service import (
    RegistrationError,
    eligible_offerings,
    register_student,
)
from .services.structure_service import (
    AcademicStructureAuthorizationError,
    AcademicStructureConflictError,
    AcademicStructureError,
    archive_class_schedule,
    create_class_definition,
    create_class_schedule,
    create_course_offering,
    create_department,
    create_school_year,
    update_course_offering,
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


def _create_department_response(request):
    if not is_admin_user(request.user):
        return _error_response(
            "FORBIDDEN", "Only administrators create departments.", 403
        )
    serializer = DepartmentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        department = create_department(
            actor=request.user,
            **serializer.validated_data,
        )
    except AcademicStructureAuthorizationError as exc:
        return _error_response("FORBIDDEN", str(exc), 403)
    except AcademicStructureConflictError as exc:
        return _error_response("CONFLICT", str(exc), 409)
    except AcademicStructureError as exc:
        return _error_response("INVALID_INPUT", str(exc), 400)
    return _success_response(DepartmentSerializer(department).data, 201)


class DepartmentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        departments = Department.objects.select_related("faculty")
        return _success_response(DepartmentSerializer(departments, many=True).data)

    def post(self, request):
        return _create_department_response(request)


class PublicDepartmentListView(APIView):
    """Department names and codes for the public sign-up form.

    Anonymous, and deliberately narrow: an unauthenticated caller may read the
    department list only because they cannot choose a department at
    registration without it (the sign-up form populates this select before any
    account exists). Only ``id``, ``name``, ``code`` and the faculty name are
    returned -- no staff, no enrolment counts, no course or student data.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        rows = Department.objects.select_related("faculty").order_by("name")
        return _success_response(
            [
                {
                    "id": str(row.pk),
                    "name": row.name,
                    "code": row.code or "",
                    "faculty": row.faculty.name if row.faculty_id else "",
                }
                for row in rows
            ]
        )


class CourseListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        courses = Course.objects.select_related("department__faculty")
        return _success_response(CourseSerializer(courses, many=True).data)


class ClassSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = ClassSession.objects.select_related(
            "course", "course_offering", "lecturer"
        )
        if is_admin_user(request.user):
            pass
        elif request.user.role == User.Role.LECTURER:
            if not is_authorized_academic_user(request.user):
                sessions = sessions.none()
            else:
                sessions = sessions.filter(lecturer=request.user)
        elif request.user.role == User.Role.STUDENT:
            sessions = sessions.filter(
                Q(
                    course_offering__enrollments__student=request.user,
                    course_offering__enrollments__is_active=True,
                    course_offering__enrollments__status__iexact="active",
                )
                | Q(
                    course_offering__isnull=True,
                    course__enrollments__student=request.user,
                    course__enrollments__is_active=True,
                    course__enrollments__status__iexact="active",
                )
            ).distinct()
        else:
            sessions = sessions.none()
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
        year = create_school_year(
            actor=request.user,
            data=serializer.validated_data,
        )
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
        semester = create_semester(
            data=serializer.validated_data,
            actor_id=request.user.id,
        )
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
        semester = update_semester(
            semester_id=semester.pk,
            changes=serializer.validated_data,
            actor_id=request.user.id,
        )
        return _success_response(SemesterSerializer(semester).data)


class SemesterActivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_admin_user(request.user):
            return _error_response(
                "UNAUTHORIZED", "Only administrators activate semesters.", 403
            )
        try:
            semester = activate_semester(semester_id=pk, actor_id=request.user.id)
        except SemesterNotFoundError:
            return _error_response("NOT_FOUND", "Semester not found.", 404)
        except SemesterActivationConflictError as exc:
            return _error_response("CONFLICT", str(exc), 409)
        return _success_response(SemesterSerializer(semester).data)


def _offering_queryset_for(user):
    rows = CourseOffering.objects.select_related(
        "course", "department", "semester", "lecturer"
    )
    if is_admin_user(user):
        return rows
    if user.role == User.Role.LECTURER:
        if not is_authorized_academic_user(user):
            return rows.none()
        return rows.filter(lecturer=user)
    if user.role == User.Role.STUDENT:
        return rows.filter(
            enrollments__student=user, enrollments__is_active=True
        ).distinct()
    return rows.none()


class CourseOfferingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success_response(
            CourseOfferingSerializer(_offering_queryset_for(request.user), many=True).data
        )

    def post(self, request):
        if not is_admin_user(request.user):
            return _error_response("FORBIDDEN", "Only administrators create offerings.", 403)
        serializer = CourseOfferingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        offering = create_course_offering(
            actor=request.user,
            data=serializer.validated_data,
        )
        return _success_response(CourseOfferingSerializer(offering).data, 201)


class CourseOfferingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return _offering_queryset_for(request.user).filter(pk=pk).first()

    def get(self, request, pk):
        offering = self._get(request, pk)
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        return _success_response(CourseOfferingSerializer(offering).data)

    def patch(self, request, pk):
        if not is_admin_user(request.user):
            return _error_response("FORBIDDEN", "Only administrators update offerings.", 403)
        offering = CourseOffering.objects.filter(pk=pk).first()
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        serializer = CourseOfferingSerializer(offering, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        offering = update_course_offering(
            actor=request.user,
            offering=offering,
            changes=serializer.validated_data,
        )
        return _success_response(CourseOfferingSerializer(offering).data)


def _registration_error(exc):
    return _error_response(exc.code, str(exc), exc.status)


def _offering_summary(offering, enrolled_ids):
    return {
        "offering_id": str(offering.id),
        "course_code": offering.course.code,
        "course_title": offering.course.name,
        "credit_units": offering.course.credit_units,
        "lecturer_name": (
            f"{offering.lecturer.first_name} {offering.lecturer.last_name}".strip()
            if offering.lecturer else "TBA"
        ),
        "is_enrolled": offering.id in enrolled_ids,
    }


class StudentAvailableCoursesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            semester, offerings, scope = eligible_offerings(request.user)
        except RegistrationError as exc:
            return _registration_error(exc)
        enrolled_ids = set(Enrollment.objects.filter(
            student=request.user,
            course_offering__semester=semester,
            is_active=True,
        ).values_list("course_offering_id", flat=True))
        return _success_response({
            "semester": semester.name,
            "registration_deadline": semester.registration_deadline,
            # Displayed scope comes from the same administrator-owned profile
            # that gates enrollment, never from a value the student posted.
            "level": scope.level,
            "department": scope.department.name,
            "courses": [_offering_summary(row, enrolled_ids) for row in offerings],
        })


class StudentRegistrationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StudentRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            records = register_student(
                student=request.user,
                offering_ids=serializer.validated_data["offering_ids"],
            )
        except RegistrationError as exc:
            return _registration_error(exc)
        return _success_response({
            "registered_count": len(records),
            "errors": [],
            "enrollment_ids": [str(record.id) for record in records],
        }, 201)


class StudentMyCoursesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.STUDENT:
            return _error_response("FORBIDDEN", "Only students can access this endpoint.", 403)
        rows = Enrollment.objects.filter(
            student=request.user,
            is_active=True,
            course_offering__isnull=False,
        ).select_related(
            "course_offering__course", "course_offering__department",
            "course_offering__semester", "course_offering__lecturer",
        )
        enrolled_ids = {row.course_offering_id for row in rows}
        return _success_response([
            {
                **_offering_summary(row.course_offering, enrolled_ids),
                "enrollment_id": str(row.id),
                "department": row.course_offering.department.name,
                "semester": row.course_offering.semester.name,
                "materials_count": 0,
                "announcements_count": 0,
                "assignments_count": 0,
            }
            for row in rows
        ])


class LecturerMyCoursesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if (
            request.user.role != User.Role.LECTURER
            or not is_authorized_academic_user(request.user)
        ):
            return _error_response(
                "FORBIDDEN", "Only approved lecturers can access this endpoint.", 403
            )
        rows = CourseOffering.objects.filter(lecturer=request.user).select_related(
            "course", "department", "semester", "lecturer"
        )
        return _success_response(CourseOfferingSerializer(rows, many=True).data)


def _enrollment_authorized(*, actor, student_id, action):
    """BR-010/BR-011/BR-013 authorization for the course-level endpoint.

    Security note — why "enroll" is admin-only here
    -----------------------------------------------
    Self-enrollment is permitted, but only through the bounded offering path
    (``POST /students/me/register/`` -> ``registration_service.register_student``),
    which enforces department, level, active semester, registration deadline and
    offering/course status.

    This endpoint previously authorized a student on "is this my own id and am I
    a STUDENT" alone. Because it takes a bare ``course`` uuid with none of those
    checks, calling *this* route instead of the offering route granted full
    attendance eligibility for any course in the system -- and still worked
    after the registration deadline had passed. A gate is only as strong as the
    absence of a looser door, so self-service "enroll" no longer lives here.

    Dropping stays self-service: BR-014 lets a student end their own future
    eligibility, which cannot escalate.
    """
    if actor is None:
        return False
    if is_admin_user(actor):
        return True
    if str(action).lower() == "enroll":
        return False
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

        return _success_response(
            {"id": str(record.id), "course": str(course_id), "is_active": record.is_active}
        )


class DepartmentCreateView(APIView):
    """Compatibility alias for the frontend's explicit create route."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return _create_department_response(request)


class AdminStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return _error_response(
                "FORBIDDEN", "Only administrators may view platform statistics.", 403
            )
        active_semester = Semester.objects.filter(is_current=True).select_related(
            "school_year"
        ).first()
        current_offerings = CourseOffering.objects.none()
        if active_semester is not None:
            current_offerings = CourseOffering.objects.filter(
                semester=active_semester
            )
        authorized_lecturers = sum(
            1
            for lecturer in User.objects.filter(role=User.Role.LECTURER).iterator()
            if is_authorized_academic_user(lecturer)
        )
        return _success_response(
            {
                "total_students": User.objects.filter(
                    role=User.Role.STUDENT
                ).count(),
                "total_lecturers": authorized_lecturers,
                "total_courses": Course.objects.count(),
                "total_departments": Department.objects.count(),
                "total_offerings": current_offerings.count(),
                "total_enrollments": Enrollment.objects.filter(
                    course_offering__in=current_offerings,
                    is_active=True,
                ).count(),
                "active_semester": (
                    SemesterSerializer(active_semester).data
                    if active_semester is not None
                    else None
                ),
            }
        )


class CourseOfferingScheduleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _offering(self, request, offering_id):
        return _offering_queryset_for(request.user).filter(pk=offering_id).first()

    def get(self, request, offering_id):
        offering = self._offering(request, offering_id)
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        # The timetable surface shows weekly *slots*. A class definition that
        # has not been scheduled yet has no slot to render (and would put a
        # null day in front of the timetable component), so it is listed by
        # GET /course-offerings/{id}/classes/ instead rather than appearing
        # here as a half-formed row.
        schedules = ClassSchedule.objects.filter(
            course_offering=offering,
            is_active=True,
            day_of_week__isnull=False,
            start_time__isnull=False,
            end_time__isnull=False,
        ).select_related("course_offering__course", "lecturer")
        return _success_response(ClassScheduleSerializer(schedules, many=True).data)

    def post(self, request, offering_id):
        offering = self._offering(request, offering_id)
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        serializer = ClassScheduleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            schedule = create_class_schedule(
                actor=request.user,
                offering=offering,
                data=serializer.validated_data,
            )
        except AcademicStructureAuthorizationError as exc:
            return _error_response("FORBIDDEN", str(exc), 403)
        except AcademicStructureConflictError as exc:
            return _error_response("CONFLICT", str(exc), 409)
        except AcademicStructureError as exc:
            return _error_response("INVALID_INPUT", str(exc), 400)
        return _success_response(ClassScheduleSerializer(schedule).data, 201)


class CourseOfferingClassListCreateView(APIView):
    """``GET``/``POST`` on one offering's class definitions (API §22).

    Accepted project decision A. ``POST`` creates an academic class
    definition that belongs to an existing, caller-scoped course offering; it
    never creates a course, an offering, an enrollment row or a second student
    workspace. The offering comes from the URL and is resolved through
    :func:`_offering_queryset_for`, so a caller cannot aim this at an offering
    they do not own — an unrelated or unapproved lecturer gets the same 404 an
    unknown id produces, and the service re-checks scope server-side anyway.

    ``GET`` preserves whatever the offering's consumers need: it answers with
    class definitions (their own ids), never with substituted offering ids.
    """

    permission_classes = [IsAuthenticated]

    def _offering(self, request, offering_id):
        return _offering_queryset_for(request.user).filter(pk=offering_id).first()

    def get(self, request, offering_id):
        offering = self._offering(request, offering_id)
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        classes = ClassSchedule.objects.filter(
            course_offering=offering, is_active=True
        ).select_related("course_offering__course", "lecturer")
        return _success_response(ClassDefinitionSerializer(classes, many=True).data)

    def post(self, request, offering_id):
        offering = self._offering(request, offering_id)
        if offering is None:
            return _error_response("NOT_FOUND", "Course offering not found.", 404)
        serializer = ClassDefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            class_definition = create_class_definition(
                actor=request.user,
                offering=offering,
                data=serializer.validated_data,
            )
        except AcademicStructureAuthorizationError as exc:
            return _error_response("FORBIDDEN", str(exc), 403)
        except AcademicStructureConflictError as exc:
            return _error_response("CONFLICT", str(exc), 409)
        except AcademicStructureError as exc:
            return _error_response("INVALID_INPUT", str(exc), 400)
        return _success_response(ClassDefinitionSerializer(class_definition).data, 201)


class ClassScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        schedule = ClassSchedule.objects.filter(
            pk=pk,
            is_active=True,
            course_offering__in=_offering_queryset_for(request.user),
        ).select_related("course_offering__lecturer").first()
        if schedule is None:
            return _error_response("NOT_FOUND", "Class schedule not found.", 404)
        try:
            archive_class_schedule(actor=request.user, schedule=schedule)
        except AcademicStructureAuthorizationError as exc:
            return _error_response("FORBIDDEN", str(exc), 403)
        except AcademicStructureError:
            return _error_response("NOT_FOUND", "Class schedule not found.", 404)
        return _success_response({"id": str(schedule.pk), "is_active": False})
