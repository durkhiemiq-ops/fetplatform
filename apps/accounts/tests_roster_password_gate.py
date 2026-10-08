from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.academic.models import Department, Faculty
from core.models import AuditEvent

from .models import User


class AccountSecurityFixture(TestCase):
    def setUp(self):
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(
            name="Computer Engineering", code="CE", faculty=self.faculty
        )
        self.admin = User.objects.create_user(
            email="admin@example.edu",
            username="admin",
            first_name="Admin",
            last_name="User",
            password="AdminPass!2026",
            role=User.Role.ADMINISTRATOR,
            is_email_verified=True,
        )

    @staticmethod
    def csv_file(body):
        return SimpleUploadedFile(
            "roster.csv", body.encode("utf-8"), content_type="text/csv"
        )

    @staticmethod
    def roster(*rows):
        header = "matricule,first_name,last_name,email,level,department_code\n"
        return header + "\n".join(rows) + "\n"


class RosterUploadTests(AccountSecurityFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_login(self.admin)

    def upload(self, body):
        return self.client.post(
            "/api/v1/admin/roster/upload/",
            {"file": self.csv_file(body)},
            format="multipart",
        )

    def test_admin_upload_creates_locked_verified_student(self):
        response = self.upload(
            self.roster("CE24001,Ada,Okafor,ada@example.edu,400,CE")
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["created_count"], 1)
        created = response.data["data"]["created"][0]
        student = User.objects.get(email="ada@example.edu")
        self.assertEqual(student.role, User.Role.STUDENT)
        self.assertEqual(student.department, self.department)
        self.assertEqual(student.level, "400")
        self.assertTrue(student.is_email_verified)
        self.assertTrue(student.must_change_password)
        self.assertTrue(student.check_password(created["temp_password"]))
        self.assertNotIn(created["temp_password"], student.password)
        self.assertEqual(response["Cache-Control"], "no-store, max-age=0")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="roster_student_created", resource_id=str(student.pk)
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="student_roster_uploaded").exists()
        )

    def test_reupload_updates_profile_without_rotating_password(self):
        first = self.upload(
            self.roster("CE24002,Ben,Ito,ben@example.edu,300,CE")
        )
        password = first.data["data"]["created"][0]["temp_password"]

        second = self.upload(
            self.roster("CE24002,Benjamin,Ito,ben@example.edu,400,CE")
        )

        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["data"]["created_count"], 0)
        self.assertEqual(second.data["data"]["updated_count"], 1)
        self.assertNotIn("temp_password", second.data["data"]["updated"][0])
        student = User.objects.get(email="ben@example.edu")
        self.assertEqual(student.first_name, "Benjamin")
        self.assertEqual(student.level, "400")
        self.assertTrue(student.check_password(password))

    def test_extra_role_column_is_rejected_instead_of_trusted(self):
        body = (
            "matricule,first_name,last_name,email,level,department_code,role\n"
            "CE24003,Eve,Ngo,eve@example.edu,400,CE,ADMINISTRATOR\n"
        )
        response = self.upload(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_ROSTER")
        self.assertFalse(User.objects.filter(email="eve@example.edu").exists())

    def test_unknown_department_is_a_row_error(self):
        response = self.upload(
            self.roster("XX24001,Unknown,Dept,unknown@example.edu,400,XX")
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["error_count"], 1)
        self.assertFalse(User.objects.filter(email="unknown@example.edu").exists())

    def test_cross_identity_collision_is_rejected(self):
        first = User.objects.create_user(
            email="first@example.edu",
            username="first",
            first_name="First",
            last_name="Student",
            password="FirstPass!2026",
            matricule="CE25001",
            role=User.Role.STUDENT,
        )
        second = User.objects.create_user(
            email="second@example.edu",
            username="second",
            first_name="Second",
            last_name="Student",
            password="SecondPass!2026",
            matricule="CE25002",
            role=User.Role.STUDENT,
        )
        response = self.upload(
            self.roster("CE25002,First,Student,first@example.edu,400,CE")
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["error_count"], 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.matricule, "CE25001")
        self.assertEqual(second.email, "second@example.edu")

    def test_is_staff_student_cannot_upload(self):
        staff_student = User.objects.create_user(
            email="staff-student@example.edu",
            username="staff-student",
            first_name="Staff",
            last_name="Student",
            password="StaffPass!2026",
            role=User.Role.STUDENT,
            is_staff=True,
            is_email_verified=True,
        )
        client = APIClient()
        client.force_login(staff_student)
        response = client.post(
            "/api/v1/admin/roster/upload/",
            {"file": self.csv_file(self.roster("CE24004,No,Access,no@example.edu,400,CE"))},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="no@example.edu").exists())


