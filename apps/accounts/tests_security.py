"""Security audit regression checks (numbered 1-8).

Each test maps to one numbered audit finding.  See the audit report:

  Check 1  CRITICAL  Rate limiting on login/register (BR-203)
  Check 2  CRITICAL  Duplicate-email indistinguishable from generic validation error
  Check 3  CRITICAL  DEBUG defaults to False (only True when explicitly set in .env)
  Check 4           SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE = True when DEBUG is False
  Check 5           Username lowercased on uniqueness check and on save
  Check 6           DRF raise_exception validation errors use the standard envelope
  Check 7           frontend/.env.example matches .env values
  Check 8           obsolete cacheCsrfToken/getCachedCsrfToken helpers absent
                    from the frontend source tree
  Check 9  CRITICAL  Registration runs AUTH_PASSWORD_VALIDATORS

Checks 3, 4, 7 and 8 are static/file checks run by scripts/security_audit_checks.py
(`python scripts/security_audit_checks.py`).  Checks 1, 2, 5, 6 and 9 are
behavioural and live here so they run under the normal Django test runner.

Run everything with:
    python scripts/security_audit_checks.py
"""

from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import User
from apps.accounts.views import LoginView, RegisterView


class FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """Low-cost hasher so throttle tests that brute a bad login run fast."""

    iterations = 1


