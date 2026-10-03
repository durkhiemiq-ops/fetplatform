from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

from .models import Course, CourseOffering, Department, Enrollment, Faculty, SchoolYear, Semester


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
        self.student.level = ""
        self.student.save(update_fields=["level"])
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
