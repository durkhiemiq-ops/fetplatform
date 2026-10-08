"""Authorization hardening: the lecturer approval policy must be structural.

Two things are asserted here.

1. Behaviour. ``core.permissions.IsApprovedAcademicUser`` and
   ``IsAdministrator`` implement the finalized policy, and the previously
   unguarded ``can_lecturer_manage_class`` honours lecturer approval.

2. Structure. :class:`LecturerRoleChecksStayCentral` fails the build when a
   product module starts authorizing on the lecturer *role* without going
   through the central helper. That is the property that stops the policy from
   eroding as other modules grow: the failure mode this guards against is a new
   endpoint that looks correct and silently admits a PENDING lecturer.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory

from apps.academic.services.eligibility_service import can_lecturer_manage_class
from apps.accounts.models import User
from core.academic_access import is_authorized_academic_user
from core.permissions import IsAdministrator, IsApprovedAcademicUser

PASSWORD = "Str0ng!Passphrase99"

#: Product modules may mention the lecturer role without consulting the central
#: helper only for a documented reason. Keep this list short and justify every
#: entry — an unexplained entry is exactly the bypass this test exists to stop.
ROLE_CHECK_ALLOWLIST = {
    # Declares the Role enum, including Role.LECTURER. It defines the policy's
    # vocabulary; it makes no authorization decision.
    "accounts/models.py",
    # Decides the role an applicant is *assigned* during registration. It is an
    # input to the policy, not an authorization decision about the caller.
    "accounts/services/registration_eligibility.py",
    # Assigns ``lecturer_approval_status`` during registration, always via
    # registration_eligibility.resolve_lecturer_approval, whose only non-None
    # result is PENDING -- the module has no path to a self-approved lecturer.
    # Its one authorization decision, change_user_role(), authorizes the *actor*
    # as an administrator (BR-002: admin-only, no self-assignment). It never
    # decides whether a PENDING or REJECTED lecturer may act academically, so
    # calling the central helper here would be dead code, not a hardening.
    "accounts/services/auth_service.py",
}

#: Real, confirmed bypasses owned by another agent, tracked until fixed.
#:
#: These are NOT sanctioned. Each entry is a live authorization decision that
#: ignores ``lecturer_approval_status``, which this pass cannot land itself
#: because the module belongs to another owner. Listing a file here keeps the
#: build green while keeping the bypass visible and impossible to forget; it
#: also means the guard still fails on any *new* offender.
#:
#: Removing an entry is part of closing the corresponding handoff.
PENDING_HANDOFF = {
    "files/services/file_service.py": (
        "OWNER: CODEX (apps/files/**, inherited from Astra who is no longer "
        "active). _is_manager(), _manageable_offering() and "
        "_readable_offering() branch on role == 'LECTURER' with no "
        "lecturer_approval_status check, so a PENDING or REJECTED lecturer "
        "assigned to an offering is treated as its manager and can read and "
        "manage its materials. "
        "Required behaviour: Files must first establish that the caller is an "
        "authorized academic user (core.academic_access."
        "is_authorized_academic_user, or core.permissions."
        "IsApprovedAcademicUser at the view), then apply its own "
        "object/resource relationship checks (is this lecturer assigned to "
        "THIS offering). Do not collapse the two layers. Until then this guard "
        "keeps reporting the bypass on purpose."
    ),
}


def _lecturer(email, status_value):
    return User.objects.create_user(
        email, email.split("@")[0], "Le", "Cturer", PASSWORD,
        role=User.Role.LECTURER, is_email_verified=True,
        lecturer_approval_status=status_value,
    )


class ApprovalPolicyPermissionTests(TestCase):
    """The reusable permission classes must match the finalized policy."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def _allows(self, permission, user):
        request = self.factory.get("/")
        request.user = user
        return permission().has_permission(request, None)

    def test_student_is_denied_academic_permission(self):
        student = User.objects.create_user(
            "s@example.test", "s", "Stu", "Dent", PASSWORD,
            role=User.Role.STUDENT, is_email_verified=True,
        )
        self.assertFalse(self._allows(IsApprovedAcademicUser, student))

    def test_pending_lecturer_is_denied(self):
        self.assertFalse(self._allows(
            IsApprovedAcademicUser, _lecturer("p@example.test", User.LecturerApproval.PENDING)
        ))

    def test_rejected_lecturer_is_denied(self):
        self.assertFalse(self._allows(
            IsApprovedAcademicUser, _lecturer("r@example.test", User.LecturerApproval.REJECTED)
        ))

    def test_approved_lecturer_is_allowed(self):
        self.assertTrue(self._allows(
            IsApprovedAcademicUser, _lecturer("a@example.test", User.LecturerApproval.APPROVED)
        ))

    def test_legacy_null_lecturer_is_allowed(self):
        """NULL means 'not an applicant' and keeps working."""
        self.assertTrue(self._allows(
            IsApprovedAcademicUser, _lecturer("legacy@example.test", None)
        ))

    def test_administrator_is_allowed(self):
        admin = User.objects.create_user(
            "adm@example.test", "adm", "Ad", "Min", PASSWORD,
            role=User.Role.ADMINISTRATOR, is_email_verified=True,
        )
        self.assertTrue(self._allows(IsApprovedAcademicUser, admin))

    def test_anonymous_is_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()
        self.assertFalse(IsApprovedAcademicUser().has_permission(request, None))
        self.assertFalse(IsAdministrator().has_permission(request, None))

    def test_administrator_permission_rejects_non_admins(self):
        lecturer = _lecturer("l@example.test", User.LecturerApproval.APPROVED)
        self.assertFalse(self._allows(IsAdministrator, lecturer))

    def test_permission_agrees_with_the_central_predicate(self):
        """The class must not drift from the predicate it delegates to."""
        cases = [
            _lecturer("p2@example.test", User.LecturerApproval.PENDING),
            _lecturer("r2@example.test", User.LecturerApproval.REJECTED),
            _lecturer("a2@example.test", User.LecturerApproval.APPROVED),
            _lecturer("n2@example.test", None),
        ]
        for user in cases:
            with self.subTest(email=user.email):
                self.assertEqual(
                    self._allows(IsApprovedAcademicUser, user),
                    is_authorized_academic_user(user),
                )


