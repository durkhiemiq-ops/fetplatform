"""``seed_demo`` must hand both demo roles something to look at.

The seed historically stopped at courses, one legacy ``ClassSession`` per
course and offering-less enrollments. Because ``GET /lecturers/me/courses/``
reads ``CourseOffering`` and ``GET /students/me/courses/`` only returns
enrollments that carry one, a freshly seeded database opened on empty lists
for *both* demo roles. That is a demo-data defect rather than an application
defect, but it made the shipped example accounts useless for a walkthrough.

Pinned here:

- one current semester, unique, whose window contains today and whose
  registration deadline is still open (the seed's own promise of a usable
  first login);
- every demo offering visible to the demo lecturer through the real endpoint;
- one named class definition per offering — Decision A: a class definition
  under an authorized offering, never a ``ClassSession``;
- demo student enrollments visible through the real student endpoint;
- idempotency, so re-running the seed cannot duplicate anything.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import (
    ClassSchedule,
    ClassSession,
    CourseOffering,
    Enrollment,
    Semester,
)
from apps.accounts.models import User
from apps.notifications.models import Notification

DEMO_COURSES = {"CEF444", "CEF450", "CEF462", "CEF476", "SE401", "CS301", "ME301"}
STUDENT_COURSES = {"CEF444", "CEF450", "CEF462", "CEF476"}


def run_seed():
    call_command("seed_demo", stdout=StringIO(), stderr=StringIO())


@override_settings(DEBUG=True)
class SeedDemoPopulationTests(TestCase):
    """A freshly seeded database must render for the demo lecturer/student."""

    def setUp(self):
        self.client = APIClient()
        run_seed()

    def test_one_current_semester_whose_window_contains_today(self):
        today = timezone.localdate()
        current = Semester.objects.filter(is_current=True)
        self.assertEqual(current.count(), 1)
        term = current.get()
        self.assertTrue(term.start_date <= today <= term.end_date)
        self.assertIsNotNone(term.registration_deadline)
        self.assertGreaterEqual(term.registration_deadline, today)

    def test_lecturer_courses_endpoint_lists_every_demo_offering(self):
        lecturer = User.objects.get(email="alida.vance@fet.edu")
        self.client.force_authenticate(user=lecturer)
        response = self.client.get("/api/v1/lecturers/me/courses/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["data"]
        self.assertEqual({row["course_code"] for row in rows}, DEMO_COURSES)
        for row in rows:
            self.assertTrue(str(row["offering_id"]))
            self.assertTrue(str(row["id"]))

    def test_every_offering_carries_one_named_class_definition(self):
        offerings = CourseOffering.objects.select_related("course", "lecturer")
        self.assertEqual(offerings.count(), len(DEMO_COURSES))
        for offering in offerings:
            classes = ClassSchedule.objects.filter(
                course_offering=offering, is_active=True
            )
            self.assertEqual(classes.count(), 1, offering.course.code)
            definition = classes.get()
            self.assertTrue(definition.name)
            self.assertEqual(definition.lecturer_id, offering.lecturer_id)
            self.assertIsNotNone(definition.day_of_week)
            self.assertIsNotNone(definition.start_time)
            self.assertLess(definition.start_time, definition.end_time)
            self.assertTrue(definition.location)

    def test_seeding_a_class_definition_never_creates_a_class_session(self):
        # Decision A: "Create class" is a class definition under an offering.
        # The legacy ClassSession anchor must stay exactly as seeded.
        self.assertEqual(ClassSession.objects.count(), len(DEMO_COURSES))

    def test_student_courses_endpoint_lists_offerings_backed_enrollments(self):
        student = User.objects.get(email="alex.scholar@fet.edu")
        self.client.force_authenticate(user=student)
        response = self.client.get("/api/v1/students/me/courses/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["data"]
        self.assertEqual({row["course_code"] for row in rows}, STUDENT_COURSES)
        for row in rows:
            self.assertTrue(str(row["offering_id"]))
            self.assertTrue(row["is_enrolled"])

    def test_every_demo_enrollment_points_at_an_offering(self):
        for email in ("alex.scholar@fet.edu", "emma.watson@fet.edu"):
            student = User.objects.get(email=email)
            rows = Enrollment.objects.filter(student=student, is_active=True)
            self.assertEqual(rows.count(), len(STUDENT_COURSES), email)
            self.assertTrue(
                all(row.course_offering_id is not None for row in rows), email
            )


@override_settings(DEBUG=True)
class SeedDemoIdempotencyTests(TestCase):
    """Re-running the seed must not duplicate rows."""

    def test_second_run_adds_no_rows(self):
        run_seed()
        tracked = [
            User,
            ClassSession,
            ClassSchedule,
            CourseOffering,
            Enrollment,
            Semester,
            Notification,
        ]
        before = [Model.objects.count() for Model in tracked]
        run_seed()
        after = [Model.objects.count() for Model in tracked]
        self.assertEqual(before, after)
