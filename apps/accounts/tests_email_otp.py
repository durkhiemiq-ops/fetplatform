"""Email verification (OTP) feature tests — the shipped proof checklist.

Evidence covered here, one test per claim:
- registration dispatches a code and the code never appears in any response;
- login is blocked with ACCOUNT_NOT_VERIFIED until the address is verified;
- the correct code verifies, flips is_email_verified, and is audited;
- the same code cannot verify twice (atomic consume);
- an expired (TTL-evicted) code fails with the same generic response;
- resend issues a fresh code and kills the previous one;
- hammering verify-email (11 requests) and resend (4 requests) throttles;
- the per-identity attempt cap destroys the code before it can be ground out;
- wrong-code / unknown-address responses are byte-identical (no oracle);
- the original register -> login -> /me/ flow still works end to end.
"""

import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import email_otp
from core.models import AuditEvent


GENERIC_FAILURE = "Verification failed. Request a new code and try again."
# Non-numeric on purpose: it can never equal a six-digit draw, so these
# tests have no 1-in-10^6 flake window.
WRONG_CODE = "definitely-not-a-code"


class EmailOTPFlowTests(TestCase):
    def setUp(self):
        # OTP keys and DRF throttle counters share the default cache.
        cache.clear()
        self.client = APIClient()
        self.payload = {
            "email": "otp-user@example.test",
            "username": "otp-user",
            "first_name": "Otp",
            "last_name": "User",
            "password": "StrongPass!2026",
        }

    def _register(self, payload=None):
        return self.client.post(
            reverse("accounts:register"), payload or self.payload, format="json"
        )

    def _verify(self, email, code):
        return self.client.post(
            reverse("accounts:verify-email"),
            {"email": email, "code": code},
            format="json",
        )

    def _resend(self, email=None):
        return self.client.post(
            reverse("accounts:resend-verification"),
            {"email": email or self.payload["email"]},
            format="json",
        )

    def _login(self):
        return self.client.post(
            reverse("accounts:login"),
            {
                "identifier": self.payload["email"],
                "password": self.payload["password"],
            },
            format="json",
        )

    def _latest_code(self):
        """Extract the six-digit code from the newest outbound email."""
        self.assertTrue(mail.outbox, "no verification email was sent")
        match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        self.assertIsNotNone(match, "verification email has no six-digit code")
        return match.group(1)

    def test_full_flow_register_code_blocks_login_verify_allows_login_me(self):
        """Registration -> OTP email -> blocked login -> verify -> login -> /me/."""
        response = self._register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.payload["email"]])
        code = self._latest_code()

        # The OTP is a secret: it must not appear as a value in the response.
        self.assertNotIn(code, [str(v) for v in response.data["data"].values()])

        blocked = self._login()
        self.assertEqual(blocked.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(blocked.data["error"]["code"], "ACCOUNT_NOT_VERIFIED")

        verified = self._verify(self.payload["email"], code)
        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        # Success response is a fixed string — carries no code either.
        self.assertNotIn(code, str(verified.data))

        user = User.objects.get(email=self.payload["email"])
        self.assertTrue(user.is_email_verified)
        self.assertEqual(
            AuditEvent.objects.filter(
                action="email_verified", resource_id=str(user.id)
            ).count(),
            1,
        )

        session = self._login()
        self.assertEqual(session.status_code, status.HTTP_200_OK)

        me = self.client.get(reverse("accounts:current-user"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["data"]["email"], self.payload["email"])

    def test_same_code_cannot_verify_twice(self):
        self._register()
        code = self._latest_code()

        first = self._verify(self.payload["email"], code)
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self._verify(self.payload["email"], code)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second.data["error"]["code"], "VERIFICATION_FAILED")
        self.assertEqual(second.data["error"]["message"], GENERIC_FAILURE)

    def test_expired_code_fails_with_generic_response(self):
        """TTL elapsed evicts the key; expiry and wrong code are indistinguishable."""
        self._register()
        code = self._latest_code()
        # Simulate EMAIL_OTP_TTL_SECONDS elapsing (cache eviction).
        cache.delete(email_otp._code_key("otp-user@example.test"))

        response = self._verify(self.payload["email"], code)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VERIFICATION_FAILED")
        self.assertEqual(response.data["error"]["message"], GENERIC_FAILURE)

        # Still locked out: expiry did not weaken the login gate.
        self.assertEqual(self._login().status_code, status.HTTP_403_FORBIDDEN)

    def test_resend_issues_fresh_code_and_kills_old_one(self):
        self._register()
        old_code = self._latest_code()

        resend = self._resend()
        self.assertEqual(resend.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)
        new_code = self._latest_code()
        # Re-issue at most twice more (3/min throttle) in the astronomically
        # unlikely event of an identical six-digit draw.
        for _ in range(2):
            if new_code != old_code:
                break
            self._resend()
            new_code = self._latest_code()
        self.assertNotEqual(old_code, new_code)

        stale = self._verify(self.payload["email"], old_code)
        self.assertEqual(stale.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(stale.data["error"]["message"], GENERIC_FAILURE)

        fresh = self._verify(self.payload["email"], new_code)
        self.assertEqual(fresh.status_code, status.HTTP_200_OK)

    def test_resend_response_identical_for_unknown_address(self):
        self._register()
        existing = self._resend()
        self.assertEqual(existing.status_code, status.HTTP_200_OK)
        sent_so_far = len(mail.outbox)

        ghost = self._resend("ghost@example.test")
        self.assertEqual(ghost.status_code, existing.status_code)
        self.assertEqual(ghost.data, existing.data)
        # No send is triggered for an address that has no pending account.
        self.assertEqual(len(mail.outbox), sent_so_far)

    def test_wrong_code_response_identical_for_unknown_address(self):
        self._register()

        real = self._verify(self.payload["email"], WRONG_CODE)
        ghost = self._verify("ghost@example.test", WRONG_CODE)

        self.assertEqual(real.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ghost.status_code, real.status_code)
        self.assertEqual(ghost.data, real.data)
        self.assertEqual(real.data["error"]["message"], GENERIC_FAILURE)

    def test_verify_endpoint_throttles_hammering(self):
        """10/minute on verify-email: the 11th guess is rejected before the view."""
        self._register()

        responses = [
            self._verify(self.payload["email"], WRONG_CODE) for _ in range(11)
        ]
        self.assertEqual(responses[0].status_code, status.HTTP_400_BAD_REQUEST)
        throttled = responses[-1]
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(throttled.data["error"]["code"], "RATE_LIMITED")

    def test_resend_endpoint_throttles_hammering(self):
        """3/minute on resend-verification from day one (cost/inbox vector)."""
        self._register()

        responses = [self._resend() for _ in range(4)]
        self.assertEqual(responses[2].status_code, status.HTTP_200_OK)
        throttled = responses[-1]
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(throttled.data["error"]["code"], "RATE_LIMITED")

    def test_attempt_cap_destroys_code_even_for_correct_guess(self):
        """EMAIL_OTP_MAX_ATTEMPTS=5: grinding dies at the identity, not the IP."""
        self._register()
        code = self._latest_code()

        for _ in range(5):
            response = self._verify(self.payload["email"], WRONG_CODE)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        late_but_correct = self._verify(self.payload["email"], code)
        self.assertEqual(late_but_correct.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(late_but_correct.data["error"]["message"], GENERIC_FAILURE)

        # The user's way out is a fresh code, which starts a clean counter.
        self._resend()
        fresh = self._verify(self.payload["email"], self._latest_code())
        self.assertEqual(fresh.status_code, status.HTTP_200_OK)

    def test_superusers_are_created_verified_ordinary_users_are_not(self):
        superuser = User.objects.create_superuser(
            "root@example.test", "root", "R", "Ot", "StrongPass!2026"
        )
        self.assertTrue(superuser.is_email_verified)

        ordinary = User.objects.create_user(
            "plain@example.test", "plain", "P", "Lain", "StrongPass!2026"
        )
        self.assertFalse(ordinary.is_email_verified)
