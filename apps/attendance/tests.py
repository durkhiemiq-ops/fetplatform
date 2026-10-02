import threading
from datetime import timedelta
from unittest import skipUnless

from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course, Enrollment
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.attendance.services.attendance_service import (
    AlreadyMarkedError,
    SessionExpiredError,
    TokenStudentMismatchError,
    generate_checkpoint_token,
    scan_attendance,
    select_checkpoints,
)
from apps.attendance.utils.qr_tokens import (
    TokenAlreadyUsedError,
    TokenExpiredError,
    generate_token,
)
from core.models import AuditEvent


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "attendance-tests",
        }
    }
)
class AttendanceSecurityTests(TestCase):
    def setUp(self):
        self.lecturer = User.objects.create_user(
            "lecturer@example.test", "lecturer", "Lect", "Urer", "StrongPass!2026", role=User.Role.LECTURER
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
        self.session = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() + timedelta(seconds=60),
        )

    def checkpoint_token(self, student=None):
        checkpoint = select_checkpoints(
            lecturer=self.lecturer, session=self.session, student_ids=[(student or self.student).id]
        )[0]
        return generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint), checkpoint

    def test_valid_authenticated_student_is_marked_once(self):
        token, checkpoint = self.checkpoint_token()
        record = scan_attendance(authenticated_student=self.student, token=token)
        self.assertEqual(record.student_id, self.student.id)
        self.assertEqual(record.checkpoint_id, checkpoint.id)

    def test_same_token_cannot_be_replayed(self):
        token, _ = self.checkpoint_token()
        scan_attendance(authenticated_student=self.student, token=token)
        with self.assertRaises(TokenAlreadyUsedError):
            scan_attendance(authenticated_student=self.student, token=token)

    def test_screenshot_token_cannot_credit_another_student(self):
        token, _ = self.checkpoint_token(student=self.student)
        with self.assertRaises(TokenStudentMismatchError):
            scan_attendance(authenticated_student=self.other_student, token=token)
        self.assertFalse(AttendanceRecord.objects.filter(student=self.other_student).exists())

    def test_cross_session_token_is_rejected(self):
        token, checkpoint = self.checkpoint_token()
        token = generate_token(checkpoint_id=checkpoint.id, session_id="different-session")
        with self.assertRaises(SessionExpiredError):
            scan_attendance(authenticated_student=self.student, token=token)

    def test_database_constraint_blocks_duplicate_student_record(self):
        token, checkpoint = self.checkpoint_token()
        scan_attendance(authenticated_student=self.student, token=token)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceRecord.objects.create(
                    attendance_session=self.session, student=self.student, checkpoint=checkpoint
                )

    def test_api_rejects_client_supplied_student_identity(self):
        token, _ = self.checkpoint_token()
        client = APIClient()
        client.force_authenticate(user=self.student)
        response = client.post(
            reverse("attendance:scan"), {"token": token, "student_id": str(self.other_student.id)}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_successful_scan_creates_a_durable_audit_event(self):
        token, _ = self.checkpoint_token()
        record = scan_attendance(authenticated_student=self.student, token=token)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="attendance_recorded", resource_type="attendance_record", resource_id=str(record.id)
            ).exists()
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "attendance-throttle-tests",
        }
    }
)
class AttendanceScanThrottleTests(TestCase):
    """POST /attendance/scan/ has its own rate limit (audit item 29 closed).

    ScopedRateThrottle keys on the authenticated student's pk (a fresh UUID
    per test, so no counter bleed).  The dedicated scope is 20/minute, below
    the global anon 30/minute budget — so the 21st request proving RATE_LIMITED
    can only come from the attendance-scan scope, before token validation runs.
    """

    def setUp(self):
        self.student = User.objects.create_user(
            "throttled@example.test", "throttled", "Throt", "Tled", "StrongPass!2026"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.student)

    def test_scan_hammering_is_throttled_before_the_view_runs(self):
        url = reverse("attendance:scan")
        responses = [
            self.client.post(url, {"token": f"junk-token-{index}"}, format="json")
            for index in range(21)
        ]
        # Requests 1-20 reach the view and fail normally (absent token)...
        self.assertEqual(responses[0].status_code, 404)
        self.assertEqual(responses[0].data["error"]["code"], "TOKEN_EXPIRED")
        # ...the 21st is rejected by the dedicated throttle and never hits
        # token consumption or the failure counter.
        throttled = responses[-1]
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.data["error"]["code"], "RATE_LIMITED")

    def test_distinct_students_burst_never_sees_the_throttle(self):
        """BR-029 + §50 evidence: the scan scope is per-student, never global.

        ScopedRateThrottle keys the attendance-scan budget on each
        authenticated student's pk, so many *different* students scanning in
        the same class window each draw from their own 20/minute allowance.
        If the scope were shared per endpoint, 21 distinct students would
        already be throttled and the BR-029 requirement would be broken.
        """
        url = reverse("attendance:scan")
        responses = []
        for index in range(25):
            student = User.objects.create_user(
                f"burst-{index}@example.test",
                f"burst{index}",
                "Bur",
                "St",
                "StrongPass!2026",
            )
            client = APIClient()
            client.force_authenticate(user=student)
            responses.append(
                client.post(url, {"token": f"junk-{index}"}, format="json")
            )
        self.assertNotIn(429, [response.status_code for response in responses])
        # Every request actually reached the view (absent token) instead of
        # being intercepted by a shared endpoint budget.
        self.assertTrue(
            all(response.status_code == 404 for response in responses)
        )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "attendance-concurrency-tests",
        }
    }
)
@skipUnless(
    connection.vendor == "postgresql",
    "scan atomicity rests on SELECT ... FOR UPDATE, which SQLite silently ignores",
)
class AttendanceConcurrencyTests(TransactionTestCase):
    """BR-029: many simultaneous scans against one session.

    PostgreSQL-only on purpose: the scan path's race defense is the
    session-row FOR UPDATE lock plus the UNIQUE(session, student) constraint,
    and SQLite would rubber-stamp the assertions without exercising either.
    Each worker runs in its own thread/transaction against the real Postgres
    test database.

    Covers the three failure classes named by BR-029: no duplicate records,
    no lost valid submissions, and no wrongly-accepted expired tokens/sessions.
    """

    def setUp(self):
        self.lecturer = User.objects.create_user(
            "conc-lecturer@example.test",
            "conclecurer",
            "Conc",
            "Lecturer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(code="FET101", name="Secure Attendance")
        self.class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )
        self.session = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() + timedelta(seconds=600),
        )

    def make_students(self, count):
        students = []
        for index in range(count):
            student = User.objects.create_user(
                f"conc-{index}@example.test",
                f"conc{index}",
                "Conc",
                f"St{index}",
                "StrongPass!2026",
            )
            Enrollment.objects.create(student=student, course=self.course)
            students.append(student)
        return students

    def run_burst(self, arguments, worker_fn, count):
        """Run `count` threads concurrently, each with its own kwarg dict.

        A barrier releases every worker at once; each worker uses its own DB
        connection (stale ones are closed first so PostgreSQL does not reuse a
        connection bound to another thread).
        """
        barrier = threading.Barrier(count)
        results = []
        errors = []

        def worker(kwargs):
            from django.db import close_old_connections

            close_old_connections()
            try:
                barrier.wait()
                results.append(worker_fn(**kwargs))
            except Exception as exc:  # noqa: BLE001 - collected for assertions
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(arguments[index],))
            for index in range(count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=180)
        return results, errors

    def test_100_distinct_students_burst_with_no_loss_or_duplicates(self):
        # BR-029's headline number: 100+ students in the same few seconds.
        students = self.make_students(100)
        checkpoints = select_checkpoints(
            lecturer=self.lecturer,
            session=self.session,
            student_ids=[student.id for student in students],
        )
        tokens = [
            generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint)
            for checkpoint in checkpoints
        ]
        arguments = [
            {"authenticated_student": student, "token": token}
            for student, token in zip(students, tokens)
        ]
        results, errors = self.run_burst(arguments, scan_attendance, 100)

        self.assertEqual(errors, [], f"valid submissions must not be lost: {errors}")
        self.assertEqual(len(results), 100)
        records = AttendanceRecord.objects.filter(attendance_session=self.session)
        self.assertEqual(records.count(), 100)
        # No duplicates: one record per distinct student.
        self.assertEqual(
            records.values_list("student_id", flat=True).distinct().count(), 100
        )

    def test_same_student_simultaneous_replay_is_recorded_exactly_once(self):
        student = self.make_students(1)[0]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer, session=self.session, student_ids=[student.id]
        )[0]
        token = generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint)
        results, errors = self.run_burst(
            [
                {"authenticated_student": student, "token": token},
                {"authenticated_student": student, "token": token},
            ],
            scan_attendance,
            2,
        )
        self.assertEqual(
            AttendanceRecord.objects.filter(
                attendance_session=self.session, student=student
            ).count(),
            1,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], (TokenAlreadyUsedError, AlreadyMarkedError))

    def test_expired_token_is_rejected_by_every_concurrent_scanner(self):
        student = self.make_students(1)[0]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer, session=self.session, student_ids=[student.id]
        )[0]
        token = generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint)
        # Simulate the 10s TTL elapsing: the cache entry is gone, exactly as it
        # would be after the window.  No record may be written from this point.
        cache.delete(f"attendance:qr:{token}")
        results, errors = self.run_burst(
            [
                {"authenticated_student": student, "token": token},
                {"authenticated_student": student, "token": token},
            ],
            scan_attendance,
            2,
        )
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(isinstance(e, TokenExpiredError) for e in errors))
        self.assertEqual(
            AttendanceRecord.objects.filter(
                attendance_session=self.session, student=student
            ).count(),
            0,
        )

    def test_expired_session_rejects_concurrent_scans_without_side_effects(self):
        student = self.make_students(1)[0]
        checkpoint = select_checkpoints(
            lecturer=self.lecturer, session=self.session, student_ids=[student.id]
        )[0]
        # Each worker gets its own fresh token so every scan reaches the
        # session-expiry check (token consumption happens first, so sharing a
        # token would make the second worker fail on replay instead).
        tokens = [
            generate_checkpoint_token(lecturer=self.lecturer, checkpoint=checkpoint)
            for _ in range(2)
        ]
        # The session window lapses AFTER tokens were issued — a realistic race
        # between a token being scanned and the lecturer's session expiring.
        self.session.expires_at = timezone.now() - timedelta(seconds=1)
        self.session.save(update_fields=["expires_at"])
        results, errors = self.run_burst(
            [
                {"authenticated_student": student, "token": tokens[0]},
                {"authenticated_student": student, "token": tokens[1]},
            ],
            scan_attendance,
            2,
        )
        self.assertEqual(results, [])
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(isinstance(e, SessionExpiredError) for e in errors))
        self.assertEqual(
            AttendanceRecord.objects.filter(attendance_session=self.session).count(),
            0,
        )
