"""Tests for the student results and classroom endpoints.

Three contracts are pinned here, because each was a live frontend-to-backend
gap:

* ``GET /students/me/assessments/`` — the Continuous Assessment page. The
  client shape is ``{ assessments: [...], summary: {...} }``.
* ``GET /classrooms/`` — the My Courses / Classrooms cards, whose two roles
  render genuinely different figures.
* ``GET /classrooms/available-courses/`` — the lecturer's classroom picker.

Beyond shape, the security properties matter more than the counts:

* BR-131. A student sees only **their own released** results. A draft result
  is not visible, and ``private_notes`` never leaves the server on the student
  path — asserted directly, not assumed.
* Cross-account reads are impossible: no request field names another student,
  and the scoping tests prove a second student sees none of the first.
* A student cannot reach the staff-shaped classroom payload.
"""

from decimal import Decimal

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)
from apps.announcements.models import Announcement
from apps.assessments.models import Assessment
from apps.files.models import LearningMaterial, UploadedFile


class AcademicFixture(TestCase):
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
            "sc-lect@fet.edu", "sc-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "sc-stu@fet.edu", "sc-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            "sc-other@fet.edu", "sc-other", "Oth", "Er", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.admin = User.objects.create_user(
            "sc-admin@fet.edu", "sc-admin", "Ad", "Min", "StrongPass!2026",
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
        Enrollment.objects.create(
            student=self.student, course=self.course, course_offering=self.offering
        )


class StudentAssessmentsTests(AcademicFixture):
    def _make(self, *, student, released=True, score="72.50", notes="private",
              status=Assessment.Status.OFFICIAL):
        return Assessment.objects.create(
            student=student,
            course=self.course,
            score=Decimal(score),
            status=status,
            released=released,
            private_notes=notes,
            created_by=self.lecturer,
        )

    def test_anonymous_is_denied_with_the_standard_envelope(self):
        response = self.client.get(reverse("student-assessments"))
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIn("error", body)

    def test_lecturer_cannot_use_the_student_results_endpoint(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(reverse("student-assessments"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "FORBIDDEN")

    def test_student_receives_the_client_aggregate_shape(self):
        self._make(student=self.student)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("student-assessments"))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        data = body["data"]
        # Destructured by ContinuousAssessment.jsx as { assessments, groups }.
        self.assertIn("assessments", data)
        self.assertIn("summary", data)
        self.assertIsInstance(data["assessments"], list)
        self.assertEqual(len(data["assessments"]), 1)

        row = data["assessments"][0]
        self.assertEqual(row["course_code"], "CS401")
        self.assertEqual(row["score"], "72.50")
        self.assertEqual(row["status"], "official")
        self.assertTrue(row["released"])
        self.assertEqual(data["summary"]["total_assessments"], 1)
        self.assertEqual(data["summary"]["average_score"], 72.5)

    def test_unreleased_results_are_not_visible_to_the_student(self):
        """BR-131: only released assessments are student-visible."""
        self._make(student=self.student, released=False)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("student-assessments"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["assessments"], [])
        self.assertEqual(response.json()["data"]["summary"]["total_assessments"], 0)

    def test_private_notes_never_leave_for_a_student(self):
        """BR-131: private lecturer notes are suppressed, key present but null."""
        self._make(student=self.student, notes="must not leak to the student")
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("student-assessments"))
        row = response.json()["data"]["assessments"][0]
        self.assertIn("private_notes", row)
        self.assertIsNone(row["private_notes"])
        self.assertNotIn("must not leak", response.content.decode("utf-8"))

    def test_a_student_cannot_read_another_students_results(self):
        self._make(student=self.student, score="91.00")
        self._make(student=self.other_student, score="33.00")

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("student-assessments"))
        rows = response.json()["data"]["assessments"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["student"], str(self.student.pk))
        self.assertNotIn("33.00", response.content.decode("utf-8"))

    def test_results_are_scoped_to_the_caller_even_with_no_filter(self):
        self._make(student=self.other_student)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("student-assessments"))
        self.assertEqual(response.json()["data"]["assessments"], [])


