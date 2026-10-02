"""Enrollment API tests (BR-010 to BR-015).

The enrollment service already existed without an HTTP surface; these tests
cover the endpoints that now expose it, including the audit trail and the
self-service authorization rule.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academic.models import Course, Department, Enrollment, Faculty
from apps.accounts.models import User
from core.models import AuditEvent

GHOST = "22222222-2222-2222-2222-222222222222"


class EnrollmentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        faculty = Faculty.objects.create(name="Engineering")
        department = Department.objects.create(name="Computer Engineering", faculty=faculty)
        self.course = Course.objects.create(
            code="CEF444", name="AI and Machine Learning", department=department
        )
        self.other = Course.objects.create(
            code="CEF450", name="Cloud Computing", department=department
        )

        self.student = User.objects.create_user(
            "enrol-student@example.test",
            "enrol-student",
            "Stu",
            "Dent",
            "StrongPass!2026",
        )
        self.other_student = User.objects.create_user(
            "enrol-other@example.test",
            "enrol-other",
            "Oth",
            "Er",
            "StrongPass!2026",
        )
        self.lecturer = User.objects.create_user(
            "enrol-lect@example.test",
            "enrol-lect",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.admin = User.objects.create_user(
            "enrol-admin@example.test",
            "enrol-admin",
            "Ad",
            "Min",
            "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )

    # ---------- list ----------

    def test_requires_authentication(self):
        response = self.client.get(reverse("academic:enrollment-list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_lists_only_own_active_enrollments(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        Enrollment.objects.create(
            student=self.student, course=self.other, is_active=False, status="inactive"
        )
        Enrollment.objects.create(student=self.other_student, course=self.other)

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("academic:enrollment-list"))
        self.assertEqual(response.status_code, 200)
        rows = response.data["data"]
        # Only the caller's own ACTIVE enrollment — BR-012 roster definition.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["course"], str(self.course.pk))
        self.assertEqual(rows[0]["course_code"], "CEF444")
        # A peer's enrollment must never appear.
        self.assertNotIn(str(self.other.pk), [r["course"] for r in rows])

    # ---------- create ----------

    def test_student_enrolls_self(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Enrollment.objects.filter(student=self.student, course=self.course, is_active=True).exists()
        )
        # BR-210: enrollment changes attendance eligibility — must be audited.
        self.assertTrue(AuditEvent.objects.filter(action="course_enrolled").exists())

    def test_duplicate_enrollment_is_conflict(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "ALREADY_ENROLLED")

    def test_unknown_course_is_not_found(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": GHOST},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("course", response.data["error"]["message"])

    def test_student_cannot_enroll_someone_else(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk), "student": str(self.other_student.pk)},
            format="json",
        )
        # BR-010: self-service only. A denial must not confirm the target exists.
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Enrollment.objects.filter(student=self.other_student).exists())

    def test_lecturer_cannot_enroll(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk), "student": str(self.student.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_enroll_another_student(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk), "student": str(self.student.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Enrollment.objects.filter(student=self.student, course=self.course).exists()
        )

    # ---------- drop ----------

    def test_drop_deactivates_without_deleting(self):
        record = Enrollment.objects.create(student=self.student, course=self.course)
        self.client.force_authenticate(user=self.student)
        response = self.client.delete(
            reverse("academic:enrollment-drop", args=[self.course.pk])
        )
        self.assertEqual(response.status_code, 200)
        # BR-014/BR-015: the row survives, deactivated.
        record.refresh_from_db()
        self.assertFalse(record.is_active)
        self.assertEqual(record.status, "inactive")
        self.assertTrue(AuditEvent.objects.filter(action="course_dropped").exists())

    def test_drop_when_not_enrolled_is_not_found(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.delete(
            reverse("academic:enrollment-drop", args=[self.other.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_drop_someone_else(self):
        Enrollment.objects.create(student=self.other_student, course=self.course)
        self.client.force_authenticate(user=self.student)
        response = self.client.delete(
            reverse("academic:enrollment-drop", args=[self.course.pk])
            + f"?student={self.other_student.pk}"
        )
        self.assertEqual(response.status_code, 403)
        record = Enrollment.objects.get(student=self.other_student, course=self.course)
        self.assertTrue(record.is_active)

    def test_reenroll_after_drop_reactivates(self):
        Enrollment.objects.create(
            student=self.student, course=self.course, is_active=False, status="inactive"
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Enrollment.objects.filter(student=self.student, course=self.course).count(), 1
        )
        self.assertTrue(
            Enrollment.objects.get(student=self.student, course=self.course).is_active
        )

    def test_unexpected_field_rejected(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:enrollment-list"),
            {"course": str(self.course.pk), "role": "ADMINISTRATOR"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
