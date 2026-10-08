"""Accepted project decision A: what the lecturer's "Create class" means.

The spec does document class creation — API Specification §22 is
``POST /api/v1/course-offerings/{offering_id}/classes/`` and §23 distinguishes
an individual *session* from the class it belongs to. What it does **not**
prescribe is ``POST /classrooms/`` or the shape that route had, which is the
one the client was calling (and which has never had a POST handler).

So the decision under test is:

* "Create class" creates an **academic class definition under an existing,
  authorized offering** — not a course, not an offering, not an enrollment
  list, and not a second student workspace.
* The canonical offering-scoped endpoint is the only write. ``POST
  /classrooms/`` stays unrouted, and ``GET /classrooms/`` keeps its read
  contract (it lists offering workspaces keyed by ``offering_id``).
* Scope is checked server-side from the URL and the session. An ownership,
  role or enrollment field in the body is rejected, never trusted.
* Eligibility stays derived from active enrollment (BR-011/BR-022); creating
  a class copies no roster and duplicates no rows.
* There is deliberately no name-uniqueness rule and no recurrence parser.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    ClassSchedule,
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)
from core.models import AuditEvent


def classes_url(offering):
    return f"/api/v1/course-offerings/{offering.pk}/classes/"


def schedules_url(offering):
    return f"/api/v1/course-offerings/{offering.pk}/schedules/"


class ClassCreationFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.department = Department.objects.create(name="Engineering", code="ENG")
        year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date() - timedelta(days=100),
            end_date=timezone.now().date() + timedelta(days=200),
        )
        self.semester = Semester.objects.create(
            school_year=year,
            name="Semester 1",
            start_date=timezone.now().date() - timedelta(days=20),
            end_date=timezone.now().date() + timedelta(days=80),
            is_current=True,
        )

        self.lecturer = User.objects.create_user(
            "cc-lect@fet.edu", "cc-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.other_lecturer = User.objects.create_user(
            "cc-other-lect@fet.edu", "cc-other-lect", "Oth", "Er", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        # Signed up, not yet approved: role alone is not authority.
        self.pending_lecturer = User.objects.create_user(
            "cc-pending@fet.edu", "cc-pending", "Pen", "Ding", "StrongPass!2026",
            role=User.Role.LECTURER,
            lecturer_approval_status=User.LecturerApproval.PENDING,
        )
        self.student = User.objects.create_user(
            "cc-stu@fet.edu", "cc-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.admin = User.objects.create_user(
            "cc-admin@fet.edu", "cc-admin", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )

        self.course = Course.objects.create(
            code="CS401", name="Distributed Systems", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        self.other_course = Course.objects.create(
            code="CS402", name="Compilers", department=self.department
        )
        self.other_offering = CourseOffering.objects.create(
            course=self.other_course,
            semester=self.semester,
            department=self.department,
            lecturer=self.other_lecturer,
        )
        # The student's eligibility comes from the backend enrollment row and
        # from nowhere else — there is no client-side enrollment to fall back on.
        Enrollment.objects.create(
            student=self.student, course=self.course, course_offering=self.offering
        )

    # -- helpers ----------------------------------------------------------

    def authenticate(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def create_class(self, user, offering=None, **body):
        payload = {"name": "Week 1 lecture"}
        payload.update(body)
        return self.authenticate(user).post(
            classes_url(offering or self.offering), payload, format="json"
        )


class ClassDefinitionCreationTests(ClassCreationFixture):
    def test_lecturer_creates_a_class_and_gets_a_persisted_identity(self):
        response = self.create_class(
            self.lecturer, class_type="TUTORIAL", location="LT-2"
        )

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["success"])
        data = body["data"]
        # 201 with an identity the client can address afterwards.
        self.assertTrue(data["id"])
        self.assertEqual(data["course_offering"], str(self.offering.pk))
        self.assertEqual(data["name"], "Week 1 lecture")
        self.assertEqual(data["class_type"], "TUTORIAL")
        self.assertEqual(data["location"], "LT-2")
        self.assertEqual(data["status"], "ACTIVE")
        self.assertTrue(data["is_active"])

        persisted = ClassSchedule.objects.get(pk=data["id"])
        self.assertEqual(persisted.name, "Week 1 lecture")
        self.assertEqual(persisted.lecturer, self.lecturer)
        self.assertEqual(persisted.course_offering, self.offering)
        self.assertIsNone(persisted.day_of_week)
        self.assertIsNone(persisted.start_time)
        self.assertIsNone(persisted.end_time)

    def test_the_created_class_reads_back_through_the_same_route(self):
        created = self.create_class(self.lecturer)
        self.assertEqual(created.status_code, 201, created.content)
        class_id = created.json()["data"]["id"]

        listing = self.authenticate(self.lecturer).get(classes_url(self.offering))

        self.assertEqual(listing.status_code, 200, listing.content)
        rows = listing.json()["data"]
        self.assertEqual(len(rows), 1)
        # Its own id, never a substituted offering id.
        self.assertEqual(rows[0]["id"], class_id)
        self.assertEqual(rows[0]["course_offering"], str(self.offering.pk))

    def test_creation_writes_the_documented_audit_entry(self):
        response = self.create_class(self.lecturer)
        self.assertEqual(response.status_code, 201, response.content)
        class_id = response.json()["data"]["id"]

        self.assertTrue(
            AuditEvent.objects.filter(
                action="class_definition_created",
                resource_type="class_definition",
                resource_id=class_id,
                actor_id=self.lecturer.pk,
            ).exists()
        )

    def test_administrator_may_create_a_class_for_any_offering(self):
        response = self.create_class(self.admin)
        self.assertEqual(response.status_code, 201, response.content)

    def test_student_enrolled_in_the_offering_still_cannot_create_a_class(self):
        """Eligibility to *see* a class is not authority to create one."""
        response = self.create_class(self.student)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["error"]["code"], "FORBIDDEN")
        self.assertFalse(ClassSchedule.objects.exists())

    def test_another_lecturers_offering_is_not_addressable(self):
        """A caller-scoped miss answers 404, identical to an unknown id (§25)."""
        response = self.create_class(self.other_lecturer, offering=self.offering)

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertFalse(ClassSchedule.objects.exists())

    def test_a_pending_lecturer_is_refused_even_on_their_own_offering(self):
        # A course of its own: an offering is unique per (course, semester).
        pending_course = Course.objects.create(
            code="CS403", name="Operating Systems", department=self.department
        )
        pending_offering = CourseOffering.objects.create(
            course=pending_course,
            semester=self.semester,
            department=self.department,
            lecturer=self.pending_lecturer,
        )
        response = self.create_class(
            self.pending_lecturer, offering=pending_offering
        )

        self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(ClassSchedule.objects.exists())

    def test_anonymous_is_refused_with_the_envelope(self):
        response = self.client.post(
            classes_url(self.offering), {"name": "Week 1 lecture"}, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(response.json()["success"])

    def test_same_offering_differs_from_unknown_offering_id(self):
        """The two must not diverge — otherwise ownership can be probed."""
        unknown = "00000000-0000-0000-0000-000000000000"
        outsider = self.authenticate(self.other_lecturer).post(
            f"/api/v1/course-offerings/{unknown}/classes/",
            {"name": "Week 1 lecture"},
            format="json",
        )
        scoped = self.create_class(self.other_lecturer, offering=self.offering)

        self.assertEqual(outsider.status_code, scoped.status_code)
        self.assertEqual(
            outsider.json()["error"]["code"], scoped.json()["error"]["code"]
        )


class ClassDefinitionValidationTests(ClassCreationFixture):
    def test_name_is_required(self):
        response = self.authenticate(self.lecturer).post(
            classes_url(self.offering), {"class_type": "LECTURE"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.json()["error"]["message"])

    def test_a_blank_name_is_refused(self):
        response = self.create_class(self.lecturer, name="   ")
        self.assertEqual(response.status_code, 400, response.content)

    def test_ownership_role_and_enrollment_fields_are_rejected(self):
        """The body is never allowed to say who owns or who is enrolled."""
        for field, value in (
            ("lecturer", str(self.other_lecturer.pk)),
            ("owner", str(self.admin.pk)),
            ("course_offering", str(self.other_offering.pk)),
            ("role", "ADMINISTRATOR"),
            ("enrollment", str(self.student.pk)),
            ("enrollments", [str(self.student.pk)]),
            ("auto_enroll", True),
            ("is_active", False),
            ("status", "INACTIVE"),
        ):
            with self.subTest(field=field):
                response = self.create_class(self.lecturer, **{field: value})
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("not permitted", response.json()["error"]["message"])
                self.assertFalse(ClassSchedule.objects.exists())

    def test_recurrence_rule_is_refused_rather_than_silently_dropped(self):
        """API §22's example carries it; this implementation has no parser.

        Telling the client is the point: silently ignoring the key would make
        a caller believe a recurrence had been scheduled.
        """
        response = self.create_class(
            self.lecturer, recurrence_rule="FREQ=WEEKLY;BYDAY=MO"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("recurrence_rule", response.json()["error"]["message"])
        self.assertFalse(ClassSchedule.objects.exists())

    def test_a_partial_weekly_slot_is_refused(self):
        response = self.create_class(self.lecturer, day_of_week="MONDAY")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("together", response.json()["error"]["message"])
        self.assertFalse(ClassSchedule.objects.exists())

    def test_a_complete_weekly_slot_is_stored(self):
        response = self.create_class(
            self.lecturer,
            day_of_week="MONDAY",
            start_time="10:00",
            end_time="11:00",
        )
        self.assertEqual(response.status_code, 201, response.content)

        persisted = ClassSchedule.objects.get()
        self.assertEqual(persisted.day_of_week, "MONDAY")
        self.assertEqual(str(persisted.start_time), "10:00:00")
        self.assertEqual(str(persisted.end_time), "11:00:00")

    def test_end_before_start_is_refused(self):
        response = self.create_class(
            self.lecturer,
            day_of_week="MONDAY",
            start_time="11:00",
            end_time="10:00",
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_an_overlapping_slot_returns_409(self):
        self.create_class(
            self.lecturer, day_of_week="MONDAY", start_time="10:00", end_time="11:00"
        )

        overlap = self.create_class(
            self.lecturer,
            name="Week 1 tutorial",
            day_of_week="MONDAY",
            start_time="10:30",
            end_time="11:30",
        )

        self.assertEqual(overlap.status_code, 409, overlap.content)
        self.assertEqual(ClassSchedule.objects.count(), 1)

    def test_the_same_name_twice_is_allowed(self):
        """No invented uniqueness rule — repeated lecture definitions are fine."""
        first = self.create_class(self.lecturer, name="Lecture")
        second = self.create_class(self.lecturer, name="Lecture")

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(ClassSchedule.objects.count(), 2)

    def test_an_unrecognised_class_type_is_refused(self):
        # `PRACTICAL` is *not* used here on purpose: DB Design §19 names it but
        # `ClassSchedule.ClassType` does not carry it, and that divergence is
        # reported rather than silently resolved by widening the choices (a
        # choices change also perturbs `makemigrations --check`).
        response = self.create_class(self.lecturer, class_type="LECTURE_HALL")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("class_type", response.json()["error"]["message"])


class ClassDefinitionScopeTests(ClassCreationFixture):
    def test_creating_a_class_creates_nothing_else(self):
        """Eligibility is enrollment; creation must not manufacture any."""
        before = {
            "courses": Course.objects.count(),
            "offerings": CourseOffering.objects.count(),
            "enrollments": Enrollment.objects.count(),
            "sessions": ClassSession.objects.count(),
        }

        response = self.create_class(self.lecturer, name="Lecture")
        self.assertEqual(response.status_code, 201, response.content)

        self.assertEqual(Course.objects.count(), before["courses"])
        self.assertEqual(CourseOffering.objects.count(), before["offerings"])
        self.assertEqual(Enrollment.objects.count(), before["enrollments"])
        # ClassSession is the individual session entity (API §23); creating a
        # class definition must never touch it.
        self.assertEqual(ClassSession.objects.count(), before["sessions"])
        self.assertEqual(ClassSchedule.objects.count(), 1)

    def test_a_class_never_copies_a_roster(self):
        """BR-011/BR-022: eligibility is derived, never manufactured here."""
        before = set(Enrollment.objects.values_list("pk", flat=True))

        self.create_class(self.lecturer, name="Lecture")

        after = set(Enrollment.objects.values_list("pk", flat=True))
        self.assertEqual(before, after)
        # The only enrollment is the one that predates the call.
        self.assertEqual(Enrollment.objects.filter(course=self.course).count(), 1)

    def test_student_sees_the_class_on_their_enrolled_offering(self):
        """The read side of eligibility: enrolled, so visible."""
        self.create_class(self.lecturer, name="Lecture")

        listing = self.authenticate(self.student).get(classes_url(self.offering))
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual(len(listing.json()["data"]), 1)

    def test_student_sees_nothing_on_an_offering_they_are_not_enrolled_in(self):
        self.create_class(self.other_lecturer, offering=self.other_offering)

        listing = self.authenticate(self.student).get(
            classes_url(self.other_offering)
        )
        self.assertEqual(listing.status_code, 404, listing.content)


class ReadContractPreservationTests(ClassCreationFixture):
    """The old read surfaces must not have been consumed by the new write."""

    def test_classrooms_list_still_returns_offering_workspaces(self):
        self.create_class(self.lecturer, name="Lecture")

        response = self.authenticate(self.lecturer).get("/api/v1/classrooms/")

        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["data"]["courses"]
        # Still keyed by offering id, not by the class that now exists under it.
        self.assertTrue(all("offering_id" in row for row in rows))
        self.assertIn(str(self.offering.pk), [row["offering_id"] for row in rows])
        # The read contract is about workspaces; the class did not replace one.
        self.assertNotIn("id", rows[0] if rows else {})
        self.assertTrue(all("course_code" in row for row in rows))

    def test_post_to_classrooms_is_still_not_routed(self):
        """No competing write endpoint appears alongside the canonical one."""
        response = self.authenticate(self.lecturer).post(
            "/api/v1/classrooms/", {"name": "Week 1 lecture"}, format="json"
        )
        self.assertEqual(response.status_code, 405, response.content)
        self.assertFalse(ClassSchedule.objects.exists())

    def test_the_timetable_shows_only_scheduled_classes(self):
        """An unscheduled definition has no slot and must not render a null row."""
        self.create_class(self.lecturer, name="Unscheduled lecture")
        self.create_class(
            self.lecturer,
            name="Scheduled lecture",
            day_of_week="MONDAY",
            start_time="10:00",
            end_time="11:00",
        )

        scheduled = self.authenticate(self.lecturer).get(schedules_url(self.offering))
        self.assertEqual(scheduled.status_code, 200, scheduled.content)
        rows = scheduled.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Scheduled lecture")
        self.assertIsNotNone(rows[0]["day_of_week"])

        classes = self.authenticate(self.lecturer).get(classes_url(self.offering))
        self.assertEqual(len(classes.json()["data"]), 2)
