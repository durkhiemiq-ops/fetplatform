"""One-time email-verification OTP mechanics.

Same discipline as ``apps.attendance.utils.qr_tokens``: short-lived,
single-use secrets with a settings-driven TTL, issued and consumed
atomically.  This module deliberately owns no authorization or account
decisions — the views decide who may issue or consume a code; this module
only guarantees the secret's properties.

Rules enforced here (the qr_tokens threat model applied to OTP delivery):
- The OTP value is a secret while live: it is returned to the caller exactly
  once for immediate delivery and is never stored, logged, or echoed.
  What persists is a keyed hash (HMAC-SHA256 keyed by SECRET_KEY and bound
  to the identity), so a cache leak does not reveal live codes and a hash
  cannot be replayed against a different account.
- Wrong-code attempts are counted per identity, not per IP: after
  EMAIL_OTP_MAX_ATTEMPTS failures the code is destroyed no matter which
  source keeps guessing — a per-IP throttle alone is bypassable from a
  botnet, while a 10^6 code space is otherwise grindable.
- Issuing (registration or resend) atomically replaces any previous code
  and clears the attempt counter, so a stale intercepted code dies the
  moment a fresh one goes out.
- Redis path is one server-side Lua operation (atomic).  The local/dev
  path uses one process lock — the same single-process caveat qr_tokens
  documents: production must use Redis for multi-worker atomicity.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from enum import Enum
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

# LocMem (dev/test) has no atomic compare-and-delete; guard the whole
# read/compare/increment/delete sequence like qr_tokens' local branch does.
_LOCAL_OTP_LOCK = threading.Lock()

# KEYS[1]=code key, KEYS[2]=attempts key.  ARGV[1]=hash, ARGV[2]=ttl.
# Issue = publish the new secret and zero the attempt counter, atomically,
# so resend always invalidates the previous code.
_ISSUE_LUA = """
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
redis.call('DEL', KEYS[2])
return 1
"""

# KEYS[1]=code key, KEYS[2]=attempts key.
# ARGV[1]=expected hash, ARGV[2]=ttl, ARGV[3]=max attempts.
# Returns 1 only when the presented code matches the stored hash; the key is
# deleted in every terminal case (verified, or attempts exhausted), so a code
# can never verify twice and a grinded code dies regardless of source IP.
_VERIFY_LUA = """
local stored = redis.call('GET', KEYS[1])
if not stored then
  return 0
end
if stored == ARGV[1] then
  redis.call('DEL', KEYS[1])
  redis.call('DEL', KEYS[2])
  return 1
end
local attempts = redis.call('INCR', KEYS[2])
if attempts == 1 then
  redis.call('EXPIRE', KEYS[2], tonumber(ARGV[2]))
end
if attempts >= tonumber(ARGV[3]) then
  redis.call('DEL', KEYS[1])
  redis.call('DEL', KEYS[2])
end
return 0
"""


class OTPError(ValueError):
    """Base error for OTP mechanics."""


class OTPResult(Enum):
    """Outcome of a consume attempt.

    Callers MUST collapse every non-VERIFIED value into one generic failure
    response — distinguishing them would rebuild the email-enumeration
    oracle that register deliberately does not expose (BR-203).
    """

    VERIFIED = "verified"
    INVALID = "invalid"  # wrong, expired, absent, or attempt-capped


def get_otp_ttl_seconds() -> int:
    """Return the configured TTL; positive, from settings — never hardcoded."""
    ttl = int(getattr(settings, "EMAIL_OTP_TTL_SECONDS", 600))
    if ttl <= 0:
        raise OTPError("Email OTP TTL must be positive")
    return ttl


def get_otp_max_attempts() -> int:
    attempts = int(getattr(settings, "EMAIL_OTP_MAX_ATTEMPTS", 5))
    if attempts < 1:
        raise OTPError("Email OTP max attempts must be at least 1")
    return attempts


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _code_key(email: str) -> str:
    return f"account:email_otp:{email}"


def _attempts_key(email: str) -> str:
    return f"account:email_otp:attempts:{email}"


def _generate_code() -> str:
    """Cryptographically strong, zero-padded six digits (000000-999999)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(email: str, code: str) -> str:
    """Keyed (SECRET_KEY-peppered) hash bound to the identity.

    A leaked cache dump cannot be reduced to a bare 10^6 rainbow table, and
    the stored value is useless against any other account.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"{email}:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _redis_client() -> Optional[object]:
    """Return a raw Redis client only for Django's Redis cache backend."""
    backend = getattr(cache, "_cache", None)
    if backend is None or not hasattr(backend, "get_client"):
        return None
    return backend.get_client(write=True)


