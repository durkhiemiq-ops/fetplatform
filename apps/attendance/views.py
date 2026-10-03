from django.core.cache import cache
from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.attendance.models import (
    AttendanceCheckpoint,
    AttendanceRecord,
    AttendanceSession,
)
from apps.attendance.services.attendance_service import (
    AlreadyMarkedError,
    AttendanceError,
    CheckpointNotEligibleError,
    ClassSessionNotFoundError,
    CorrectionAuthorizationError,
    LecturerNotAuthorizedError,
    NotEligibleError,
    SessionAlreadyActiveError,
    SessionExpiredError,
    SessionNotActiveError,
    TokenStudentMismatchError,
    close_attendance_session,
    correct_attendance,
    eligible_students_for_session,
    evaluate_repeated_failure,
    generate_checkpoint_token,
    list_review_flags,
    refresh_session_status,
    scan_attendance,
    select_checkpoints,
    start_attendance_session,
    start_flexible_attendance_session,
)
from apps.attendance.utils.qr_tokens import (
    InvalidTokenError,
    TokenAlreadyUsedError,
    TokenExpiredError,
    get_qr_token_ttl_seconds,
)
from core.academic_access import is_admin_user, is_authorized_academic_user

from .serializers import (
    AttendanceScanSerializer,
    AttendanceSessionCreateSerializer,
    CheckpointSelectSerializer,
    CorrectionCreateSerializer,
    FlexibleAttendanceStartSerializer,
)


def _error(message, code, http_status):
    return Response({"success": False, "error": {"code": code, "message": message}}, status=http_status)


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


def _user_name(user):
    if user is None:
        return ""
    return f"{user.first_name} {user.last_name}".strip() or user.username or str(user.id)[:8]


class AttendanceScanView(APIView):
    permission_classes = [IsAuthenticated]
    # Dedicated app-level rate limit: closes audit item 29's gateway-only
    # dependency.  ScopedRateThrottle keys on the authenticated student, so
    # one student's hammering cannot exhaust another's allowance.  A gateway
    # limit stays recommended as defence in depth, but the endpoint is no
    # longer unsafe without one.
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "attendance-scan"

    def post(self, request):
        serializer = AttendanceScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = scan_attendance(authenticated_student=request.user, token=serializer.validated_data["token"])
        except TokenExpiredError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="TOKEN_EXPIRED",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "TOKEN_EXPIRED", status.HTTP_404_NOT_FOUND)
        except TokenAlreadyUsedError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="TOKEN_ALREADY_USED",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "TOKEN_ALREADY_USED", status.HTTP_409_CONFLICT)
        except InvalidTokenError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="INVALID_TOKEN",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "INVALID_TOKEN", status.HTTP_404_NOT_FOUND)
        except TokenStudentMismatchError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="TOKEN_STUDENT_MISMATCH",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "TOKEN_STUDENT_MISMATCH", status.HTTP_403_FORBIDDEN)
        except NotEligibleError as exc:
            return _error(str(exc), "NOT_ELIGIBLE", status.HTTP_403_FORBIDDEN)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", status.HTTP_409_CONFLICT)
        except AlreadyMarkedError as exc:
            return _error(str(exc), "ALREADY_MARKED", status.HTTP_409_CONFLICT)
        except AttendanceError as exc:
            return _error(str(exc), "ATTENDANCE_REJECTED", status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "success": True,
                "data": {
                    "attendance_record_id": str(record.id),
                    "attendance_session_id": str(record.attendance_session_id),
                    "recorded_at": record.recorded_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )


def _session_base(user, pk):
    """Load a session row the caller is allowed to manage/read, else None."""
    session = (
        AttendanceSession.objects.select_related("class_session__course", "lecturer")
        .filter(id=pk)
        .first()
    )
    if session is None:
        return None
    refresh_session_status(session)
    if not (is_admin_user(user) or str(session.lecturer_id) == str(user.id)):
        return None
    return session


def _serialize_correction(correction):
    # §67: internal corrector id is not consumed by the UI; keep the human
    # "who" and the audit facts only.
    return {
        "id": str(correction.id),
        "reason": correction.reason,
        "old_status": correction.old_status,
        "new_status": correction.new_status,
        "corrected_by_name": _user_name(correction.corrected_by),
        "created_at": correction.created_at,
    }


def _serialize_record(record, include_corrections=False):
    # §67: FK uuids (session/checkpoint/student) are not consumed by the UI;
    # keep the presentation fields plus the correction envelope.
    data = {
        "id": str(record.id),
        "attendance_session": str(record.attendance_session_id),
        "student": str(record.student_id),
        "student_name": _user_name(record.student),
        "student_email": record.student.email,
        "recorded_at": record.recorded_at,
        "status": record.status,
        "verification_method": record.verification_method,
    }
    if include_corrections:
        data["corrections"] = [_serialize_correction(c) for c in record.corrections.all()]
        data["corrected"] = bool(data["corrections"])
    else:
        data["corrected"] = record.corrections.exists() if hasattr(record, "corrections") else False
    return data


class AttendanceSessionListCreateView(APIView):
    """Session registry for academic users; students only ever scan."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may list attendance sessions.", "UNAUTHORIZED", 403)
        queryset = AttendanceSession.objects.select_related("class_session__course", "lecturer")
        if not is_admin_user(request.user):
            queryset = queryset.filter(lecturer=request.user)
        queryset = queryset.annotate(
            checkpoint_cnt=Count("checkpoints", distinct=True),
            record_cnt=Count("records", distinct=True),
        ).order_by("-started_at")
        rows = []
        for session in queryset:
            refresh_session_status(session)
            # §67: class_session/lecturer uuid and lecturer_name are not
            # consumed by the UI; course identity and counts carry the row.
            rows.append({
                "id": str(session.id),
                "course_code": session.class_session.course.code,
                "course_name": session.class_session.course.name,
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "checkpoints": session.checkpoint_cnt,
                "records": session.record_cnt,
            })
        return _success(rows)

    def post(self, request):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may start attendance sessions.", "UNAUTHORIZED", 403)
        serializer = AttendanceSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            session = start_attendance_session(
                actor=request.user,
                class_session_id=validated["class_session"],
                duration_seconds=validated.get("duration_seconds"),
            )
        except ClassSessionNotFoundError as exc:
            return _error(str(exc), "CLASS_NOT_FOUND", 404)
        except SessionAlreadyActiveError as exc:
            return _error(str(exc), "SESSION_ALREADY_ACTIVE", 409)
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        except AttendanceError as exc:
            return _error(str(exc), "INVALID_INPUT", 400)
        return _success(
            {
                # §67: the class_session uuid echoes the request body; the
                # frontend consumes only identity/status/timing.
                "id": str(session.id),
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
            },
            201,
        )


class FlexibleAttendanceStartView(APIView):
    """Start an attendance window from a server-owned course offering."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may start attendance sessions.", "UNAUTHORIZED", 403)
        serializer = FlexibleAttendanceStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = start_flexible_attendance_session(
                actor=request.user,
                offering_id=serializer.validated_data["offering_id"],
                duration_seconds=serializer.validated_data.get("duration_seconds"),
            )
        except ClassSessionNotFoundError:
            return _error("Course offering not found.", "NOT_FOUND", 404)
        except SessionAlreadyActiveError as exc:
            return _error(str(exc), "SESSION_ALREADY_ACTIVE", 409)
        except LecturerNotAuthorizedError:
            return _error("Course offering not found.", "NOT_FOUND", 404)
        except AttendanceError as exc:
            return _error(str(exc), "INVALID_INPUT", 400)
        return _success(
            {
                "id": str(session.id),
                "class_session": str(session.class_session_id),
                "course_code": session.class_session.course.code,
                "class_name": session.class_session.course.name,
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
            },
            201,
        )