class ForcedPasswordChangeTests(AccountSecurityFixture):
    def setUp(self):
        super().setUp()
        self.student = User.objects.create_user(
            email="temporary@example.edu",
            username="temporary",
            first_name="Temporary",
            last_name="Student",
            password="TemporaryPass!2026",
            role=User.Role.STUDENT,
            is_email_verified=True,
            must_change_password=True,
        )
        self.client = APIClient()
        self.client.force_login(self.student)

    def test_temporary_password_login_returns_server_owned_gate(self):
        client = APIClient()
        response = client.post(
            "/api/v1/auth/login/",
            {
                "identifier": "temporary@example.edu",
                "password": "TemporaryPass!2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["data"]["must_change_password"])
        self.assertEqual(response.data["data"]["role"], User.Role.STUDENT)

    def test_gate_allowlist_covers_both_url_namespaces(self):
        """A gated account must not be trapped by the compatibility alias.

        Both namespaces are live. If the gate lists only one of them, the other
        returns 403 for identity and sign-out, leaving the user unable to read
        its own profile or log out.
        """
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/accounts/me/").status_code, 200)

        # Sign-out must work through both families.
        canonical = APIClient()
        canonical.force_login(self.student)
        self.assertEqual(
            canonical.post("/api/v1/accounts/logout/").status_code, 200
        )
        alias = APIClient()
        alias.force_login(self.student)
        self.assertEqual(alias.post("/api/v1/auth/logout/").status_code, 200)

    def test_locked_account_can_read_identity_but_not_application_data(self):
        identity = self.client.get("/api/v1/auth/me/")
        self.assertEqual(identity.status_code, 200)
        self.assertTrue(identity.data["data"]["must_change_password"])

        canonical_identity = self.client.get("/api/v1/accounts/me/")
        self.assertEqual(canonical_identity.status_code, 200)
        self.assertTrue(canonical_identity.data["data"]["must_change_password"])

        for path in (
            "/api/v1/projects/",
            "/api/v1/notifications/",
            "/api/v1/departments/",
            "/api/v1/accounts/lecturers/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json(),
                    {
                        "success": False,
                        "error": {
                            "code": "PASSWORD_CHANGE_REQUIRED",
                            "message": "Change the temporary password before continuing.",
                        },
                    },
                )

    def test_successful_change_clears_gate_and_keeps_session(self):
        response = self.client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": "TemporaryPass!2026",
                "new_password": "ReplacementPass!2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertFalse(self.student.must_change_password)
        self.assertTrue(self.student.check_password("ReplacementPass!2026"))
        self.assertEqual(self.client.get("/api/v1/projects/").status_code, 200)
        event = AuditEvent.objects.get(
            action="password_changed", resource_id=str(self.student.pk)
        )
        self.assertEqual(event.details, {"cleared_temporary_password": True})

    def test_failed_or_same_password_does_not_clear_gate(self):
        wrong = self.client.post(
            "/api/v1/auth/change-password/",
            {"current_password": "wrong", "new_password": "ReplacementPass!2026"},
            format="json",
        )
        self.assertEqual(wrong.status_code, 400)
        same = self.client.post(
            "/api/v1/auth/change-password/",
            {
                "current_password": "TemporaryPass!2026",
                "new_password": "TemporaryPass!2026",
            },
            format="json",
        )
        self.assertEqual(same.status_code, 400)
        self.student.refresh_from_db()
        self.assertTrue(self.student.must_change_password)

    def test_client_cannot_clear_security_flag(self):
        normal = User.objects.create_user(
            email="normal@example.edu",
            username="normal",
            first_name="Normal",
            last_name="Student",
            password="NormalPass!2026",
            role=User.Role.STUDENT,
            is_email_verified=True,
        )
        client = APIClient()
        client.force_login(normal)
        response = client.patch(
            "/api/v1/accounts/me/", {"must_change_password": True}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        normal.refresh_from_db()
        self.assertFalse(normal.must_change_password)

    def test_normal_account_is_unaffected(self):
        self.student.must_change_password = False
        self.student.save(update_fields=["must_change_password"])
        self.assertEqual(self.client.get("/api/v1/projects/").status_code, 200)
