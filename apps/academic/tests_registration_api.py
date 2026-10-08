from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

from .models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    Programme,
    ProgrammeLevel,
    SchoolYear,
    Semester,
    StudentAcademicProfile,
)


class StudentRegistrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(name="Computer Engineering", faculty=self.faculty)
        self.other_department = Department.objects.create(name="Electrical Engineering", faculty=self.faculty)
        self.year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=300),
        )
        self.semester = Semester.objects.create(
            school_year=self.year,
            name="Semester 1",
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() + timedelta(days=100),
            registration_deadline=timezone.localdate() + timedelta(days=5),
            is_current=True,
        )
        self.student = User.objects.create_user(
            "registration@example.test", "registration", "Reg", "Student",
            "StrongPass!2026", department=self.department, level="400",
        )
        # Enrollment scope is administrator-owned (MVP mandate s10): the
        # department/level on the User row above is an intake declaration and
        # is deliberately NOT what gates course access -- the profile is.
        self.programme = Programme.objects.create(
            department=self.department, code="CE-BSC", name="Computer Engineering"
        )
        self.level_400 = ProgrammeLevel.objects.create(
            programme=self.programme, code="400", name="Level 400"
        )
        self.profile = StudentAcademicProfile.objects.create(
            student=self.student, programme=self.programme,
            programme_level=self.level_400, cohort=2023,
        )
        self.lecturer = User.objects.create_user(
            "registration-lecturer@example.test", "registration-lecturer", "Lect", "Urer",
            "StrongPass!2026", role=User.Role.LECTURER, department=self.department,
        )
        self.course = Course.objects.create(
            code="CEF444", name="Secure Systems", department=self.department,
            level="400", credit_units=4,
        )
        self.offering = CourseOffering.objects.create(
            course=self.course, semester=self.semester, department=self.department,
            lecturer=self.lecturer,
        )

    def test_flat_available_courses_uses_server_profile(self):
        self.client.force_authenticate(self.student)
        response = self.client.get("/api/v1/students/me/available-courses/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["department"], self.department.name)
        self.assertEqual(response.data["data"]["level"], "400")
        self.assertEqual(response.data["data"]["courses"][0]["offering_id"], str(self.offering.id))

    def test_register_creates_audited_offering_enrollment(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            "/api/v1/students/me/register/",
            {"offering_ids": [str(self.offering.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        row = Enrollment.objects.get(student=self.student, course_offering=self.offering)
        self.assertEqual(row.course, self.course)
        self.assertEqual(row.enrolled_by, self.student)
        self.assertTrue(AuditEvent.objects.filter(
            action="course_offering_registered", resource_id=str(row.id)
        ).exists())

    def test_wrong_department_and_missing_id_are_indistinguishable(self):
        other_course = Course.objects.create(
            code="EEF444", name="Private Power Systems", department=self.other_department, level="400"
        )
        other = CourseOffering.objects.create(
            course=other_course, semester=self.semester, department=self.other_department
        )
        self.client.force_authenticate(self.student)
        foreign = self.client.post(
            "/api/v1/students/me/register/", {"offering_ids": [str(other.id)]}, format="json"
        )
        missing = self.client.post(
            "/api/v1/students/me/register/",
            {"offering_ids": ["11111111-1111-1111-1111-111111111111"]},
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(foreign.data, missing.data)
        self.assertFalse(Enrollment.objects.filter(student=self.student).exists())

    def test_wrong_level_is_not_offered_or_accepted(self):
        other_course = Course.objects.create(
            code="CEF544", name="Graduate Security", department=self.department, level="500"
        )
        other = CourseOffering.objects.create(
            course=other_course, semester=self.semester, department=self.department
        )
        self.client.force_authenticate(self.student)
        listing = self.client.get("/api/v1/students/me/available-courses/")
        ids = {row["offering_id"] for row in listing.data["data"]["courses"]}
        self.assertNotIn(str(other.id), ids)
        response = self.client.post(
            "/api/v1/students/me/register/", {"offering_ids": [str(other.id)]}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    # ---- client-declared level must never become enrollment authority ----

    def test_student_without_an_admin_profile_cannot_self_enroll(self):
        """MASTER-ACAD-01: the level posted at signup grants no course access.

        ``User.level`` is written by the public registration form, so it is
        client-controlled. Before this fix the legacy endpoint filtered courses
        on it directly, letting any applicant post ``level=400`` and obtain
        attendance/material eligibility for a cohort they never joined.
        """
        undeclared = User.objects.create_user(
            "undeclared@example.test", "undeclared", "Un", "Declared",
            "StrongPass!2026", department=self.department, level="400",
        )
        self.client.force_authenticate(undeclared)
        listing = self.client.get("/api/v1/students/me/available-courses/")
        registration = self.client.post(
            "/api/v1/students/me/register/", {"offering_ids": [str(self.offering.id)]},
            format="json",
        )
        self.assertEqual(listing.status_code, 400)
        self.assertEqual(listing.data["error"]["code"], "INCOMPLETE_PROFILE")
        self.assertEqual(registration.status_code, 400)
        self.assertEqual(registration.data["error"]["code"], "INCOMPLETE_PROFILE")
        self.assertFalse(Enrollment.objects.filter(student=undeclared).exists())

    def test_scope_follows_the_admin_profile_not_the_posted_level(self):
        """A posted level is ignored even when the profile says otherwise."""
        overreach = User.objects.create_user(
            "overreach@example.test", "overreach", "Ov", "Reach",
            "StrongPass!2026", department=self.department, level="400",
        )
        level_100 = ProgrammeLevel.objects.create(
            programme=self.programme, code="100", name="Level 100"
        )
        StudentAcademicProfile.objects.create(
            student=overreach, programme=self.programme,
            programme_level=level_100, cohort=2026,
        )
        self.client.force_authenticate(overreach)
        listing = self.client.get("/api/v1/students/me/available-courses/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"]["level"], "100")
        self.assertEqual(listing.data["data"]["courses"], [])
        registration = self.client.post(
            "/api/v1/students/me/register/", {"offering_ids": [str(self.offering.id)]},
            format="json",
        )
        self.assertEqual(registration.status_code, 400)
        self.assertFalse(Enrollment.objects.filter(student=overreach).exists())

    def test_expired_registration_deadline_blocks_reads_and_writes(self):
        self.semester.registration_deadline = timezone.localdate() - timedelta(days=1)
        self.semester.save()
        self.client.force_authenticate(self.student)
        listing = self.client.get("/api/v1/students/me/available-courses/")
        registration = self.client.post(
            "/api/v1/students/me/register/",
            {"offering_ids": [str(self.offering.id)]},
            format="json",
        )
        self.assertEqual(listing.status_code, 400)
        self.assertEqual(listing.data["error"]["code"], "REGISTRATION_CLOSED")
        self.assertEqual(registration.data["error"]["code"], "REGISTRATION_CLOSED")

    # ---- the gate must not be escapable via the legacy endpoint ----

    def test_legacy_course_endpoint_cannot_bypass_the_registration_gate(self):
        """A bounded gate is only as good as the absence of a looser door.

        ``POST /academic/enrollments/`` authorised a student purely on "is this
        my own id and am I a STUDENT" -- no department, level, semester,
        deadline or status check. Calling that route directly with any course
        uuid granted full attendance eligibility, making every rule above
        decorative. Self-enrollment now exists only on
        ``POST /students/me/register/``.
        """
        other_course = Course.objects.create(
            code="EEF555", name="Out-of-scope course",
            department=self.other_department, level="500",
        )
        self.client.force_authenticate(self.student)
        response = self.client.post(
            "/api/v1/academic/enrollments/",
            {"course": str(other_course.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Enrollment.objects.filter(student=self.student, course=other_course).exists()
        )

    def test_legacy_course_endpoint_cannot_bypass_a_closed_deadline(self):
        """Same door, used to escape a closed registration window."""
        self.semester.registration_deadline = timezone.localdate() - timedelta(days=1)
        self.semester.save()
        self.client.force_authenticate(self.student)
        response = self.client.post(
            "/api/v1/academic/enrollments/",
            {"course": str(self.course.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Enrollment.objects.filter(student=self.student, course=self.course).exists()
        )

    def test_admin_may_still_enrol_via_the_legacy_endpoint(self):
        """The endpoint remains the admin-mediated path; only self-service moves."""
        admin = User.objects.create_user(
            "reg-admin@example.test", "reg-admin", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_authenticate(admin)
        response = self.client.post(
            "/api/v1/academic/enrollments/",
            {"course": str(self.course.pk), "student": str(self.student.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Enrollment.objects.filter(student=self.student, course=self.course).exists()
        )

    def test_incomplete_profile_and_non_student_are_rejected(self):
        # The incomplete state is "no administrator-assigned profile". It used
        # to be triggered by clearing ``User.level``, but that field is
        # client-writable at signup and is no longer the enrollment gate
        # (MVP mandate s10), so clearing it proves nothing about access.
        self.profile.delete()
        self.client.force_authenticate(self.student)
        incomplete = self.client.get("/api/v1/students/me/available-courses/")
        self.assertEqual(incomplete.data["error"]["code"], "INCOMPLETE_PROFILE")
        self.client.force_authenticate(self.lecturer)
        lecturer = self.client.get("/api/v1/students/me/available-courses/")
        self.assertEqual(lecturer.status_code, 403)

    def test_unknown_fields_and_duplicate_ids_are_rejected(self):
        self.client.force_authenticate(self.student)
        unknown = self.client.post(
            "/api/v1/students/me/register/",
            {"offering_ids": [str(self.offering.id)], "role": "ADMINISTRATOR"},
            format="json",
        )
        duplicate = self.client.post(
            "/api/v1/students/me/register/",
            {"offering_ids": [str(self.offering.id), str(self.offering.id)]},
            format="json",
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)
        self.assertFalse(Enrollment.objects.filter(student=self.student).exists())
