"""API-level tests for the full attendance lifecycle and authorization matrix.

Covers session start/close/list/detail, checkpoint selection, the lecturer's
QR token issuance, records scoping, audited corrections, and the BR-064 review
surface.  Every write path is gated by role and ownership server-side, and
every significant action is audited.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course, Enrollment
from apps.accounts.models import User
from apps.attendance.models import (
    AttendanceCheckpoint,
    AttendanceCorrection,
    AttendanceRecord,
    AttendanceSession,
)
from apps.attendance.services.attendance_service import (
    evaluate_repeated_failure,
    flag_suspicious_activity,
    generate_checkpoint_token,
    scan_attendance,
    select_checkpoints,
)
from core.models import AuditEvent


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "attendance-api-tests",
        }
    }
)
class AttendanceLifecycleApiTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            "lecturer@example.test", "lecturer", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.admin = User.objects.create_user(
            "admin@example.test", "administrator", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.other_lecturer = User.objects.create_user(
            "other-lecturer@example.test", "otherlecturer", "Other", "Lecturer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "student@example.test", "student", "Stu", "Dent", "StrongPass!2026"
        )
        self.other_student = User.objects.create_user(
            "other@example.test", "other", "Other", "Student", "StrongPass!2026"
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")
        Enrollment.objects.create(student=self.student, course=self.course)
        Enrollment.objects.create(student=self.other_student, course=self.course)
        self.class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )

    def auth(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def start_session(self, **kwargs):
        return self.auth(self.lecturer).post(
            reverse("attendance:session-list"),
            {"class_session": str(self.class_session.id), **(kwargs or {})},
            format="json",
        )

    # ---- Session lifecycle -------------------------------------------------

    def test_lecturer_can_start_and_read_back_a_session(self):
        response = self.start_session(duration_seconds=30)
        self.assertEqual(response.status_code, 201)
        session_id = response.data["data"]["id"]
        self.assertEqual(response.data["data"]["status"], "ACTIVE")

        listing = self.auth(self.lecturer).get(reverse("attendance:session-list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["data"]), 1)
        self.assertEqual(listing.data["data"][0]["id"], session_id)
        self.assertEqual(listing.data["data"][0]["course_code"], "FET101")

        detail = self.auth(self.lecturer).get(reverse("attendance:session-detail", args=[session_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data["data"]["eligible_students"]), 2)
        names = {row["username"] for row in detail.data["data"]["eligible_students"]}
        self.assertEqual(names, {"student", "other"})

    def test_student_cannot_start_or_list_sessions(self):
        student_client = self.auth(self.student)
        self.assertEqual(
            student_client.post(
                reverse("attendance:session-list"),
                {"class_session": str(self.class_session.id)},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            student_client.get(reverse("attendance:session-list")).status_code, 403
        )

    def test_non_owner_lecturer_cannot_start_session_for_another_class(self):
        response = self.auth(self.other_lecturer).post(
            reverse("attendance:session-list"),
            {"class_session": str(self.class_session.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_admin_can_start_session_on_any_class(self):
        response = self.auth(self.admin).post(
            reverse("attendance:session-list"),
            {"class_session": str(self.class_session.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_only_one_active_session_per_class(self):
        self.assertEqual(self.start_session().status_code, 201)
        duplicate = self.start_session()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["error"]["code"], "SESSION_ALREADY_ACTIVE")

    def test_duration_out_of_band_is_rejected(self):
        response = self.start_session(duration_seconds=1)
        self.assertEqual(response.status_code, 400)

    def test_starting_an_unknown_class_returns_404(self):
        response = self.auth(self.lecturer).post(
            reverse("attendance:session-list"),
            {"class_session": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["code"], "CLASS_NOT_FOUND")

    def test_session_start_is_audited(self):
        self.start_session()
        self.assertTrue(
            AuditEvent.objects.filter(action="attendance_session_started").exists()
        )

    def test_owner_closes_session_and_audits(self):
        session_id = self.start_session().data["data"]["id"]
        response = self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[session_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "CLOSED")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_session_closed", resource_id=session_id
            ).exists()
        )
        # Closing twice is a conflict, not a silent no-op.
        again = self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[session_id])
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["error"]["code"], "SESSION_NOT_ACTIVE")

    def test_only_owner_or_admin_can_close(self):
        session_id = self.start_session().data["data"]["id"]
        self.assertEqual(
            self.auth(self.other_lecturer)
            .post(reverse("attendance:session-close", args=[session_id]))
            .status_code,
            404,
        )
        self.assertEqual(
            self.auth(self.admin)
            .post(reverse("attendance:session-close", args=[session_id]))
            .status_code,
            200,
        )

    def test_expired_session_is_lazily_marked_expired(self):
        expired = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        detail = self.auth(self.lecturer).get(
            reverse("attendance:session-detail", args=[expired.id])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["data"]["status"], "EXPIRED")
        close = self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[expired.id])
        )
        self.assertEqual(close.status_code, 409)

    # ---- Checkpoints + QR token issuance (the lecturer's generator) ---------

    def test_lecturer_selects_checkpoints_and_issues_a_qr_token(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        select = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(self.student.id), str(self.other_student.id)]},
            format="json",
        )
        self.assertEqual(select.status_code, 201)
        # The station under test belongs to other_student, so the scanner
        # (self.student) is never relaying their own code.
        checkpoint_id = next(
            row["id"]
            for row in select.data["data"]["checkpoints"]
            if row["student"] == str(self.other_student.id)
        )

        token = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[checkpoint_id])
        )
        self.assertEqual(token.status_code, 201)
        # §67: the token payload is exactly the token + its TTL — no internal
        # checkpoint/session/student uuids.
        self.assertEqual(set(token.data["data"].keys()), {"token", "ttl_seconds"})
        self.assertEqual(token.data["data"]["ttl_seconds"], 10)

        # The issued token completes the real scan loop.
        scan = self.auth(self.student).post(
            reverse("attendance:scan"),
            {"token": token.data["data"]["token"]},
            format="json",
        )
        self.assertEqual(scan.status_code, 201)
        record = AttendanceRecord.objects.get(
            attendance_session_id=session_id, student=self.student
        )
        self.assertEqual(str(record.checkpoint_id), checkpoint_id)

    def test_checkpoint_selection_rejects_non_eligible_student(self):
        outsider = User.objects.create_user(
            "outsider@example.test", "outsider", "Out", "Sider", "StrongPass!2026"
        )
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        response = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(outsider.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "CHECKPOINT_REJECTED")

    def test_checkpoint_selection_is_atomic_and_audited(self):
        outsider = User.objects.create_user(
            "partial-outsider@example.test",
            "partial-outsider",
            "Out",
            "Sider",
            "StrongPass!2026",
        )
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        selection_url = reverse("attendance:session-checkpoints", args=[session_id])

        rejected = self.auth(self.lecturer).post(
            selection_url,
            {"student_ids": [str(self.student.id), str(outsider.id)]},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(
            AttendanceCheckpoint.objects.filter(attendance_session_id=session_id).exists()
        )

        accepted = self.auth(self.lecturer).post(
            selection_url,
            {"student_ids": [str(self.student.id)]},
            format="json",
        )
        self.assertEqual(accepted.status_code, 201)
        checkpoint_id = accepted.data["data"]["checkpoints"][0]["id"]
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_checkpoints_selected",
                resource_id=str(session_id),
                actor_id=self.lecturer.id,
            ).exists()
        )

        issued = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[checkpoint_id])
        )
        self.assertEqual(issued.status_code, 201)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_token_issued",
                resource_id=str(checkpoint_id),
                actor_id=self.lecturer.id,
            ).exists()
        )

    def test_repeated_scan_failures_raise_one_flag_per_window(self):
        for _ in range(6):
            evaluate_repeated_failure(
                cache_backend=cache,
                actor_id=self.student.id,
                failure_code="INVALID_TOKEN",
                request_ip="127.0.0.1",
            )
        self.assertEqual(
            AuditEvent.objects.filter(
                action="attendance_suspicious_activity",
                actor_id=self.student.id,
            ).count(),
            1,
        )

    def test_checkpoints_need_at_least_one_student(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        response = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_owner_cannot_select_checkpoints_or_issue_tokens(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        other = self.auth(self.other_lecturer)
        self.assertEqual(
            other.post(
                reverse("attendance:session-checkpoints", args=[session_id]),
                {"student_ids": [str(self.student.id)]},
                format="json",
            ).status_code,
            404,
        )
        checkpoint = select_checkpoints(
            lecturer=self.lecturer,
            session=AttendanceSession.objects.get(id=session_id),
            student_ids=[self.student.id],
        )[0]
        # §25: a non-owner probing a checkpoint token request must see exactly
        # the not-found shape, indistinguishable from a checkpoint that never
        # existed.
        self.assertEqual(
            other.post(reverse("attendance:checkpoint-token", args=[checkpoint.id])).status_code,
            404,
        )
        self.assertEqual(
            other.post(reverse("attendance:checkpoint-token", args=[checkpoint.id])).data["error"]["code"],
            "NOT_FOUND",
        )

    def test_token_issuance_fails_on_closed_session(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer,
            session=AttendanceSession.objects.get(id=session_id),
            student_ids=[self.student.id],
        )[0]
        self.auth(self.lecturer).post(reverse("attendance:session-close", args=[session_id]))
        response = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[checkpoint.id])
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "SESSION_EXPIRED")

    # ---- Records + corrections ----------------------------------------------

    def test_student_sees_own_records_only(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer,
            session=AttendanceSession.objects.get(id=session_id),
            student_ids=[self.other_student.id],
        )[0]
        scan_attendance(
            authenticated_student=self.student,
            token=generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint),
        )

        mine = self.auth(self.student).get(reverse("attendance:record-list"))
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(len(mine.data["data"]), 1)
        # §67: the row carries presentation fields only — the student uuid and
        # internal session/class uuids are not returned.
        self.assertNotIn("student", mine.data["data"][0])
        self.assertNotIn("attendance_session", mine.data["data"][0])
        self.assertNotIn("class_session", mine.data["data"][0])
        self.assertEqual(mine.data["data"][0]["student_name"], "Stu Dent")
        self.assertEqual(mine.data["data"][0]["course_code"], "FET101")

        theirs = self.auth(self.other_student).get(reverse("attendance:record-list"))
        self.assertEqual(len(theirs.data["data"]), 0)

    def test_lecturer_can_read_own_sessions_records(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        scan_attendance(
            authenticated_student=self.student,
            token=generate_checkpoint_token(
                lecturer=self.lecturer,
                checkpoint=select_checkpoints(
                    lecturer=self.lecturer,
                    session=AttendanceSession.objects.get(id=session_id),
                    student_ids=[self.other_student.id],
                )[0],
            ),
        )
        response = self.auth(self.lecturer).get(
            reverse("attendance:record-list"), {"session": session_id}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)

        other = self.auth(self.other_lecturer).get(
            reverse("attendance:record-list"), {"session": session_id}
        )
        self.assertEqual(other.status_code, 404)

    def test_correction_is_traceable_and_owner_only(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer,
            session=AttendanceSession.objects.get(id=session_id),
            student_ids=[self.other_student.id],
        )[0]
        record = scan_attendance(
            authenticated_student=self.student,
            token=generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint),
        )

        response = self.auth(self.lecturer).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "LATE", "reason": "Student was present but scanned late."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_corrected", resource_id=str(record.id)
            ).exists()
        )
        # The original record is preserved, never replaced -- the correction is
        # an append-only event that also moves the record's status (BR-042).
        self.assertEqual(AttendanceRecord.objects.filter(id=record.id).count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.status, AttendanceRecord.Status.LATE)
        correction = AttendanceCorrection.objects.get(attendance_record=record)
        self.assertEqual(correction.old_status, AttendanceRecord.Status.PRESENT)
        self.assertEqual(correction.new_status, AttendanceRecord.Status.LATE)

        # A correction must actually change something: correcting to the status
        # the record already holds is rejected.
        no_op = self.auth(self.lecturer).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "LATE", "reason": "Already late."},
            format="json",
        )
        self.assertEqual(no_op.status_code, 400)

        no_reason = self.auth(self.lecturer).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "PRESENT", "reason": ""},
            format="json",
        )
        self.assertEqual(no_reason.status_code, 400)

        other = self.auth(self.other_lecturer).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "ABSENT", "reason": "not mine"},
            format="json",
        )
        # §25: a non-owner sees exactly the missing-record shape, no matter how
        # they probe (with or without a reason).
        self.assertEqual(other.status_code, 404)
        self.assertEqual(other.data["error"]["code"], "NOT_FOUND")
        self.assertNotIn("reason", other.data["error"])

        # §25 + BR-042: even probing with a *legitimate-looking* reason must not
        # reveal existence, and the audit trail must not be touched.
        other_probe = self.auth(self.other_lecturer).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "ABSENT", "reason": "Student was present but scanned late."},
            format="json",
        )
        self.assertEqual(other_probe.status_code, 404)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="attendance_corrected", resource_id=str(record.id)
            ).count(),
            1,
        )

    def test_admin_can_correct_any_records_record_and_it_is_audited(self):
        # BR-042: corrections are the record's session lecturer OR an
        # administrator; both require an audit reason.
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer,
            session=AttendanceSession.objects.get(id=session_id),
            student_ids=[self.other_student.id],
        )[0]
        record = scan_attendance(
            authenticated_student=self.student,
            token=generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint),
        )

        response = self.auth(self.admin).post(
            reverse("attendance:record-corrections", args=[record.id]),
            {"status": "EXCUSED", "reason": "Administrative correction per BR-042."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        correction = response.data["data"]["correction"]
        correction_id = correction["id"]
        # §67: the correction payload is exactly the audit envelope — the
        # internal corrector uuid is not exposed; the human name is.
        self.assertEqual(
            set(correction.keys()),
            {
                "id",
                "reason",
                "old_status",
                "new_status",
                "corrected_by_name",
                "created_at",
            },
        )
        self.assertEqual(correction["old_status"], AttendanceRecord.Status.PRESENT)
        self.assertEqual(correction["new_status"], AttendanceRecord.Status.EXCUSED)
        self.assertEqual(correction["corrected_by_name"], "Ad Min")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_corrected",
                resource_id=str(record.id),
                actor_id=self.admin.id,
            ).exists()
        )
        self.assertEqual(AttendanceCorrection.objects.filter(id=correction_id).count(), 1)

    def test_response_payloads_are_trimmed_per_s67(self):
        """§67: no response returns fields the frontend does not consume."""
        session_id = self.start_session(duration_seconds=30, mode="STATIONS").data["data"]["id"]
        # Seed one checkpoint so the session detail has a row to inspect.
        self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [self.student.id]},
            format="json",
        )

        # Session list: no internal class_session/lecturer uuids, no redundant
        # lecturer name.
        listing = self.auth(self.lecturer).get(reverse("attendance:session-list"))
        row = listing.data["data"][0]
        self.assertNotIn("class_session", row)
        self.assertNotIn("lecturer", row)
        self.assertNotIn("lecturer_name", row)

        # Session detail: same top-level trim; checkpoint rows are the
        # id/student/student_name/marked presentation only (no embedded record).
        detail = self.auth(self.lecturer).get(
            reverse("attendance:session-detail", args=[session_id])
        )
        self.assertNotIn("class_session", detail.data["data"])
        self.assertNotIn("lecturer", detail.data["data"])
        self.assertNotIn("lecturer_name", detail.data["data"])
        checkpoint_row = detail.data["data"]["checkpoints"][0]
        self.assertEqual(
            set(checkpoint_row.keys()),
            {"id", "student", "student_name", "marked", "checkpoint_number", "source"},
        )
        self.assertNotIn("record", checkpoint_row)
        self.assertNotIn("attendance_session", checkpoint_row)

        # Checkpoint selection: checkpoint rows carry no owning session uuid.
        select = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [self.student.id]},
            format="json",
        )
        selected = select.data["data"]["checkpoints"][0]
        self.assertEqual(
            set(selected.keys()), {"id", "student", "student_name"}
        )

    # ---- BR-064 review surface ----------------------------------------------

    def test_review_flags_scoped_and_not_denials(self):
        session_id = self.start_session(mode="STATIONS").data["data"]["id"]
        scan_attendance(
            authenticated_student=self.student,
            token=generate_checkpoint_token(
                lecturer=self.lecturer,
                checkpoint=select_checkpoints(
                    lecturer=self.lecturer,
                    session=AttendanceSession.objects.get(id=session_id),
                    student_ids=[self.other_student.id],
                )[0],
            ),
        )
        # A student outside every class this lecturer teaches must be invisible
        # to the lecturer's review surface but visible to an administrator.
        outsider = User.objects.create_user(
            "outsider@example.test", "outsider", "Out", "Sider", "StrongPass!2026"
        )
        flag_suspicious_activity(
            actor_id=self.student.id, reason="repeated_invalid_attendance_scan",
            metadata={"failure_code": "TOKEN_EXPIRED"},
        )
        flag_suspicious_activity(
            actor_id=self.other_student.id, reason="suspicious_login_pattern"
        )
        flag_suspicious_activity(
            actor_id=outsider.id, reason="repeated_invalid_attendance_scan"
        )

        lecturer_flags = self.auth(self.lecturer).get(reverse("attendance:review"))
        self.assertEqual(lecturer_flags.status_code, 200)
        flagged = {row["student_id"] for row in lecturer_flags.data["data"]}
        # Lecturers see flags for students in classes they teach only — never
        # students from outside their classes.
        self.assertEqual(
            flagged, {str(self.student.id), str(self.other_student.id)}
        )

        admin_flags = self.auth(self.admin).get(reverse("attendance:review"))
        self.assertEqual(
            {row["student_id"] for row in admin_flags.data["data"]},
            {str(self.student.id), str(self.other_student.id), str(outsider.id)},
        )

        self.assertEqual(
            self.auth(self.student).get(reverse("attendance:review")).status_code, 403
        )