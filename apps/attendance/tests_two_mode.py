"""The two-mode attendance slice, end to end (MASTER-ATT-01/02).

Master prompt §11 defines two wire modes and §42/§407-408 defines the two
acceptance journeys.  These tests exercise both through the HTTP surface, not
the service layer, because the contract under test *is* the wire contract:

``PROJECTOR``
    one code for the room; every enrolled scanner credits themselves and the
    record has no scan point.

``STATIONS``
    seeded scan points relay scans; a scanner is marked present **and**
    activated as a station in the same transaction (seed -> B -> C cascade),
    and nobody can relay their own code.

Both modes share the same token rules: 10-second TTL, session-bound, never
consumed (the shared-QR mandate), credited only to the authenticated scanner.
"""

from datetime import date

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import (
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)
from apps.accounts.models import User
from apps.attendance.models import AttendanceCheckpoint, AttendanceRecord, AttendanceSession


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "attendance-two-mode-tests",
        }
    }
)
class TwoModeAttendanceJourneyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.lecturer = User.objects.create_user(
            "mode-lecturer@example.test", "modelecturer", "Mode", "Lecturer",
            "StrongPass!2026", role=User.Role.LECTURER,
        )
        self.admin = User.objects.create_user(
            "mode-admin@example.test", "modeadmin", "Ad", "Min",
            "StrongPass!2026", role=User.Role.ADMINISTRATOR,
        )
        self.course = Course.objects.create(code="FET101", name="Two Modes")
        self.class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )
        self.students = [
            self._student(f"mode-{index}") for index in range(5)
        ]
        self.outsider = self._student("mode-outsider", enrolled=False)

    def _student(self, username, enrolled=True):
        student = User.objects.create_user(
            f"{username}@example.test", username, "Stu", username.title(),
            "StrongPass!2026",
        )
        if enrolled:
            Enrollment.objects.create(student=student, course=self.course)
        return student

    def auth(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def start(self, **kwargs):
        response = self.auth(self.lecturer).post(
            reverse("attendance:session-list"),
            {"class_session": str(self.class_session.id), **kwargs},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["data"]

    def scan(self, student, token):
        return self.auth(student).post(
            reverse("attendance:scan"), {"token": token}, format="json"
        )

    # ---- Journey 1: projected mode ------------------------------------------

    def test_projected_journey_scan_duplicate_unenrolled_expired_and_closed(self):
        session = self.start(duration_seconds=120)
        session_id = session["id"]
        self.assertEqual(session["mode"], "PROJECTOR")

        issued = self.auth(self.lecturer).post(
            reverse("attendance:session-token", args=[session_id])
        )
        self.assertEqual(issued.status_code, 201, issued.data)
        # §67: exactly the code and how long it lives — 10 seconds (BR-035),
        # re-issued continuously by the projector, never consumed by a scan.
        self.assertEqual(
            set(issued.data["data"].keys()), {"token", "ttl_seconds", "expires_in_seconds"}
        )
        self.assertEqual(issued.data["data"]["ttl_seconds"], 10)
        token = issued.data["data"]["token"]

        # One eligible scanner credits himself with no scan point.
        first = self.scan(self.students[0], token)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["data"]["mode"], "PROJECTOR")
        self.assertEqual(first.data["data"]["scope"], "PROJECTOR")
        self.assertFalse(first.data["data"]["station_activated"])
        record = AttendanceRecord.objects.get(student=self.students[0])
        self.assertIsNone(record.checkpoint_id)

        # The shared code still works for the next student...
        second = self.scan(self.students[1], token)
        self.assertEqual(second.status_code, 201, second.data)
        # ...but a second credit for a student already marked is refused.
        duplicate = self.scan(self.students[0], token)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["error"]["code"], "ALREADY_MARKED")
        self.assertEqual(AttendanceRecord.objects.filter(student=self.students[0]).count(), 1)

        # An unenrolled scanner is refused by the same shared code.
        unenrolled = self.scan(self.outsider, token)
        self.assertEqual(unenrolled.status_code, 403)
        self.assertEqual(unenrolled.data["error"]["code"], "NOT_ELIGIBLE")
        self.assertFalse(AttendanceRecord.objects.filter(student=self.outsider).exists())

        # A code outside its 10-second window is gone, not "already used".
        cache.delete(f"attendance:qr:{token}")
        lapsed = self.scan(self.students[2], token)
        self.assertEqual(lapsed.status_code, 404)
        self.assertEqual(lapsed.data["error"]["code"], "TOKEN_EXPIRED")

        # Closing the session ends issuance and scanning alike.
        live_token = self.auth(self.lecturer).post(
            reverse("attendance:session-token", args=[session_id])
        ).data["data"]["token"]
        closed = self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[session_id])
        )
        self.assertEqual(closed.status_code, 200, closed.data)
        after_close_token = self.auth(self.lecturer).post(
            reverse("attendance:session-token", args=[session_id])
        )
        self.assertEqual(after_close_token.status_code, 409)
        self.assertEqual(after_close_token.data["error"]["code"], "SESSION_EXPIRED")

        stale = self.scan(self.students[2], live_token)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["error"]["code"], "SESSION_EXPIRED")
        self.assertFalse(AttendanceRecord.objects.filter(student=self.students[2]).exists())

    def test_projector_token_is_session_bound_and_not_issued_by_a_student(self):
        session = self.start(duration_seconds=120)
        # A student cannot mint the room's code.
        student_call = self.auth(self.students[0]).post(
            reverse("attendance:session-token", args=[session["id"]])
        )
        self.assertEqual(student_call.status_code, 403)

        # A second, live session for the same class cannot be started...
        duplicate = self.auth(self.lecturer).post(
            reverse("attendance:session-list"),
            {"class_session": str(self.class_session.id)},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)

    # ---- Journey 2: stations mode -------------------------------------------

    def test_station_journey_seed_relay_cascade_selfscan_and_removal(self):
        session = self.start(duration_seconds=180, mode="STATIONS")
        session_id = session["id"]
        self.assertEqual(session["mode"], "STATIONS")
        a, b, c = self.students[0], self.students[1], self.students[2]

        # The lecturer seeds station A; seeding grants scan-point authority
        # and never presence.
        seeded = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(a.id)]},
            format="json",
        )
        self.assertEqual(seeded.status_code, 201, seeded.data)
        station_a = seeded.data["data"]["checkpoints"][0]
        # The seed shows up as a SEED scan point on the session detail...
        detail = self.auth(self.lecturer).get(
            reverse("attendance:session-detail", args=[session_id])
        ).data["data"]
        seeded_row = next(
            row for row in detail["checkpoints"] if row["id"] == station_a["id"]
        )
        self.assertEqual(seeded_row["source"], "SEED")
        self.assertEqual(seeded_row["checkpoint_number"], 1)
        self.assertFalse(seeded_row["marked"])
        # ...and granting scan-point authority never grants presence.
        self.assertFalse(AttendanceRecord.objects.filter(student=a).exists())

        token_a = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[station_a["id"]])
        ).data["data"]["token"]

        # A cannot relay their own code: presence is claimed by scanning
        # somebody else's, never by producing a QR.
        self_scan = self.scan(a, token_a)
        self.assertEqual(self_scan.status_code, 403)
        self.assertEqual(self_scan.data["error"]["code"], "SELF_SCAN_REJECTED")
        self.assertFalse(AttendanceRecord.objects.filter(student=a).exists())

        # B scans A's code: marked present AND activated as a station in the
        # same transaction (the seed -> B -> C cascade).
        relay = self.scan(b, token_a)
        self.assertEqual(relay.status_code, 201, relay.data)
        self.assertEqual(relay.data["data"]["scope"], "STATION")
        self.assertTrue(relay.data["data"]["station_activated"])
        record_b = AttendanceRecord.objects.get(student=b)
        self.assertEqual(str(record_b.checkpoint_id), station_a["id"])
        self.assertTrue(
            AttendanceCheckpoint.objects.filter(
                attendance_session_id=session_id,
                student=b,
                source=AttendanceCheckpoint.Source.CASCADE,
            ).exists()
        )

        # B's device polls for its own next 10-second relay code.
        own_token = self.auth(b).get(
            reverse("attendance:my-station-token", args=[session_id])
        )
        self.assertEqual(own_token.status_code, 200, own_token.data)
        self.assertEqual(own_token.data["data"]["expires_in_seconds"], 10)
        self.assertEqual(own_token.data["data"]["course_code"], "FET101")
        token_b = own_token.data["data"]["token"]

        # C scans B's code: the cascade continues.
        relay_two = self.scan(c, token_b)
        self.assertEqual(relay_two.status_code, 201, relay_two.data)
        record_c = AttendanceRecord.objects.get(student=c)
        self.assertIsNotNone(record_c.checkpoint_id)

        # A student who is not a station gets an honest refusal (§25: the same
        # shape as a session that does not exist).
        not_a_station = self.auth(self.students[3]).get(
            reverse("attendance:my-station-token", args=[session_id])
        )
        self.assertEqual(not_a_station.status_code, 403)

        # An unused seed may be withdrawn; one that already relayed never is.
        unused = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(self.students[3].id)]},
            format="json",
        ).data["data"]["checkpoints"][0]
        removed = self.auth(self.lecturer).delete(
            reverse("attendance:session-checkpoint-delete", args=[session_id, unused["id"]])
        )
        self.assertEqual(removed.status_code, 200, removed.data)
        self.assertFalse(AttendanceCheckpoint.objects.filter(id=unused["id"]).exists())

        relayed = self.auth(self.lecturer).delete(
            reverse("attendance:session-checkpoint-delete", args=[session_id, station_a["id"]])
        )
        self.assertEqual(relayed.status_code, 400)
        self.assertEqual(relayed.data["error"]["code"], "CHECKPOINT_REJECTED")

    def test_auto_select_seeds_deterministically_without_marking_presence(self):
        session = self.start(duration_seconds=120, mode="STATIONS")
        selected = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints-auto-select", args=[session["id"]]),
            {"count": 2},
            format="json",
        )
        self.assertEqual(selected.status_code, 201, selected.data)
        rows = selected.data["data"]["checkpoints"]
        self.assertEqual(len(rows), 2)
        # Seeding is not attendance.
        self.assertEqual(AttendanceRecord.objects.count(), 0)

        # A wider second pass converges on the rest of the roster instead of
        # re-seeding (or shuffling) the students already holding a scan point.
        wider = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints-auto-select", args=[session["id"]]),
            {"count": 20},
            format="json",
        )
        self.assertEqual(wider.status_code, 201)
        wider_rows = wider.data["data"]["checkpoints"]
        self.assertEqual(len(wider_rows), 3)
        self.assertTrue(
            {row["id"] for row in rows}.isdisjoint({row["id"] for row in wider_rows})
        )

    def test_a_non_seed_station_requires_prior_present_attendance(self):
        """The invariant station mode rests on.

        A student becomes a station by *scanning*, and scanning is exactly
        what writes their PRESENT record — so every non-seed station must
        already hold valid PRESENT attendance **in this same active
        station-mode session**. Seeding is the deliberate exception: it grants
        scan-point authority and never presence, so the seed's student still
        has no attendance row of any kind until they scan.

        Without this, "station" would be a title anybody could hold while
        being absent.
        """
        session = self.start(duration_seconds=180, mode="STATIONS")
        session_id = session["id"]
        a, b, c = self.students[0], self.students[1], self.students[2]

        seeded = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(a.id)]},
            format="json",
        )
        self.assertEqual(seeded.status_code, 201, seeded.data)
        seed_checkpoint = seeded.data["data"]["checkpoints"][0]

        token_a = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[seed_checkpoint["id"]])
        ).data["data"]["token"]

        # Seed authority is not presence: a checkpoint, and no record at all.
        self.assertTrue(
            AttendanceCheckpoint.objects.filter(
                attendance_session_id=session_id,
                student=a,
                source=AttendanceCheckpoint.Source.SEED,
            ).exists()
        )
        self.assertFalse(AttendanceRecord.objects.filter(student=a).exists())

        # The cascade: each scanner gains presence, then station authority.
        self.assertEqual(self.scan(b, token_a).status_code, 201)
        token_b = self.auth(b).get(
            reverse("attendance:my-station-token", args=[session_id])
        ).data["data"]["token"]
        self.assertEqual(self.scan(c, token_b).status_code, 201)

        live = AttendanceSession.objects.get(pk=session_id)
        self.assertEqual(live.status, AttendanceSession.Status.ACTIVE)

        non_seed = AttendanceCheckpoint.objects.filter(
            attendance_session_id=session_id
        ).exclude(source=AttendanceCheckpoint.Source.SEED)
        self.assertGreaterEqual(non_seed.count(), 2)

        for checkpoint in non_seed:
            record = AttendanceRecord.objects.filter(
                attendance_session_id=session_id,
                student=checkpoint.student,
                status=AttendanceRecord.Status.PRESENT,
            ).first()
            self.assertIsNotNone(
                record,
                "a non-seed station must hold PRESENT attendance in the same session",
            )
            # Same session — presence earned elsewhere does not license a
            # station here.
            self.assertEqual(record.attendance_session_id, checkpoint.attendance_session_id)
            # And it came first: the record is what licensed the station.
            self.assertLessEqual(record.recorded_at, checkpoint.created_at)

        # Nobody who never scanned holds a station or a record.
        for never_scanned in (self.students[3], self.students[4], self.outsider):
            self.assertFalse(
                AttendanceCheckpoint.objects.filter(student=never_scanned).exists()
            )
            self.assertFalse(
                AttendanceRecord.objects.filter(student=never_scanned).exists()
            )

        # The seed remains the documented exception.
        self.assertFalse(AttendanceRecord.objects.filter(student=a).exists())

    def test_modes_do_not_leak_into_each_other(self):
        projected = self.start(duration_seconds=120)
        # A projected session refuses to seed stations.
        seed_on_projected = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[projected["id"]]),
            {"student_ids": [str(self.students[0].id)]},
            format="json",
        )
        self.assertEqual(seed_on_projected.status_code, 409)
        self.assertEqual(seed_on_projected.data["error"]["code"], "MODE_MISMATCH")

        # A station session refuses to mint the room's single code.
        self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[projected["id"]])
        )
        station_session = self.start(duration_seconds=120, mode="STATIONS")
        projected_code = self.auth(self.lecturer).post(
            reverse("attendance:session-token", args=[station_session["id"]])
        )
        self.assertEqual(projected_code.status_code, 409)
        self.assertEqual(projected_code.data["error"]["code"], "MODE_MISMATCH")

    # ---- Student surfaces ---------------------------------------------------

    def test_student_station_banner_and_history_are_one_stable_prefix(self):
        session = self.start(duration_seconds=180, mode="STATIONS")
        a, b = self.students[0], self.students[1]
        station_a = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session["id"]]),
            {"student_ids": [str(a.id)]},
            format="json",
        ).data["data"]["checkpoints"][0]
        token_a = self.auth(self.lecturer).post(
            reverse("attendance:checkpoint-token", args=[station_a["id"]])
        ).data["data"]["token"]
        self.assertEqual(self.scan(b, token_a).status_code, 201)

        # The relaying student sees their live station...
        banner = self.auth(b).get(reverse("student-station"))
        self.assertEqual(banner.status_code, 200)
        self.assertEqual(banner.data["data"]["course_code"], "FET101")
        self.assertEqual(banner.data["data"]["mode"], "STATIONS")
        self.assertEqual(banner.data["data"]["source"], "CASCADE")

        # ...a student with no station sees an honest null, never an error.
        quiet = self.auth(self.students[4]).get(reverse("student-station"))
        self.assertEqual(quiet.status_code, 200)
        self.assertIsNone(quiet.data["data"])

        # The same prefix carries the student's own history.
        history = self.auth(b).get(reverse("student-attendance"))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data["data"]), 1)
        self.assertNotIn("student", history.data["data"][0])

    def test_session_rows_expose_mode_and_live_headcount(self):
        session = self.start(duration_seconds=120, mode="STATIONS")
        listing = self.auth(self.lecturer).get(reverse("attendance:session-list"))
        row = listing.data["data"][0]
        self.assertEqual(row["mode"], "STATIONS")
        self.assertTrue(row["is_active"])
        self.assertEqual(row["expected_headcount"], 5)
        self.assertEqual(row["present"], 0)
        self.assertEqual(row["headcount_remaining"], 5)

        detail = self.auth(self.lecturer).get(
            reverse("attendance:session-detail", args=[session["id"]])
        )
        self.assertEqual(detail.data["data"]["mode"], "STATIONS")
        self.assertEqual(detail.data["data"]["expected_headcount"], 5)
        self.assertEqual(len(detail.data["data"]["eligible_students"]), 5)

    # ---- The flexible start path (the UI's "Start session") ----------------

    def _offering(self):
        faculty = Faculty.objects.create(name="Two Mode Faculty")
        department = Department.objects.create(
            name="Two Mode Department", code="TMD", faculty=faculty
        )
        self.course.department = department
        self.course.save(update_fields=["department"])
        year = SchoolYear.objects.create(
            name="2033/2034", start_date=date(2033, 9, 1), end_date=date(2034, 6, 30)
        )
        semester = Semester.objects.create(
            school_year=year,
            name="First",
            start_date=date(2033, 9, 1),
            end_date=date(2034, 1, 31),
        )
        return CourseOffering.objects.create(
            course=self.course,
            semester=semester,
            department=department,
            lecturer=self.lecturer,
        )

    def _offer_roster(self, offering):
        """Attach the existing roster to the offering (enrollment is scoped)."""
        Enrollment.objects.filter(
            student__in=self.students, course=self.course
        ).update(course_offering=offering)

    def test_start_flex_honours_the_requested_mode(self):
        offering = self._offering()
        self._offer_roster(offering)

        stations = self.auth(self.lecturer).post(
            reverse("attendance:start-flex"),
            {"offering_id": str(offering.id), "duration_seconds": 120, "mode": "STATIONS"},
            format="json",
        )
        self.assertEqual(stations.status_code, 201, stations.data)
        self.assertEqual(stations.data["data"]["mode"], "STATIONS")
        session_id = stations.data["data"]["id"]

        # The requested mode is not cosmetic: seeding works on this session.
        seeded = self.auth(self.lecturer).post(
            reverse("attendance:session-checkpoints", args=[session_id]),
            {"student_ids": [str(self.students[0].id)]},
            format="json",
        )
        self.assertEqual(seeded.status_code, 201, seeded.data)

        self.auth(self.lecturer).post(
            reverse("attendance:session-close", args=[session_id])
        )
        defaulted = self.auth(self.lecturer).post(
            reverse("attendance:start-flex"),
            {"offering_id": str(offering.id), "duration_seconds": 120},
            format="json",
        )
        self.assertEqual(defaulted.status_code, 201, defaulted.data)
        self.assertEqual(defaulted.data["data"]["mode"], "PROJECTOR")
