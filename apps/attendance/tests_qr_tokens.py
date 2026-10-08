"""QR token mechanics tests — the backend-independent contract.

Why validation does not consume
-------------------------------
``consume_token`` used to burn a code after the first scan so replay could be
detected.  That contract is incompatible with the MVP's shared-QR mandate: one
projected code (or one station's code) must keep working for every student who
scans it inside its 10-second TTL, so the class behind the first scanner is
never locked out.

Replay is therefore solved by the layers *around* the token:

* the token lives only ``QR_TOKEN_TTL_SECONDS`` (10s) and is re-issued
  continuously by whoever displays it,
* it is bound to one session (and, for a station, one scan point),
* every scan is credited to the authenticated scanner and no one else, and
* the database's UNIQUE(session, student) constraint makes a second credit for
  the same student impossible (``attendance_service.AlreadyMarkedError``).

So this module *validates*; ``attendance_service`` deduplicates.  These tests
pin the mechanics-layer half of that contract: a live token reads identically
forever inside its TTL, and an absent one always reads as expired — never as
"already used", a distinction that no longer exists.
"""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.attendance.utils import qr_tokens
from apps.attendance.utils.qr_tokens import (
    InvalidTokenError,
    TokenExpiredError,
    generate_token,
    get_qr_token_ttl_seconds,
    validate_token,
)


def _store(token, value):
    """Write through the same store ``generate_token`` uses.

    Under Redis the module writes with the raw client (no Django key
    versioning), so a test that pokes ``cache.set`` would be editing a
    *different* key and would silently pass/fail for the wrong reason.
    """
    client = qr_tokens._redis_client()
    if client is not None:
        client.set(qr_tokens._key(token), value, ex=10)
    else:
        cache.set(qr_tokens._key(token), value, timeout=10)


def _forget(token):
    """Expire a token exactly as the TTL would."""
    client = qr_tokens._redis_client()
    if client is not None:
        client.delete(qr_tokens._key(token))
    else:
        cache.delete(qr_tokens._key(token))


class QrTokenValidationContractTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.checkpoint_id = "11111111-1111-1111-1111-111111111111"
        self.session_id = "22222222-2222-2222-2222-222222222222"

    def _issue(self, **kwargs):
        token = generate_token(
            session_id=kwargs.get("session_id", self.session_id),
            checkpoint_id=kwargs.get("checkpoint_id", self.checkpoint_id),
        )
        self.assertTrue(token)
        return token

    def test_token_ttl_is_the_ten_second_brit035_default(self):
        self.assertEqual(get_qr_token_ttl_seconds(), 10)

    def test_station_token_binds_session_checkpoint_and_scope(self):
        token = self._issue()
        payload = validate_token(token)
        self.assertEqual(payload["checkpoint_id"], self.checkpoint_id)
        self.assertEqual(payload["session_id"], self.session_id)
        self.assertEqual(payload["scope"], "STATION")

    def test_projected_token_binds_session_and_scope_only(self):
        token = self._issue(checkpoint_id=None)
        payload = validate_token(token)
        self.assertEqual(payload["session_id"], self.session_id)
        self.assertNotIn("checkpoint_id", payload)
        self.assertEqual(payload["scope"], "PROJECTOR")

    def test_scope_is_derived_server_side_not_from_the_caller(self):
        """No argument can turn a projected issuance into a station token."""
        token = self._issue(checkpoint_id=None)
        payload = validate_token(token)
        # The caller cannot smuggle a checkpoint binding into the payload.
        self.assertEqual(payload["scope"], "PROJECTOR")

    def test_validation_does_not_consume_the_shared_code(self):
        """BR-039: the class behind the first scanner must still get through."""
        token = self._issue()
        first = validate_token(token)
        second = validate_token(token)
        third = validate_token(token)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_validating_one_token_does_not_affect_another(self):
        first = self._issue()
        second = self._issue(session_id="33333333-3333-3333-3333-333333333333")
        validate_token(first)
        payload = validate_token(second)
        self.assertNotEqual(payload["session_id"], self.session_id)

    def test_expired_token_raises_expired(self):
        """The only terminal failure this layer reports (mapped to 404)."""
        token = self._issue()
        _forget(token)
        with self.assertRaises(TokenExpiredError):
            validate_token(token)

    def test_never_issued_token_raises_expired(self):
        with self.assertRaises(TokenExpiredError):
            validate_token("this-token-was-never-issued")

    def test_empty_and_non_string_tokens_raise_expired(self):
        for bad in ("", None, 12345, []):
            with self.subTest(token=bad):
                with self.assertRaises(TokenExpiredError):
                    validate_token(bad)

    def test_unreadable_cached_payload_raises_invalid_not_expired(self):
        """A corrupted store is a different failure from a lapsed TTL."""
        token = self._issue()
        # Unparseable bytes in the live slot: reading it must be INVALID (404),
        # never a claim that the code merely aged out.
        _store(token, "{not-json")
        with self.assertRaises(InvalidTokenError):
            validate_token(token)

    def test_generated_tokens_are_unique_and_long(self):
        """256 bits of entropy via secrets; collisions are not acceptable."""
        tokens = {self._issue() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        for token in tokens:
            self.assertGreaterEqual(len(token), 40)