def issue_otp(email: str) -> str:
    """Issue a fresh code, replacing any previous one, and return the raw value.

    The raw code is returned exactly once so the caller can email it; only
    its keyed hash is persisted.  Resend reuses this function, which is what
    makes "a fresh code kills the old one" structural rather than aspirational.
    """
    email = normalize_email(email)
    if not email:
        raise OTPError("Email is required to issue a code")

    code = _generate_code()
    ttl = get_otp_ttl_seconds()
    expected = _hash_code(email, code)
    client = _redis_client()
    if client is not None:
        client.eval(
            _ISSUE_LUA,
            2,
            _code_key(email),
            _attempts_key(email),
            expected,
            ttl,
        )
    else:
        # Development/test simulation only: one process lock provides the
        # issue/replace atomicity that Redis gives natively.
        with _LOCAL_OTP_LOCK:
            cache.set(_code_key(email), expected, timeout=ttl)
            cache.delete(_attempts_key(email))
    return code


def verify_otp(email: str, code: str) -> OTPResult:
    """Atomically check-and-consume a code.

    Exactly-once semantics with no race window (one Lua operation on Redis,
    one process lock locally); the attempt counter lives beside the code so
    brute force is capped per identity even from rotating source IPs.
    """
    email = normalize_email(email)
    if not email or not isinstance(code, str) or not code:
        return OTPResult.INVALID

    ttl = get_otp_ttl_seconds()
    max_attempts = get_otp_max_attempts()
    expected = _hash_code(email, code)
    client = _redis_client()
    if client is not None:
        raw = client.eval(
            _VERIFY_LUA,
            2,
            _code_key(email),
            _attempts_key(email),
            expected,
            ttl,
            max_attempts,
        )
        return OTPResult.VERIFIED if raw == 1 else OTPResult.INVALID

    with _LOCAL_OTP_LOCK:
        stored = cache.get(_code_key(email))
        if stored is None:
            return OTPResult.INVALID
        if hmac.compare_digest(stored, expected):
            cache.delete(_code_key(email))
            cache.delete(_attempts_key(email))
            return OTPResult.VERIFIED
        attempts = int(cache.get(_attempts_key(email)) or 0) + 1
        cache.set(_attempts_key(email), attempts, timeout=ttl)
        if attempts >= max_attempts:
            cache.delete(_code_key(email))
            cache.delete(_attempts_key(email))
        return OTPResult.INVALID


def send_verification_email(email: str, code: str) -> None:
    """Dispatch the raw code to its owner.  The code appears only here, in
    the outbound message body — never in a log line or an API response.

    Delivery configuration comes from settings (console backend in dev,
    SMTP via env in production); this function performs no throttling —
    callers' throttle scopes own the abuse economics.
    """
    ttl_minutes = max(1, get_otp_ttl_seconds() // 60)
    subject = "Your FET Platform verification code"
    message = (
        f"Your verification code is: {code}\n\n"
        f"The code expires in {ttl_minutes} minutes. Never share it — "
        "staff will never ask for it.\n"
        "If you did not create an account with this address, ignore "
        "this email.\n"
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
