"""QR token mechanics tests — specifically the backend-independent contract.

The defect these guard against
-----------------------------
``consume_token`` used to report failure differently depending on the cache
backend:

* LocMem kept a process-global ``_LOCAL_USED_KEYS`` set, so it could tell an
  expired token from a replayed one -- expired raised ``TokenExpiredError``.
* Redis cannot: ``GET``+``DEL`` returns nil for both, so it raised
  ``TokenAlreadyUsedError`` for everything.

The view maps those to 404 and 409 respectively, so **the same expired QR code
returned a different HTTP status depending on the deployment's cache**. Tests
run under LocMem and production runs under Redis, so the suite was verifying a
code path production never took.

``consume_token`` now writes a TTL tombstone on consumption, so both backends
separate "expired" (404) from "already used" (409). These tests pin that
contract at the mechanics layer, where it is unambiguous.
"""

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.attendance.utils import qr_tokens
from apps.attendance.utils.qr_tokens import (
    TokenAlreadyUsedError,
    TokenExpiredError,
    consume_token,
    generate_token,
)


class QrTokenConsumptionContractTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.checkpoint_id = "11111111-1111-1111-1111-111111111111"
        self.session_id = "22222222-2222-2222-2222-222222222222"

    def _issue(self):
        token = generate_token(
            checkpoint_id=self.checkpoint_id, session_id=self.session_id
        )
        self.assertTrue(token)
        return token

    def test_fresh_token_consumes_and_returns_its_binding(self):
        token = self._issue()
        payload = consume_token(token)
        self.assertEqual(payload["checkpoint_id"], self.checkpoint_id)
        self.assertEqual(payload["session_id"], self.session_id)

    def test_replayed_token_raises_already_used(self):
        """BR-038: once consumed, never valid again."""
        token = self._issue()
        consume_token(token)
        with self.assertRaises(TokenAlreadyUsedError):
            consume_token(token)

    def test_expired_token_raises_expired_not_already_used(self):
        """The distinction that used to vanish on Redis.

        Simulates TTL expiry by deleting the live key without leaving a
        tombstone -- exactly what Redis does when the key ages out. The result
        must be ``TokenExpiredError`` so the view returns 404, not 409.
        """
        token = self._issue()
        cache.delete(qr_tokens._key(token))
        with self.assertRaises(TokenExpiredError):
            consume_token(token)

    def test_never_issued_token_raises_expired(self):
        """A token that never existed is expired, never "already used"."""
        with self.assertRaises(TokenExpiredError):
            consume_token("this-token-was-never-issued")

    def test_empty_and_non_string_tokens_raise_expired(self):
        for bad in ("", None, 12345, []):
            with self.subTest(token=bad):
                with self.assertRaises(TokenExpiredError):
                    consume_token(bad)

    def test_consuming_one_token_does_not_affect_another(self):
        """No cross-contamination between concurrently live checkpoints."""
        first = self._issue()
        second = self._issue()
        consume_token(first)
        # second is untouched and still consumable
        payload = consume_token(second)
        self.assertEqual(payload["checkpoint_id"], self.checkpoint_id)

    def test_used_tombstone_expires_so_the_store_stays_bounded(self):
        """The tombstone must be TTL'd, not an unbounded process-global set."""
        token = self._issue()
        consume_token(token)
        tombstone = qr_tokens._used_key(token)
        self.assertTrue(cache.get(tombstone))
        # Simulate the TTL elapsing.
        cache.delete(tombstone)
        # With both the live key and the tombstone gone, the token reads as
        # expired -- the correct terminal state, and the store no longer
        # carries anything for it.
        with self.assertRaises(TokenExpiredError):
            consume_token(token)

    def test_generated_tokens_are_unique_and_long(self):
        """256 bits of entropy via secrets; collisions are not acceptable."""
        tokens = {self._issue() for _ in range(50)}
        self.assertEqual(len(tokens), 50)
        for token in tokens:
            self.assertGreaterEqual(len(token), 40)