class AttendanceSessionDetailView(APIView):
    """Full live view: checkpoints, marked records, corrections, roster."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may view attendance sessions.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)

        checkpoints = list(
            session.checkpoints.select_related("student").order_by("student__first_name", "student__last_name")
        )
        records = list(
            session.records.select_related("student")
            .prefetch_related("corrections__corrected_by")
            .order_by("recorded_at")
        )
        record_by_student = {str(record.student_id): record for record in records}

        checkpoint_rows = []
        for checkpoint in checkpoints:
            record = record_by_student.get(str(checkpoint.student_id))
            checkpoint_rows.append({
                "id": str(checkpoint.id),
                "student": str(checkpoint.student_id),
                "student_name": _user_name(checkpoint.student),
                "marked": record is not None,
            })

        eligible = [
            {
                "id": str(student.id),
                "first_name": student.first_name,
                "last_name": student.last_name,
                "username": student.username,
            }
            for student in eligible_students_for_session(session=session)
        ]

        return _success(
            {
                "id": str(session.id),
                "course_code": session.class_session.course.code,
                "course_name": session.class_session.course.name,
                "status": session.status,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "checkpoints": checkpoint_rows,
                "records": [_serialize_record(r, include_corrections=True) for r in records],
                "eligible_students": eligible,
                "marked_count": len([c for c in checkpoint_rows if c["marked"]]),
                "total_checkpoints": len(checkpoint_rows),
                "record_count": len(records),
            }
        )


class AttendanceSessionCloseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may close attendance sessions.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        try:
            session = close_attendance_session(actor=request.user, session=session)
        except SessionNotActiveError as exc:
            return _error(str(exc), "SESSION_NOT_ACTIVE", 409)
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        return _success(
            {
                "id": str(session.id),
                "status": session.status,
            }
        )


class AttendanceCheckpointSelectView(APIView):
    """BR-050/051/053: lecturer confirms who is present and becomes a checkpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may select checkpoints.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        serializer = CheckpointSelectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            checkpoints = select_checkpoints(
                lecturer=request.user,
                session=session,
                student_ids=serializer.validated_data["student_ids"],
            )
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        except (CheckpointNotEligibleError, AttendanceError) as exc:
            return _error(str(exc), "CHECKPOINT_REJECTED", 400)
        return _success(
            {
                # §67: the owning session uuid is redundant here — the caller
                # just addressed the session in the URL.
                "checkpoints": [
                    {
                        "id": str(checkpoint.id),
                        "student": str(checkpoint.student_id),
                        "student_name": _user_name(checkpoint.student),
                    }
                    for checkpoint in checkpoints
                ]
            },
            201,
        )