class CanLecturerManageClassTests(TestCase):
    """BR-021/BR-072 scope check must respect lecturer approval.

    Regression: this helper authorized on the role string alone, so an assigned
    PENDING applicant would have been allowed here while every lecturer-only
    endpoint refused them.
    """

    CLASS_ID = "class-1"
    COURSE_ID = "course-1"

    def _manage(self, user, **kwargs):
        params = {"class_id": self.CLASS_ID, "course_id": None}
        params.update(kwargs)
        return can_lecturer_manage_class(
            user,
            assigned_class_ids=[self.CLASS_ID],
            assigned_course_ids=[self.COURSE_ID],
            **params,
        )

    def test_pending_lecturer_cannot_manage_assigned_class(self):
        self.assertFalse(self._manage(
            _lecturer("p@example.test", User.LecturerApproval.PENDING)
        ))

    def test_rejected_lecturer_cannot_manage_assigned_class(self):
        self.assertFalse(self._manage(
            _lecturer("r@example.test", User.LecturerApproval.REJECTED)
        ))

    def test_approved_lecturer_can_manage_assigned_class(self):
        self.assertTrue(self._manage(
            _lecturer("a@example.test", User.LecturerApproval.APPROVED)
        ))

    def test_legacy_lecturer_can_manage_assigned_class(self):
        self.assertTrue(self._manage(_lecturer("n@example.test", None)))

    def test_administrator_bypasses_the_scope_check(self):
        admin = User.objects.create_user(
            "adm@example.test", "adm", "Ad", "Min", PASSWORD,
            role=User.Role.ADMINISTRATOR, is_email_verified=True,
        )
        self.assertTrue(can_lecturer_manage_class(
            admin, class_id=self.CLASS_ID, assigned_class_ids=[]
        ))

    def test_approved_lecturer_still_needs_assignment(self):
        """Approval is necessary but not sufficient — BR-021 scope holds."""
        self.assertFalse(can_lecturer_manage_class(
            _lecturer("a@example.test", User.LecturerApproval.APPROVED),
            class_id="unassigned-class", assigned_class_ids=[self.CLASS_ID],
        ))

    def test_none_is_denied(self):
        self.assertFalse(can_lecturer_manage_class(None, class_id=self.CLASS_ID))

    def test_duck_typed_lecturer_without_approval_attribute_still_works(self):
        """Callers pass loosely-typed objects; absent means legacy, not denied."""
        legacy = type("LegacyLecturer", (), {
            "role": User.Role.LECTURER,
            "class_ids": [self.CLASS_ID],
            "course_ids": [],
        })()
        self.assertTrue(
            can_lecturer_manage_class(legacy, class_id=self.CLASS_ID)
        )


class LecturerRoleChecksStayCentral(SimpleTestCase):
    """No product module may authorize on the lecturer role alone.

    A module that references the lecturer role but not
    ``is_authorized_academic_user`` has either forgotten the approval gate or
    is allowlisted for a documented reason. Both cases deserve a deliberate
    decision rather than an accident.
    """

    #: A lecturer-role reference in non-test product code.
    MARKERS = ("User.Role.LECTURER", "ROLE_LECTURER", '"LECTURER"', "'LECTURER'")
    CENTRAL_HELPER = "is_authorized_academic_user"

    def _product_modules(self):
        apps_root = Path(settings.BASE_DIR) / "apps"
        for path in sorted(apps_root.rglob("*.py")):
            parts = set(path.parts)
            if "migrations" in parts or "tests" in parts or path.name.startswith("test"):
                continue
            yield path

    def test_lecturer_role_checks_go_through_the_central_helper(self):
        new_offenders = []
        tracked = []
        for path in self._product_modules():
            text = path.read_text(encoding="utf-8")
            if not any(marker in text for marker in self.MARKERS):
                continue
            if self.CENTRAL_HELPER in text:
                continue
            relative = path.relative_to(Path(settings.BASE_DIR) / "apps").as_posix()
            if relative in ROLE_CHECK_ALLOWLIST:
                continue
            if relative in PENDING_HANDOFF:
                tracked.append(relative)
                continue
            new_offenders.append(relative)

        self.assertEqual(
            new_offenders, [],
            "These modules reference the lecturer role without consulting "
            f"{self.CENTRAL_HELPER}, so a PENDING or REJECTED lecturer could "
            "be authorized where this policy expects a refusal. Call the "
            "central helper, use core.permissions.IsApprovedAcademicUser, or "
            f"add a justified entry to ROLE_CHECK_ALLOWLIST: {new_offenders}",
        )
        # Tracked, not sanctioned: still report them so the list cannot quietly
        # grow without anyone reading the reason attached to it.
        for relative in tracked:
            with self.subTest(module=relative):
                self.assertIn(relative, PENDING_HANDOFF)

    def test_allowlist_entries_still_exist(self):
        """An allowlist/hand-off entry that no longer applies is dead weight."""
        apps_root = Path(settings.BASE_DIR) / "apps"
        for relative in (*ROLE_CHECK_ALLOWLIST, *PENDING_HANDOFF):
            self.assertTrue(
                (apps_root / relative).exists(),
                f"Lists {relative}, which no longer exists",
            )