class ClassroomListTests(AcademicFixture):
    def _material(self, offering):
        # A material is only reachable through its uploaded file, so the
        # fixture has to build the whole chain rather than the leaf alone.
        uploaded = UploadedFile.objects.create(
            course_offering=offering,
            uploaded_by=self.lecturer,
            file=ContentFile(b"%PDF-1.4 test", name="notes.pdf"),
            original_name="notes.pdf",
            mime_type="application/pdf",
            size_bytes=12,
            sha256="0" * 64,
        )
        return LearningMaterial.objects.create(
            title="Week 1 notes",
            course_offering=offering,
            uploaded_by=self.lecturer,
            file=uploaded,
        )

    def test_anonymous_is_denied(self):
        response = self.client.get(reverse("academic:classroom-list"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_enrolled_student_gets_the_student_card_shape(self):
        self._material(self.offering)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("academic:classroom-list"))

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["semester"], "Semester 1")
        self.assertEqual(len(data["courses"]), 1)

        course = data["courses"][0]
        self.assertEqual(course["course_code"], "CS401")
        self.assertEqual(course["course_title"], "Distributed Systems")
        self.assertEqual(course["materials_count"], 1)
        # Student cards read department and announcements, never staffing.
        self.assertEqual(course["department"], "Engineering")
        self.assertIn("announcements_count", course)
        self.assertNotIn("enrolled_students", course)

    def test_staff_card_carries_enrollment_count(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(reverse("academic:classroom-list"))
        data = response.json()["data"]
        course = data["courses"][0]
        # The staff card renders Students; the student card never sees this.
        self.assertEqual(course["enrolled_students"], 1)
        self.assertEqual(course["lecturer_name"], "Lect Urer")

    def test_announcement_counter_counts_published_for_the_course(self):
        Announcement.objects.create(
            title="Lab moved",
            body="Room 4.",
            scope="course",
            course=self.course,
            is_published=True,
            created_by=self.lecturer,
        )
        # An unpublished announcement must not be counted.
        Announcement.objects.create(
            title="Draft",
            body="Not yet.",
            scope="course",
            course=self.course,
            is_published=False,
            created_by=self.lecturer,
        )
        self.client.force_authenticate(user=self.student)
        data = self.client.get(reverse("academic:classroom-list")).json()["data"]
        self.assertEqual(data["courses"][0]["announcements_count"], 1)

    def test_unenrolled_student_sees_no_classrooms(self):
        self.client.force_authenticate(user=self.other_student)
        data = self.client.get(reverse("academic:classroom-list")).json()["data"]
        self.assertEqual(data["courses"], [])


class ClassroomAvailableCoursesTests(AcademicFixture):
    def test_anonymous_is_denied(self):
        response = self.client.get(reverse("academic:classroom-available-courses"))
        self.assertEqual(response.status_code, 403)

    def test_lecturer_sees_their_own_offerings(self):
        other = CourseOffering.objects.create(
            course=Course.objects.create(code="CS402", name="Other", department=self.department),
            semester=self.semester,
            department=self.department,
            lecturer=User.objects.create_user(
                "sc-lect2@fet.edu", "sc-lect2", "L2", "U", "StrongPass!2026",
                role=User.Role.LECTURER,
            ),
        )
        self.client.force_authenticate(user=self.lecturer)
        data = self.client.get(reverse("academic:classroom-available-courses")).json()["data"]

        codes = {c["course_code"] for c in data["courses"]}
        self.assertEqual(codes, {"CS401"})
        self.assertNotIn("CS402", codes)

    def test_student_gets_an_empty_picker_not_a_catalogue(self):
        """A student cannot enumerate offerings they are not enrolled in."""
        self.client.force_authenticate(user=self.student)
        data = self.client.get(reverse("academic:classroom-available-courses")).json()["data"]
        self.assertEqual(data["courses"], [])
