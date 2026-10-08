"""Carry-over application tests (frontend ↔ backend contract + access rules).

The client's Carry-over page depends on three routes that did not exist before
this work: ``GET /carry-over/``, ``POST /carry-over/apply/`` and
``POST /carry-over/{id}/review/``. These pin both the contract and the access
model:

* a student sees only their own rows and can only apply for themselves;
* reviewing is staff-only, and the approval is what creates the enrollment
  (attendance eligibility therefore follows a real review);
* a decision is single-shot and atomic;
* denials use the project envelope, with unknown and unauthorized ids
  indistinguishable where §25 requires it.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    CarryOverApplication,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)


class CarryOverFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.department = Department.objects.create(name="Engineering", code="ENG")
        year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date() - timedelta(days=100),
            end_date=timezone.now().date() + timedelta(days=200),
        )
        semester = Semester.objects.create(
            school_year=year,
            name="Semester 1",
            start_date=timezone.now().date() - timedelta(days=20),
            end_date=timezone.now().date() + timedelta(days=80),
            is_current=True,
        )
        self.lecturer = User.objects.create_user(
            "co-lect@fet.edu", "co-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "co-stu@fet.edu", "co-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            "co-other@fet.edu", "co-other", "Oth", "Er", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.admin = User.objects.create_user(
            "co-admin@fet.edu", "co-admin", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )

        self.course = Course.objects.create(
            code="CS301", name="Operating Systems", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=semester,
            department=self.department,
            lecturer=self.lecturer,
        )

    def _apply(self, user, offering=None, reason="I failed this course"):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("academic:carry-over-apply"),
            {"course_offering_id": str((offering or self.offering).pk), "reason": reason},
            format="json",
        )

    def _review(self, user, application, decision="APPROVED", note="ok"):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("academic:carry-over-review", args=[application.pk]),
            {"decision": decision, "note": note},
            format="json",
        )


class CarryOverApplyTests(CarryOverFixture):
    def test_anonymous_is_denied(self):
        response = self.client.post(
            reverse("academic:carry-over-apply"),
            {"course_offering_id": str(self.offering.pk)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_student_can_apply_for_themselves(self):
        response = self._apply(self.student)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["status"], "PENDING")
        self.assertEqual(body["data"]["course_code"], "CS301")
        # The row names the applicant from the session, not the body.
        self.assertEqual(
            CarryOverApplication.objects.get().student_id, self.student.pk
        )

    def test_lecturer_cannot_apply(self):
        response = self._apply(self.lecturer)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "FORBIDDEN")

    def test_unknown_offering_returns_the_error_envelope(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:carry-over-apply"),
            {"course_offering_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "NOT_FOUND")

    def test_missing_offering_id_is_rejected(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("academic:carry-over-apply"), {"reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_duplicate_pending_application_is_blocked_by_the_database(self):
        self.assertEqual(self._apply(self.student).status_code, 201)
        response = self._apply(self.student)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        # The invariant: only one PENDING row survives the second attempt.
        self.assertEqual(
            CarryOverApplication.objects.filter(student=self.student).count(), 1
        )

    def test_already_enrolled_student_is_rejected(self):
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            course_offering=self.offering,
        )
        response = self._apply(self.student)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ALREADY_ENROLLED")


class CarryOverListTests(CarryOverFixture):
    def test_student_sees_only_their_own_applications(self):
        self._apply(self.student)
        self._apply(self.other_student)

        self.client.force_authenticate(user=self.student)
        body = self.client.get(reverse("academic:carry-over-list")).json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["student"], str(self.student.pk))

    def test_staff_see_the_whole_queue(self):
        self._apply(self.student)
        self._apply(self.other_student)

        for user in (self.lecturer, self.admin):
            with self.subTest(user=user.email):
                self.client.force_authenticate(user=user)
                body = self.client.get(reverse("academic:carry-over-list")).json()
                self.assertEqual(len(body["data"]), 2)

    def test_status_filter_does_not_widen_a_students_scope(self):
        self._apply(self.student)
        self._apply(self.other_student)

        self.client.force_authenticate(user=self.student)
        # Filtering for a status nobody in scope holds must return nothing,
        # not somebody else's rows.
        body = self.client.get(
            reverse("academic:carry-over-list"), {"status": "APPROVED"}
        ).json()
        self.assertEqual(body["data"], [])

        body = self.client.get(
            reverse("academic:carry-over-list"), {"status": "pending"}
        ).json()
        self.assertEqual(len(body["data"]), 1)


class CarryOverReviewTests(CarryOverFixture):
    def test_student_cannot_review(self):
        application = CarryOverApplication.objects.create(
            student=self.student, course_offering=self.offering
        )
        response = self._review(self.student, application)
        self.assertEqual(response.status_code, 403)
        application.refresh_from_db()
        self.assertEqual(application.status, "PENDING")

    def test_approval_creates_the_enrollment(self):
        application = CarryOverApplication.objects.create(
            student=self.student, course_offering=self.offering
        )
        response = self._review(self.lecturer, application, "APPROVED")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["data"]["enrolled"])

        application.refresh_from_db()
        self.assertEqual(application.status, "APPROVED")
        self.assertEqual(application.reviewed_by_id, self.lecturer.pk)

        enrollment = Enrollment.objects.get(
            student=self.student, course_offering=self.offering
        )
        self.assertTrue(enrollment.is_active)
        self.assertEqual(enrollment.course_id, self.course.pk)

    def test_rejection_does_not_enroll(self):
        application = CarryOverApplication.objects.create(
            student=self.student, course_offering=self.offering
        )
        response = self._review(self.lecturer, application, "REJECTED")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["enrolled"])
        application.refresh_from_db()
        self.assertEqual(application.status, "REJECTED")
        self.assertFalse(Enrollment.objects.filter(student=self.student).exists())

    def test_a_decision_cannot_be_replayed(self):
        application = CarryOverApplication.objects.create(
            student=self.student, course_offering=self.offering
        )
        self.assertEqual(
            self._review(self.lecturer, application, "APPROVED").status_code, 200
        )
        response = self._review(self.lecturer, application, "REJECTED")
        self.assertEqual(response.status_code, 409)
        application.refresh_from_db()
        self.assertEqual(application.status, "APPROVED")

    def test_invalid_decision_is_rejected(self):
        application = CarryOverApplication.objects.create(
            student=self.student, course_offering=self.offering
        )
        response = self._review(self.lecturer, application, "MAYBE")
        self.assertEqual(response.status_code, 400)
        application.refresh_from_db()
        self.assertEqual(application.status, "PENDING")

    def test_unknown_application_id_returns_the_same_404(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("academic:carry-over-review", args=["00000000-0000-0000-0000-000000000000"]),
            {"decision": "APPROVED"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
