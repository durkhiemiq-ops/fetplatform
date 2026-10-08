"""Adversarial regressions for the ongoing backend/frontend security review."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course
from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.projects.models import Project, ProjectGroup, ProjectGroupMembership


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SecurityBoundaryReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(
            "review-student@example.test", "review-student", "Review", "Student",
            "ReviewPassword!482", is_email_verified=True,
        )
        cls.lecturer = User.objects.create_user(
            "review-lecturer@example.test", "review-lecturer", "Review", "Lecturer",
            "ReviewPassword!482", role=User.Role.LECTURER,
        )
        cls.other_lecturer = User.objects.create_user(
            "review-other@example.test", "review-other", "Other", "Lecturer",
            "ReviewPassword!482", role=User.Role.LECTURER,
        )
        cls.own_course = Course.objects.create(code="REVIEW-OWN", name="Owned course")
        cls.other_course = Course.objects.create(code="REVIEW-OTHER", name="Other course")
        ClassSession.objects.create(
            course=cls.own_course, lecturer=cls.lecturer, starts_at=timezone.now(),
        )
        ClassSession.objects.create(
            course=cls.other_course, lecturer=cls.other_lecturer, starts_at=timezone.now(),
        )
        cls.project = Project.objects.create(
            title="Owned project", owner=cls.lecturer, supervisor=cls.lecturer,
            status="active", is_active=True,
        )
        cls.foreign_project = Project.objects.create(
            title="Private other project", owner=cls.other_lecturer,
            supervisor=cls.other_lecturer, status="active", is_active=True,
        )
        cls.foreign_group = ProjectGroup.objects.create(
            project=cls.foreign_project, name="Foreign group",
        )

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        # settings_test pins LocMemCache, which is process-wide and so not reset
        # between test classes. These tests register accounts anonymously, and
        # the "register" throttle is only 5/minute; clearing on the way out stops
        # those counters leaking into the next module and surfacing there as
        # spurious 429s.
        cache.clear()

    def test_public_registration_never_creates_a_privileged_account(self):
        """Public registration exists again, but it must never mint privilege.

        This previously asserted the routes were absent entirely, which
        contradicted the API specification ("Creates a new account where
        self-registration is allowed"). Self-registration is now restored, so
        the meaningful boundary is narrower and stronger: an anonymous caller
        can create an account, but never an administrator, and never a lecturer
        with privileges. Lecturer applicants land PENDING until an
        administrator decides.

        Exercised against all three aliases so the namespaces cannot drift.
        """
        for index, path in enumerate((
            "/api/v1/accounts/register/", "/api/v1/auth/register/",
            "/api/v1/auth/self-register/",
        )):
            with self.subTest(path=path):
                email = f"review-public-{index}@example.test"
                response = self.client.post(path, {
                    "account_type": "lecturer",
                    "email": email, "username": f"review-public-{index}",
                    "first_name": "Public", "last_name": "Registrant",
                    "password": "UnrelatedSecret!5938",
                    "staffid": f"STF-REVIEW-{index}",
                    # The whole point: a forged privileged role in the payload.
                    "role": "ADMINISTRATOR",
                    "lecturer_approval_status": "APPROVED",
                }, format="json")
                self.assertIn(response.status_code, (201, 400))

                account = User.objects.filter(email=email).first()
                if account is None:
                    continue  # refused outright, which is also safe
                self.assertNotEqual(account.role, User.Role.ADMINISTRATOR)
                self.assertFalse(account.is_staff)
                self.assertFalse(account.is_superuser)
                if account.role == User.Role.LECTURER:
                    self.assertEqual(
                        account.lecturer_approval_status,
                        User.LecturerApproval.PENDING,
                    )

    def test_login_rejects_cross_origin_request_without_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post("/api/v1/auth/login/", {
            "email": self.student.email, "password": "ReviewPassword!482",
        }, HTTP_ORIGIN="https://attacker.invalid")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", client.session)

    def test_login_accepts_same_origin_request_with_csrf_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/v1/accounts/csrf/")
        response = client.post("/api/v1/auth/login/", {
            "email": self.student.email, "password": "ReviewPassword!482",
        }, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.session["_auth_user_id"], str(self.student.pk))

    def test_django_staff_flag_does_not_grant_platform_admin_access(self):
        self.student.is_staff = True
        self.student.save(update_fields=["is_staff"])
        self.client.force_authenticate(self.student)
        response = self.client.get("/api/v1/accounts/")
        self.assertEqual(response.status_code, 403)

    def test_lecturer_cannot_read_foreign_unreleased_assessment(self):
        assessment = Assessment.objects.create(
            student=self.student, course=self.other_course,
            created_by=self.other_lecturer, released=False,
            private_notes="Private review fixture",
        )
        self.client.force_authenticate(self.lecturer)
        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(assessment.pk), {
            str(row["id"]) for row in response.data["data"]
        })

    def test_project_manager_cannot_assign_foreign_project_group(self):
        self.client.force_authenticate(self.lecturer)
        response = self.client.post(reverse("projects:member-add", args=[self.project.pk]), {
            "student": str(self.student.pk), "group": str(self.foreign_group.pk),
        }, format="json")
        self.assertIn(response.status_code, (400, 404))
        self.assertFalse(ProjectGroupMembership.objects.filter(project=self.project).exists())

    def test_private_project_write_has_same_response_as_missing_project(self):
        self.client.force_authenticate(self.lecturer)
        foreign = self.client.patch(
            reverse("projects:detail", args=[self.foreign_project.pk]),
            {"status": "completed"}, format="json",
        )
        missing = self.client.patch(
            reverse("projects:detail", args=["ffffffff-ffff-ffff-ffff-ffffffffffff"]),
            {"status": "completed"}, format="json",
        )
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.data, missing.data)