class AttendanceCheckpointTokenView(APIView):
    """The lecturer's QR generator: one short-TTL token per confirmed checkpoint."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may issue QR tokens.", "UNAUTHORIZED", 403)
        checkpoint = AttendanceCheckpoint.objects.select_related(
            "attendance_session", "student"
        ).filter(id=pk).first()
        if checkpoint is None:
            return _error("Checkpoint not found.", "NOT_FOUND", 404)
        try:
            token = generate_checkpoint_token(lecturer=request.user, checkpoint=checkpoint)
        except LecturerNotAuthorizedError as exc:
            # §25: a non-owner must be indistinguishable from a missing
            # checkpoint — same shape, same code.
            return _error("Checkpoint not found.", "NOT_FOUND", 404)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        # §67: the frontend consumes only the token and its TTL; internal
        # checkpoint/session/student uuids stay server-side.
        return _success(
            {
                "token": token,
                "ttl_seconds": get_qr_token_ttl_seconds(),
            },
            201,
        )


class AttendanceRecordListView(APIView):
    """Students see their own history; academics see their sessions' records."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get("session")

        if is_authorized_academic_user(request.user):
            base = AttendanceRecord.objects.select_related(
                "student", "attendance_session__class_session__course"
            ).prefetch_related("corrections__corrected_by")
            if session_id:
                session = _session_base(request.user, session_id)
                if session is None:
                    return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
                queryset = base.filter(attendance_session=session).order_by("-recorded_at")
            elif is_admin_user(request.user):
                queryset = base.order_by("-recorded_at")
            else:
                queryset = base.filter(
                    attendance_session__lecturer=request.user
                ).order_by("-recorded_at")
        else:
            queryset = (
                AttendanceRecord.objects.filter(student=request.user)
                .select_related("attendance_session__class_session__course")
                .prefetch_related("corrections__corrected_by")
                .order_by("-recorded_at")
            )

        rows = []
        for record in queryset[:500]:
            course = record.attendance_session.class_session.course
            # §67: session/class/student uuids are not rendered by the UI;
            # course codes, names and the correction envelope carry the row.
            rows.append(
                {
                    "id": str(record.id),
                    "course_code": course.code,
                    "course_name": course.name,
                    "student_name": _user_name(record.student),
                    "recorded_at": record.recorded_at,
                    "status": "PRESENT",
                    "corrected": record.corrections.exists(),
                    "correction_count": record.corrections.count(),
                }
            )
        return _success(rows)


class AttendanceCorrectionView(APIView):
    """BR-042: change status through an immutable correction event."""

    permission_classes = [IsAuthenticated]

    def _correct(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may correct attendance.", "UNAUTHORIZED", 403)
        record = (
            AttendanceRecord.objects.filter(id=pk)
            .select_related("attendance_session__lecturer", "student")
            .first()
        )
        if record is None:
            return _error("Attendance record not found.", "NOT_FOUND", 404)
        # §25 + BR-042: the corrector is the record's session lecturer or an
        # administrator.  Any other caller (with or without a reason) must
        # receive exactly the not-found shape — probing must not reveal that
        # the record exists.
        if not is_admin_user(request.user) and str(record.attendance_session.lecturer_id) != str(request.user.id):
            return _error("Attendance record not found.", "NOT_FOUND", 404)
        serializer = CorrectionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            correction = correct_attendance(
                record=record,
                lecturer=request.user,
                new_status=serializer.validated_data["status"],
                reason=serializer.validated_data["reason"],
            )
        except CorrectionAuthorizationError as exc:
            # Defensive: the pre-check above already closed this path; keep
            # the same non-existence shape in case it ever fires.
            return _error("Attendance record not found.", "NOT_FOUND", 404)
        except AttendanceError as exc:
            return _error(str(exc), "INVALID_INPUT", 400)
        return _success(
            {
                **_serialize_record(record, include_corrections=True),
                "correction": _serialize_correction(correction),
            }
        )

    def patch(self, request, pk):
        return self._correct(request, pk)

    def post(self, request, pk):
        return self._correct(request, pk)


class AttendanceReviewView(APIView):
    """BR-064: 'Attendance Requiring Review' flags for the caller's classes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may review attendance flags.", "UNAUTHORIZED", 403)
        try:
            flags = list_review_flags(actor=request.user)
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        return _success(flags)
