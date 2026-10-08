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
from apps.accounts.models import User
from apps.attendance.services.attendance_service import (
    AlreadyMarkedError,
    AttendanceError,
    CheckpointNotEligibleError,
    ClassSessionNotFoundError,
    CorrectionAuthorizationError,
    LecturerNotAuthorizedError,
    ModeMismatchError,
    NotEligibleError,
    SelfScanRejectedError,
    SessionAlreadyActiveError,
    SessionExpiredError,
    SessionNotActiveError,
    auto_select_checkpoints,
    close_attendance_session,
    correct_attendance,
    eligible_students_for_session,
    evaluate_repeated_failure,
    expected_headcount,
    generate_checkpoint_token,
    generate_projected_token,
    list_review_flags,
    refresh_session_status,
    remove_checkpoint,
    scan_attendance,
    select_checkpoints,
    start_attendance_session,
    start_flexible_attendance_session,
    station_summary,
    station_token,
)
from apps.attendance.utils.qr_tokens import (
    InvalidTokenError,
    TokenExpiredError,
    get_qr_token_ttl_seconds,
)
from core.academic_access import is_admin_user, is_authorized_academic_user

from .serializers import (
    AttendanceScanSerializer,
    AttendanceSessionCreateSerializer,
    AutoSelectStationsSerializer,
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
        except SelfScanRejectedError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="SELF_SCAN_REJECTED",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "SELF_SCAN_REJECTED", status.HTTP_403_FORBIDDEN)
        except ModeMismatchError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="MODE_MISMATCH",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "MODE_MISMATCH", status.HTTP_409_CONFLICT)
        except InvalidTokenError as exc:
            evaluate_repeated_failure(
                cache_backend=cache, actor_id=request.user.id, failure_code="INVALID_TOKEN",
                request_ip=request.META.get("REMOTE_ADDR"),
            )
            return _error(str(exc), "INVALID_TOKEN", status.HTTP_404_NOT_FOUND)
        except NotEligibleError as exc:
            return _error(str(exc), "NOT_ELIGIBLE", status.HTTP_403_FORBIDDEN)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", status.HTTP_409_CONFLICT)
        except AlreadyMarkedError as exc:
            return _error(str(exc), "ALREADY_MARKED", status.HTTP_409_CONFLICT)
        except AttendanceError as exc:
            return _error(str(exc), "ATTENDANCE_REJECTED", status.HTTP_400_BAD_REQUEST)

        session = record.attendance_session
        return Response(
            {
                "success": True,
                "data": {
                    "attendance_record_id": str(record.id),
                    "attendance_session_id": str(record.attendance_session_id),
                    "recorded_at": record.recorded_at,
                    # Honest reporting for the student's screen (MVP s11.C):
                    # which mode just credited them, and whether the scan also
                    # turned their device into a relay station.
                    "mode": session.mode,
                    "scope": getattr(record, "scope", None),
                    "station_activated": bool(getattr(record, "station_activated", False)),
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
            present = session.record_cnt
            # §67: class_session/lecturer uuid and lecturer_name are not
            # consumed by the UI; course identity, mode and counts carry the row.
            headcount = expected_headcount(session=session)
            rows.append({
                "id": str(session.id),
                "course_code": session.class_session.course.code,
                "course_name": session.class_session.course.name,
                "class_name": session.class_session.course.name,
                "status": session.status,
                "mode": session.mode,
                "is_active": session.status == AttendanceSession.Status.ACTIVE,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "checkpoints": session.checkpoint_cnt,
                "stations": session.checkpoint_cnt,
                "records": session.record_cnt,
                "present": present,
                "total_present": present,
                "total_eligible": headcount,
                "expected_headcount": headcount,
                "headcount_remaining": max(headcount - present, 0),
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
                mode=validated.get("mode"),
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
                "mode": session.mode,
                "is_active": session.status == AttendanceSession.Status.ACTIVE,
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
                mode=serializer.validated_data.get("mode"),
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
                "mode": session.mode,
                "is_active": session.status == AttendanceSession.Status.ACTIVE,
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
            session.checkpoints.select_related("student").order_by("created_at", "student__username")
        )
        records = list(
            session.records.select_related("student")
            .prefetch_related("corrections__corrected_by")
            .order_by("recorded_at")
        )
        record_by_student = {str(record.student_id): record for record in records}

        checkpoint_rows = []
        for position, checkpoint in enumerate(checkpoints, start=1):
            record = record_by_student.get(str(checkpoint.student_id))
            checkpoint_rows.append({
                "id": str(checkpoint.id),
                "student": str(checkpoint.student_id),
                "student_name": _user_name(checkpoint.student),
                "marked": record is not None,
                # Position is presentational only; it is not an identifier and
                # carries no authority.
                "checkpoint_number": position,
                "source": checkpoint.source,
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

        present = len(records)
        headcount = len(eligible)
        return _success(
            {
                "id": str(session.id),
                "course_code": session.class_session.course.code,
                "course_name": session.class_session.course.name,
                "class_name": session.class_session.course.name,
                "status": session.status,
                "mode": session.mode,
                "is_active": session.status == AttendanceSession.Status.ACTIVE,
                "started_at": session.started_at,
                "expires_at": session.expires_at,
                "checkpoints": checkpoint_rows,
                "records": [_serialize_record(r, include_corrections=True) for r in records],
                "eligible_students": eligible,
                "marked_count": len([c for c in checkpoint_rows if c["marked"]]),
                "total_checkpoints": len(checkpoint_rows),
                "stations": len(checkpoint_rows),
                "record_count": present,
                "present": present,
                "total_present": present,
                "total_eligible": headcount,
                "expected_headcount": headcount,
                "headcount_remaining": max(headcount - present, 0),
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
        except ModeMismatchError as exc:
            # Seeding only exists in stations mode; a projected session says so.
            return _error(str(exc), "MODE_MISMATCH", 409)
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


class AttendanceSessionTokenView(APIView):
    """Projected mode: issue the one shared code the whole room scans."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may issue QR codes.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        try:
            token = generate_projected_token(lecturer=request.user, session=session)
        except LecturerNotAuthorizedError:
            # §25: a non-owner must be indistinguishable from a missing session.
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        except ModeMismatchError as exc:
            return _error(str(exc), "MODE_MISMATCH", 409)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        ttl = get_qr_token_ttl_seconds()
        # §67: session uuid stays server-side; the client needs the code and
        # how long it lives so it can rotate it before expiry.
        return _success({"token": token, "ttl_seconds": ttl, "expires_in_seconds": ttl}, 201)


class AttendanceAutoSelectView(APIView):
    """Seed a handful of eligible students without manual picking."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may select stations.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        serializer = AutoSelectStationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            checkpoints = auto_select_checkpoints(
                lecturer=request.user,
                session=session,
                count=serializer.validated_data.get("count", 3),
            )
        except ModeMismatchError as exc:
            return _error(str(exc), "MODE_MISMATCH", 409)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        except (CheckpointNotEligibleError, AttendanceError) as exc:
            return _error(str(exc), "CHECKPOINT_REJECTED", 400)
        return _success(
            {
                "checkpoints": [
                    {
                        "id": str(checkpoint.id),
                        "student": str(checkpoint.student_id),
                        "student_name": _user_name(checkpoint.student),
                        "source": checkpoint.source,
                    }
                    for checkpoint in checkpoints
                ]
            },
            201,
        )


class AttendanceCheckpointDeleteView(APIView):
    """Withdraw a seed that has not relayed anything yet."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, checkpoint_pk):
        if not is_authorized_academic_user(request.user):
            return _error("Only academic users may manage stations.", "UNAUTHORIZED", 403)
        session = _session_base(request.user, pk)
        if session is None:
            return _error("Attendance session not found or not yours.", "NOT_FOUND", 404)
        checkpoint = (
            session.checkpoints.filter(id=checkpoint_pk).select_related("student").first()
        )
        if checkpoint is None:
            return _error("Station not found.", "NOT_FOUND", 404)
        try:
            remove_checkpoint(lecturer=request.user, session=session, checkpoint=checkpoint)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        except LecturerNotAuthorizedError as exc:
            return _error(str(exc), "UNAUTHORIZED", 403)
        except AttendanceError as exc:
            # Includes "already relayed attendance": history is never erased.
            return _error(str(exc), "CHECKPOINT_REJECTED", 400)
        return _success({"id": str(checkpoint_pk), "removed": True})


class AttendanceStationTokenView(APIView):
    """A station's own device polls this for its next 10-second relay code."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if getattr(request.user, "role", None) != User.Role.STUDENT:
            return _error("Only student accounts act as stations.", "UNAUTHORIZED", 403)
        try:
            data = station_token(student=request.user, session_id=pk)
        except NotEligibleError as exc:
            # §25: no confirmation of whether the session or the station exists.
            return _error(str(exc), "FORBIDDEN", 403)
        except ModeMismatchError as exc:
            return _error(str(exc), "MODE_MISMATCH", 409)
        except SessionExpiredError as exc:
            return _error(str(exc), "SESSION_EXPIRED", 409)
        return _success(data)


class MyStationView(APIView):
    """The student's live station banner, or an honest null when there is none.

    Always 200: "you are not a station right now" is a normal state, not an
    error, and the client must not show a failure for it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success(station_summary(student=request.user))


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
        # The corrections relation is already prefetched above: read the cached
        # rows, never exists()/count(), which would re-query per record.
        for record in queryset[:500]:
            course = record.attendance_session.class_session.course
            # §67: session/class/student uuids are not rendered by the UI;
            # course codes, names and the correction envelope carry the row.
            corrections = list(record.corrections.all())
            rows.append(
                {
                    "id": str(record.id),
                    "course_code": course.code,
                    "course_name": course.name,
                    "student_name": _user_name(record.student),
                    "recorded_at": record.recorded_at,
                    "status": "PRESENT",
                    "corrected": bool(corrections),
                    "correction_count": len(corrections),
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