class SecurityAuditChecks(TestCase):
    def setUp(self):
        # Isolation: DRF throttle counters live in the shared default cache, so
        # wipe them before each check so tests cannot consume each other's
        # login/register rate budgets.
        cache.clear()
        self.client = APIClient()
        self.request_factory = APIRequestFactory()
        self.valid_payload = {
            "email": "person@example.test",
            "username": "person",
            "first_name": "Per",
            "last_name": "Son",
            "password": "StrongPass!2026",
        }

    def _provision(self, payload):
        request = self.request_factory.post("/internal/provision/", payload, format="json")
        return RegisterView.as_view()(request)

    def test_check_1_throttle_classes_configured_on_login_and_register(self):
        """Check 1: ScopedRateThrottle wired so the configured rates apply."""
        from rest_framework.throttling import ScopedRateThrottle

        for view in (LoginView, RegisterView):
            throttles = [cls.__name__ for cls in view.throttle_classes]
            self.assertIn(ScopedRateThrottle.__name__, throttles)
            self.assertTrue(view.throttle_scope, "throttle_scope must be set")

    @override_settings(PASSWORD_HASHERS=["apps.accounts.tests_security.FastPBKDF2PasswordHasher"])
    def test_check_1_login_rate_limit_returns_429(self):
        """Check 1: the 11th login attempt (scope 'login' = 10/min) → 429 RATE_LIMITED.

        Fires against the *real* configured rate; DRF binds
        ScopedRateThrottle.THROTTLE_RATES at import time, so an
        override_settings(REST_FRAMEWORK=...) would not change the limit.
        """
        url = reverse("accounts:login")
        response = None
        for _ in range(11):
            response = self.client.post(
                url,
                {
                    "identifier": "ghost@example.test",
                    "password": "wrong-password",
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["error"]["code"], "RATE_LIMITED")

    def test_check_2_duplicate_email_is_indistinguishable_from_validation_error(self):
        """Check 2: duplicate email → same 400 status / envelope / code as a
        generic validation failure, so registered emails cannot be enumerated."""
        first = self._provision(self.valid_payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        duplicate_payload = dict(self.valid_payload, username="different-person")
        duplicate = self._provision(duplicate_payload)

        malformed_payload = dict(
            self.valid_payload, email="another@example.test", password="short"
        )
        malformed = self._provision(malformed_payload)

        self.assertEqual(duplicate.status_code, malformed.status_code)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(duplicate.data.keys()), {"success", "error"})
        self.assertEqual(set(malformed.data.keys()), {"success", "error"})
        self.assertEqual(duplicate.data["success"], malformed.data["success"])
        self.assertEqual(
            duplicate.data["error"]["code"], malformed.data["error"]["code"]
        )
        self.assertEqual(duplicate.data["error"]["code"], "INVALID_DATA")

    def test_check_5_username_is_lowercased_on_save(self):
        """Check 5: mixed-case username is stored lowercase, matching email."""
        payload = dict(self.valid_payload, username="Mixed.Case.Name")
        response = self._provision(payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email=self.valid_payload["email"])
        self.assertEqual(created.username, "mixed.case.name")

    def test_check_5_username_uniqueness_check_is_case_insensitive(self):
        """Check 5: a same-username-different-case registration is rejected."""
        self._provision(self.valid_payload)

        duplicate_case_payload = dict(
            self.valid_payload,
            email="other@example.test",
            username="PERSON",
        )
        response = self._provision(duplicate_case_payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_DATA")
        self.assertFalse(
            User.objects.filter(email="other@example.test").exists(),
            "case-variant username should be rejected before creation",
        )

    def test_check_6_drf_validation_errors_use_standard_envelope(self):
        """Check 6: raise_exception validation errors → {success, error} shape,
        not DRF's raw {'field': [...]} dict."""
        response = self.client.post(reverse("accounts:login"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data.keys()), {"success", "error"})
        self.assertIn("code", response.data["error"])
        self.assertIn("message", response.data["error"])
        self.assertEqual(response.data["error"]["code"], "INVALID_DATA")
        self.assertIsInstance(response.data["error"]["message"], str)


class RegistrationPasswordValidatorChecks(TestCase):
    """Check 9: registration runs the configured AUTH_PASSWORD_VALIDATORS.

    Regression guard.  Before this, ``RegisterSerializer`` enforced only
    ``min_length=8``: every validator in ``config/settings.py`` was configured
    but the sole call site for ``validate_password`` anywhere in the project was
    the change-password view.  ``12345678`` and ``qwertyui`` were accepted.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.request_factory = APIRequestFactory()
        self.payload = {
            "email": "person@example.test",
            "username": "person",
            "first_name": "Per",
            "last_name": "Son",
            "password": "StrongPass!2026",
        }

    def _register(self, password, **overrides):
        request = self.request_factory.post(
            "/internal/provision/",
            dict(self.payload, password=password, **overrides),
            format="json",
        )
        return RegisterView.as_view()(request)

    def test_check_9_numeric_password_is_rejected(self):
        """NumericPasswordValidator: an all-digit password must not register."""
        response = self._register("12345678")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_DATA")
        self.assertFalse(User.objects.filter(email=self.payload["email"]).exists())

    def test_check_9_common_password_is_rejected(self):
        """CommonPasswordValidator: a breached/common password must not register."""
        response = self._register("qwertyui")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("common", response.data["error"]["message"].lower())
        self.assertFalse(User.objects.filter(email=self.payload["email"]).exists())

    def test_check_9_short_password_is_rejected(self):
        """MinimumLengthValidator, on top of the existing min_length=8 field rule."""
        response = self._register("Ab1!")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email=self.payload["email"]).exists())

    def test_check_9_password_similar_to_identity_is_rejected(self):
        """UserAttributeSimilarityValidator only works if the submitted
        identity fields are handed to it — this is the case that proves the
        unsaved-User wiring in RegisterSerializer.validate() is real."""
        response = self._register(
            "person@example.test-2026",
            email="person@example.test",
            username="person",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email=self.payload["email"]).exists())

    def test_check_9_strong_password_is_accepted(self):
        """The fix must not over-block: a genuinely strong password registers."""
        response = self._register("Tr0ub4dor&3-Quartz")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email=self.payload["email"]).exists())

    def test_check_9_failure_keeps_envelope_and_reveals_no_account(self):
        """A weak-password rejection is indistinguishable in shape from the
        duplicate-email response, so password rules cannot be used to probe
        whether an address is registered (BR-203)."""
        self._register(self.payload["password"])

        weak = self._register("12345678", username="someone-else")
        duplicate = self._register(self.payload["password"], username="someone-else")
        self.assertEqual(weak.status_code, duplicate.status_code)
        self.assertEqual(set(weak.data.keys()), {"success", "error"})
        self.assertEqual(weak.data["error"]["code"], duplicate.data["error"]["code"])
        self.assertEqual(weak.data["error"]["code"], "INVALID_DATA")
