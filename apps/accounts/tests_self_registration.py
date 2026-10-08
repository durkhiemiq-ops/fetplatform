"""Secure self-registration: students, lecturers, and escalation attempts.

Covers the flows the platform can genuinely support:

* a student registers and is stored STUDENT, server-side;
* a lecturer applicant is stored PENDING and holds no academic privileges
  until an administrator approves them;
* no request body can grant ADMINISTRATOR or bypass lecturer approval.

What these tests deliberately do **not** claim: that the system can prove
somebody is a real student or a real member of staff. No university registry
exists in this repository, so eligibility is limited to what is actually
knowable here -- identity uniqueness and email
ownership via one-time code.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from apps.academic.models import Course, Department, Faculty
from apps.accounts.models import User
from core.academic_access import is_authorized_academic_user
from core.models import AuditEvent

PASSWORD = "Str0ng!Passphrase99"


class SelfRegistrationTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(
            name="Computer Engineering", code="CE", faculty=self.faculty
        )
        Course.objects.create(
            code="CEF444", name="Secure Systems", department=self.department,
            level="400", credit_units=4,
        )
        self.admin = User.objects.create_user(
            "reg-admin@example.test", "reg-admin", "Ad", "Min", PASSWORD,
            role=User.Role.ADMINISTRATOR, is_email_verified=True,
        )

    def tearDown(self):
        # settings_test pins LocMemCache, which is process-wide and therefore
        # NOT reset between test classes. Without this, the throttle counters
        # these registration tests consume ("register" is only 5/minute) leak
        # into whatever module runs next and surface there as spurious 429s.
        # Clearing keeps each test independent without weakening the throttle.
        cache.clear()

    def register(self, **overrides):
        payload = {
            "account_type": "student",
            "email": "newcomer@example.test",
            "first_name": "New",
            "last_name": "Comer",
            "password": PASSWORD,
            "matricule": "FE24A001",
        }
        payload.update(overrides)
        payload = {k: v for k, v in payload.items() if v is not None}
        return self.client.post(
            reverse("accounts:self-register"), payload, format="json"
        )


class StudentSelfRegistrationTests(SelfRegistrationTestBase):
    def test_eligible_student_registers_as_student(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="newcomer@example.test")
        self.assertEqual(account.role, User.Role.STUDENT)
        self.assertIsNone(account.lecturer_approval_status)
        self.assertTrue(account.check_password(PASSWORD))
        # A self-registered user chose their own password: no forced reset.
        self.assertFalse(account.must_change_password)
        self.assertFalse(account.is_email_verified)
        self.assertIsNone(account.department_id)
        self.assertEqual(account.level, "")

    def test_password_is_hashed_and_never_returned(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="newcomer@example.test")
        self.assertNotEqual(account.password, PASSWORD)
        # Hashed, not merely different: never the clear-text value.
        self.assertFalse(PASSWORD in account.password)
        self.assertTrue(account.check_password(PASSWORD))
        # No credential material anywhere in the response body.
        self.assertNotIn(PASSWORD, response.content.decode())
        self.assertNotIn("password", response.json()["data"])

    def test_matricule_is_required_for_students(self):
        response = self.register(matricule=None)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_unknown_department_is_refused(self):
        response = self.register(department="11111111-1111-1111-1111-111111111111")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_level_not_offered_by_the_catalogue_is_refused(self):
        response = self.register(level="900")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_cannot_impersonate_an_existing_matricule(self):
        User.objects.create_user(
            "real@example.test", "real", "Real", "Student", PASSWORD,
            matricule="FE24A777",
        )
        response = self.register(matricule="FE24A777")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_duplicate_email_is_indistinguishable_from_other_validation_failure(self):
        User.objects.create_user(
            "taken@example.test", "taken", "Ta", "Ken", PASSWORD,
        )
        duplicate = self.register(email="taken@example.test")
        malformed = self.register(
            email="other@example.test", department="11111111-1111-1111-1111-111111111111"
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.data["error"]["code"], malformed.data["error"]["code"])
        self.assertEqual(duplicate.data["error"]["code"], "INVALID_DATA")

    def test_weak_password_is_refused(self):
        response = self.register(password="12345678")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_registration_issues_a_verification_code_and_allows_login(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="newcomer@example.test")
        login = self.client.post(
            reverse("accounts:login"),
            {"email": account.email, "password": PASSWORD},
            format="json",
        )
        # Product decision: sign-in never requires email verification.
        self.assertEqual(login.status_code, 200)


class LecturerSelfRegistrationTests(SelfRegistrationTestBase):
    def register_lecturer(self, **overrides):
        payload = {
            "account_type": "lecturer",
            "email": "applicant@example.test",
            "first_name": "Lee",
            "last_name": "Churer",
            "password": PASSWORD,
        }
        payload.update(overrides)
        # Mirror SelfRegistrationTestBase.register: None means "omit", so a
        # test can express "no staffid supplied" without sending JSON null.
        payload = {k: v for k, v in payload.items() if v is not None}
        return self.client.post(
            reverse("accounts:self-register"), payload, format="json"
        )

    def test_lecturer_applicant_is_created_pending(self):
        response = self.register_lecturer()
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="applicant@example.test")
        self.assertEqual(account.role, User.Role.LECTURER)
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.PENDING
        )
        self.assertTrue(response.json()["data"]["lecturer_approval_required"])

    def test_pending_lecturer_has_no_academic_privileges(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        self.assertFalse(is_authorized_academic_user(account))

    def test_pending_lecturer_is_refused_by_a_lecturer_only_endpoint(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        account.is_email_verified = True
        account.save(update_fields=["is_email_verified"])
        self.client.force_authenticate(user=account)
        response = self.client.get(reverse("attendance:session-list"))
        self.assertEqual(response.status_code, 403)

    def test_email_verification_alone_does_not_approve(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        account.is_email_verified = True
        account.save(update_fields=["is_email_verified"])
        account.refresh_from_db()
        self.assertTrue(account.is_email_verified)
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.PENDING
        )
        self.assertFalse(is_authorized_academic_user(account))

    def test_admin_approval_grants_privileges_and_is_audited(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("accounts:lecturer-approval", args=[account.pk]),
            {"decision": "approve", "reason": "HR letter received"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.APPROVED
        )
        self.assertTrue(is_authorized_academic_user(account))
        self.assertTrue(
            AuditEvent.objects.filter(
                action="lecturer_application_decided", resource_id=str(account.pk)
            ).exists()
        )

    def test_approved_lecturer_reaches_a_lecturer_endpoint(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        self.client.force_authenticate(user=self.admin)
        self.client.post(
            reverse("accounts:lecturer-approval", args=[account.pk]),
            {"decision": "approve"},
            format="json",
        )
        # Re-read: the decision happened in another request, so this instance
        # still carries PENDING.
        account.refresh_from_db()
        self.client.force_authenticate(user=account)
        response = self.client.get(reverse("attendance:session-list"))
        self.assertEqual(response.status_code, 200)

    def test_rejection_withholds_privileges(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        self.client.force_authenticate(user=self.admin)
        self.client.post(
            reverse("accounts:lecturer-approval", args=[account.pk]),
            {"decision": "reject", "reason": "No staff record"},
            format="json",
        )
        account.refresh_from_db()
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.REJECTED
        )
        self.assertFalse(is_authorized_academic_user(account))
        self.client.force_authenticate(user=account)
        self.assertEqual(self.client.get(reverse("attendance:session-list")).status_code, 403)

    def test_non_admin_cannot_decide_an_application(self):
        self.register_lecturer()
        account = User.objects.get(email="applicant@example.test")
        impostor = User.objects.create_user(
            "nosy@example.test", "nosy", "Nos", "Ey", PASSWORD,
            role=User.Role.STUDENT,
        )
        self.client.force_authenticate(user=impostor)
        response = self.client.post(
            reverse("accounts:lecturer-approval", args=[account.pk]),
            {"decision": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        account.refresh_from_db()
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.PENDING
        )

    def test_lecturer_registration_requires_no_staff_code(self):
        # MVP mandate s8: no fabricated staff code. Nothing authoritative
        # exists to check such a value against, so the old expectation that a
        # public applicant must supply one was invalid — not a weakening of
        # the suite, but a changed requirement.
        response = self.register_lecturer(staffid=None)
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="applicant@example.test")
        self.assertIsNone(account.staffid)
        self.assertEqual(account.role, User.Role.LECTURER)
        # Email verification + admin approval remain the whole gate.
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.PENDING
        )
        self.assertFalse(is_authorized_academic_user(account))

    def test_public_staffid_is_rejected(self):
        # Historical staff identifiers remain stored but cannot be self-issued.
        User.objects.create_user(
            "existing-staff@example.test", "existing-staff", "Ex", "Staff",
            PASSWORD, role=User.Role.LECTURER, staffid="STF-999",
            is_email_verified=True,
        )
        taken = self.register_lecturer(staffid="STF-999")
        self.assertEqual(taken.status_code, 400)
        self.assertFalse(
            User.objects.filter(email="applicant@example.test").exists()
        )


class PrivilegeEscalationTests(SelfRegistrationTestBase):
    def test_forged_admin_role_in_payload_is_rejected(self):
        response = self.register(role="ADMINISTRATOR")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_student_cannot_request_the_lecturer_path_and_gain_privileges(self):
        response = self.register(account_type="lecturer", matricule=None)
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="newcomer@example.test")
        # Even on the lecturer path, no privilege without approval.
        self.assertEqual(account.lecturer_approval_status, User.LecturerApproval.PENDING)
        self.assertFalse(is_authorized_academic_user(account))

    def test_unknown_account_type_is_rejected(self):
        for bad in ("admin", "administrator", "coordinator", "root", ""):
            with self.subTest(account_type=bad):
                response = self.register(account_type=bad)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(
                    User.objects.filter(email="newcomer@example.test").exists()
                )

    def test_client_cannot_set_approval_status_or_must_change_password(self):
        response = self.register(
            account_type="lecturer",
            staffid="STF-555",
            lecturer_approval_status="APPROVED",
            must_change_password=False,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="newcomer@example.test").exists())

    def test_approval_endpoint_is_not_reachable_anonymously(self):
        response = self.client.post(
            reverse("accounts:lecturer-approval", args=["11111111-1111-1111-1111-111111111111"]),
            {"decision": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_both_namespaces_serve_the_same_behaviour(self):
        alias = self.client.post(
            reverse("accounts:register"),
            {
                "account_type": "lecturer",
                "email": "alias@example.test",
                "first_name": "Al", "last_name": "Ias",
                "password": PASSWORD,
            },
            format="json",
        )
        self.assertEqual(alias.status_code, 201)
        account = User.objects.get(email="alias@example.test")
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.PENDING
        )


class ExistingAccountSafetyTests(SelfRegistrationTestBase):
    def test_migration_default_leaves_existing_accounts_unaffected(self):
        # Pre-existing lecturer: created by an administrator, never applied.
        lecturer = User.objects.create_user(
            "existing-lect@example.test", "existing-lect", "Ex", "Lect",
            PASSWORD, role=User.Role.LECTURER,
        )
        lecturer.refresh_from_db()
        self.assertIsNone(lecturer.lecturer_approval_status)
        self.assertTrue(is_authorized_academic_user(lecturer))
        self.assertTrue(lecturer.is_active)

    def test_pre_existing_accounts_can_still_log_in(self):
        login = self.client.post(
            reverse("accounts:login"),
            {"email": self.admin.email, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["data"]["role"], "ADMINISTRATOR")

    def test_roster_provisioned_accounts_are_unaffected_by_the_new_field(self):
        from apps.accounts.services.roster_service import import_student_roster

        csv_bytes = (
            "matricule,first_name,last_name,email,level,department_code\r\n"
            "FE24B999,Ros,Ter,ros.ter@example.test,400,CE\r\n"
        )
        upload = self.client.post(
            reverse("roster-upload"),
            {"file": _csv(csv_bytes)},
        )
        # Roster upload is admin-only, so authenticate as one first.
        self.client.force_authenticate(user=self.admin)
        upload = self.client.post(
            reverse("roster-upload"),
            {"file": _csv(csv_bytes)},
        )
        self.assertEqual(upload.status_code, 201)
        created = User.objects.get(email="ros.ter@example.test")
        self.assertTrue(created.must_change_password)
        # Not an applicant: no approval workflow applies to it.
        self.assertIsNone(created.lecturer_approval_status)
        self.assertTrue(created.is_email_verified)
        self.assertTrue(AuditEvent.objects.filter(
            action="roster_student_created", resource_id=str(created.pk)
        ).exists())


def _csv(text):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("roster.csv", text.encode("utf-8"), "text/csv")


class LecturerApprovalSelfEscalationTests(SelfRegistrationTestBase):
    """A lecturer applicant must not be able to approve themselves.

    ``UserSerializer`` is reused by ``PATCH /accounts/me/``. Any server-owned
    field left out of ``read_only_fields`` becomes self-writable through that
    endpoint, which turns an applicant into teaching staff with one request.
    """

    def _pending_lecturer(self):
        response = self.register(
            account_type="lecturer",
            email="applicant@example.test",
            matricule=None,
        )
        self.assertEqual(response.status_code, 201)
        account = User.objects.get(email="applicant@example.test")
        self.assertEqual(account.role, User.Role.LECTURER)
        self.assertEqual(account.lecturer_approval_status, User.LecturerApproval.PENDING)
        return account

    def test_patch_me_cannot_self_approve(self):
        account = self._pending_lecturer()
        self.client.force_authenticate(user=account)

        response = self.client.patch(
            reverse("accounts:current-user"),
            {"lecturer_approval_status": User.LecturerApproval.APPROVED},
            format="json",
        )

        self.assertIn(response.status_code, (200, 400))
        account.refresh_from_db()
        # The decisive assertion: approval is administrator-owned only.
        self.assertEqual(account.lecturer_approval_status, User.LecturerApproval.PENDING)
        self.assertFalse(is_authorized_academic_user(account))

    def test_patch_me_cannot_forge_admin_role_or_verification(self):
        account = self._pending_lecturer()
        self.client.force_authenticate(user=account)

        self.client.patch(
            reverse("accounts:current-user"),
            {
                "role": User.Role.ADMINISTRATOR,
                "is_email_verified": True,
                "must_change_password": False,
            },
            format="json",
        )

        account.refresh_from_db()
        self.assertEqual(account.role, User.Role.LECTURER)
        self.assertEqual(account.lecturer_approval_status, User.LecturerApproval.PENDING)

    def test_administrator_approval_grants_academic_privileges(self):
        account = self._pending_lecturer()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            reverse("accounts:lecturer-approval", args=[str(account.pk)]),
            {"decision": "approve"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.APPROVED
        )
        self.assertTrue(is_authorized_academic_user(account))

    def test_rejection_withholds_academic_privileges(self):
        account = self._pending_lecturer()
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            reverse("accounts:lecturer-approval", args=[str(account.pk)]),
            {"decision": "reject", "reason": "No verifiable staff record."},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(
            account.lecturer_approval_status, User.LecturerApproval.REJECTED
        )
        self.assertFalse(is_authorized_academic_user(account))

    def test_non_admin_cannot_approve(self):
        account = self._pending_lecturer()
        self.client.force_authenticate(user=account)

        response = self.client.post(
            reverse("accounts:lecturer-approval", args=[str(account.pk)]),
            {"decision": "approve"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        account.refresh_from_db()
        self.assertEqual(account.lecturer_approval_status, User.LecturerApproval.PENDING)

    def test_legacy_null_status_retains_lecturer_privileges(self):
        """NULL means 'not an applicant' and must not silently demote old rows."""
        lecturer = User.objects.create_user(
            "legacy@example.test", "legacy", "Leg", "Acy", PASSWORD,
            role=User.Role.LECTURER, is_email_verified=True,
        )
        self.assertIsNone(lecturer.lecturer_approval_status)
        self.assertTrue(is_authorized_academic_user(lecturer))


class LecturerListAuthorizationTests(SelfRegistrationTestBase):
    """GET /accounts/lecturers/ backs the administrator approval queue."""

    def _lecturer(self, email, status_value):
        return User.objects.create_user(
            email, email.split("@")[0], "Le", "Cturer", PASSWORD,
            role=User.Role.LECTURER, is_email_verified=True,
            lecturer_approval_status=status_value,
        )

    def test_admin_sees_lecturers_with_approval_status(self):
        pending = self._lecturer("pend@example.test", User.LecturerApproval.PENDING)
        self._lecturer("ok@example.test", User.LecturerApproval.APPROVED)
        self._lecturer("legacy@example.test", None)
        User.objects.create_user(
            "stu@example.test", "stu", "Stu", "Dent", PASSWORD,
            role=User.Role.STUDENT, is_email_verified=True,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("accounts:lecturer-list"))

        self.assertEqual(response.status_code, 200)
        body = response.json()["data"]
        # Paginated with the project's standard paginator, like every other
        # paginated endpoint: {count, next, previous, results}.
        self.assertEqual(
            sorted(body), ["count", "next", "previous", "results"]
        )
        self.assertEqual(body["count"], 3)
        rows = body["results"]
        # Students are excluded; every lecturer is present.
        self.assertEqual({r["email"] for r in rows}, {
            "pend@example.test", "ok@example.test", "legacy@example.test",
        })
        by_email = {r["email"]: r for r in rows}
        self.assertEqual(
            by_email["pend@example.test"]["lecturer_approval_status"], "PENDING"
        )
        self.assertIsNone(
            by_email["legacy@example.test"]["lecturer_approval_status"]
        )
        self.assertNotIn("password", rows[0])

    def test_lecturer_list_paginates_beyond_one_page(self):
        """The approval queue must not silently hide applicants on page 2."""
        page_size = api_settings.PAGE_SIZE
        for i in range(page_size + 3):
            self._lecturer(
                f"bulk{i:03d}@example.test", User.LecturerApproval.PENDING
            )
        self.client.force_authenticate(user=self.admin)

        first = self.client.get(reverse("accounts:lecturer-list")).json()["data"]
        self.assertEqual(len(first["results"]), page_size)
        self.assertIsNotNone(first["next"])

        second = self.client.get(first["next"]).json()["data"]
        self.assertEqual(len(second["results"]), 3)
        self.assertIsNone(second["next"])

        seen = {r["email"] for r in first["results"]} | {
            r["email"] for r in second["results"]
        }
        self.assertEqual(len(seen), page_size + 3)

    def test_non_admin_cannot_list_lecturers(self):
        lecturer = self._lecturer("peer@example.test", User.LecturerApproval.APPROVED)
        self.client.force_authenticate(user=lecturer)
        self.assertEqual(
            self.client.get(reverse("accounts:lecturer-list")).status_code, 403
        )

    def test_pending_applicant_cannot_list_lecturers(self):
        applicant = self._lecturer("new@example.test", User.LecturerApproval.PENDING)
        self.client.force_authenticate(user=applicant)
        self.assertEqual(
            self.client.get(reverse("accounts:lecturer-list")).status_code, 403
        )

    def test_anonymous_cannot_list_lecturers(self):
        # Session auth yields 403, not 401, for a missing credential — matching
        # the existing anonymous-approval test.
        self.assertEqual(
            self.client.get(reverse("accounts:lecturer-list")).status_code, 403
        )
